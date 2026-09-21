-- ml-broker support tables.
-- broker = async bridge: Postgres NOTIFY/poll -> ml-service /predict -> predictions.
-- The durable queue is the source of truth; NOTIFY is only a wake-up.

-- Raw feature source the producer writes into. channel_id == ml-service subject_id.
CREATE TABLE IF NOT EXISTS sensor_features (
    id          bigserial PRIMARY KEY,
    channel_id  text NOT NULL,                 -- == ml-service subject_id (e.g. "103904")
    as_of       timestamptz NOT NULL,          -- observation timestamp (dedup key)
    features    jsonb NOT NULL,                -- feature vector (keys = category feature names)
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sensor_features_channel ON sensor_features (channel_id, as_of DESC);

-- Durable predict queue: source of truth; NOTIFY is only a wake-up.
CREATE TABLE IF NOT EXISTS ml_predict_queue (
    id           bigserial PRIMARY KEY,
    category     text NOT NULL,                -- sensor-failure | fire-risk | unauthorized-access | infrastructure-wear
    subject_id   text NOT NULL,
    as_of        timestamptz NOT NULL,
    priority     integer NOT NULL DEFAULT 0,
    status       text NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
    attempts     integer NOT NULL DEFAULT 0,
    error        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    claimed_at   timestamptz,
    finished_at  timestamptz,
    retry_after  timestamptz,
    CONSTRAINT uq_queue_dedup UNIQUE (category, subject_id, as_of),
    CONSTRAINT ml_predict_queue_status_chk CHECK (status IN ('pending','running','done','failed'))
);
CREATE INDEX IF NOT EXISTS idx_queue_status_id ON ml_predict_queue (status, id);

-- Crontab-analog for scheduled work.
CREATE TABLE IF NOT EXISTS ml_schedule (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind         text NOT NULL,                -- predict-all | retrain
    name         text NOT NULL,
    cron_expr    text NOT NULL,                -- standard 5-field cron
    args         jsonb NOT NULL DEFAULT '{}',  -- e.g. {"categories":["sensor-failure"]}
    enabled      boolean NOT NULL DEFAULT true,
    last_run_at  timestamptz,
    next_run_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_ml_schedule_name UNIQUE (name),
    CONSTRAINT ml_schedule_kind_chk CHECK (kind IN ('predict-all','retrain'))
);

-- Retrain run log.
CREATE TABLE IF NOT EXISTS ml_retrain_runs (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    category     text,                          -- null = all categories
    status       text NOT NULL DEFAULT 'running',  -- running | done | failed
    metrics      jsonb
);

-- Conflict-safe predictions: at-least-once queue delivery must not create dup rows.
ALTER TABLE predictions
    ADD CONSTRAINT uq_predictions_dedup UNIQUE (category, subject_id, predicted_at);

-- Fan a new sensor_features row out to the queue (one row per category) and ping listeners.
CREATE OR REPLACE FUNCTION ml_enqueue_from_features()
RETURNS trigger AS $$
DECLARE c text;
BEGIN
    FOREACH c IN ARRAY ARRAY['sensor-failure','fire-risk','unauthorized-access','infrastructure-wear']
    LOOP
        INSERT INTO ml_predict_queue (category, subject_id, as_of)
        VALUES (c, NEW.channel_id, NEW.as_of)
        ON CONFLICT (category, subject_id, as_of) DO NOTHING;
    END LOOP;
    PERFORM pg_notify('ml_predict', '1');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_enqueue_features ON sensor_features;
CREATE TRIGGER trg_enqueue_features
    AFTER INSERT ON sensor_features
    FOR EACH ROW EXECUTE FUNCTION ml_enqueue_from_features();

-- Seed default schedule; idempotent across re-runs.
INSERT INTO ml_schedule (kind, name, cron_expr, args) VALUES
  ('predict-all', 'hourly-predict', '0 * * * *', '{}'),
  ('retrain',     'daily-retrain',  '30 4 * * *', '{}')
ON CONFLICT DO NOTHING;
