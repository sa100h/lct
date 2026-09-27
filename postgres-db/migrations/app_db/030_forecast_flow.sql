-- Forecast flow bridge after migrations 019 and 021.
-- 021 removes the legacy predictions and sensor_features tables.
-- This migration uses forecast_journal, sensor_channels, ml_predict_queue and
-- forecast_results only.

ALTER TABLE forecast_journal
    ADD COLUMN IF NOT EXISTS is_cancelled boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'pending';

UPDATE forecast_journal SET is_cancelled = false WHERE is_cancelled IS NULL;
UPDATE forecast_journal SET status = 'pending' WHERE status IS NULL;
ALTER TABLE forecast_journal ALTER COLUMN is_cancelled SET DEFAULT false;
ALTER TABLE forecast_journal ALTER COLUMN is_cancelled SET NOT NULL;
ALTER TABLE forecast_journal ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE forecast_journal ALTER COLUMN status SET NOT NULL;

ALTER TABLE forecast_journal DROP CONSTRAINT IF EXISTS forecast_journal_status_chk;
ALTER TABLE forecast_journal
    ADD CONSTRAINT forecast_journal_status_chk
    CHECK (status IN ('pending', 'running', 'done', 'error', 'cancelled'));
CREATE INDEX IF NOT EXISTS idx_forecast_journal_status
    ON forecast_journal (status, creation_time);

ALTER TABLE forecast_results
    -- Legacy package-level rows may have NULL here; broker-created rows do not.
    ALTER COLUMN dispatcher_object_id DROP NOT NULL;
ALTER TABLE forecast_results
    ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE forecast_results
    DROP CONSTRAINT IF EXISTS uq_forecast_results_name;

ALTER TABLE ml_predict_queue
    ADD COLUMN IF NOT EXISTS forecast_journal_id uuid REFERENCES forecast_journal(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS forecast_name text,
    ADD COLUMN IF NOT EXISTS features jsonb,
    ADD COLUMN IF NOT EXISTS dispatcher_object_id integer,
    ADD COLUMN IF NOT EXISTS result jsonb;

ALTER TABLE ml_predict_queue DROP CONSTRAINT IF EXISTS ml_predict_queue_status_chk;
ALTER TABLE ml_predict_queue
    ADD CONSTRAINT ml_predict_queue_status_chk
    CHECK (status IN ('pending', 'running', 'done', 'failed', 'cancelled'));
ALTER TABLE ml_predict_queue DROP CONSTRAINT IF EXISTS uq_queue_dedup;
ALTER TABLE ml_predict_queue DROP CONSTRAINT IF EXISTS uq_forecast_queue_dedup;
ALTER TABLE ml_predict_queue
    ADD CONSTRAINT uq_forecast_queue_dedup
    UNIQUE (forecast_journal_id, subject_id, category, as_of);
CREATE INDEX IF NOT EXISTS idx_queue_journal_status
    ON ml_predict_queue (forecast_journal_id, status)
    WHERE forecast_journal_id IS NOT NULL;

CREATE OR REPLACE FUNCTION trg_forecast_journal_notify() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM pg_notify('lct_ml_forecast',
            json_build_object('action', 'new', 'forecast_id', NEW.id)::text);
    ELSIF TG_OP = 'UPDATE' AND NEW.is_cancelled AND NOT OLD.is_cancelled THEN
        PERFORM pg_notify('lct_ml_forecast',
            json_build_object('action', 'cancelled', 'forecast_id', NEW.id)::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_forecast_journal_notify ON forecast_journal;
CREATE TRIGGER trg_forecast_journal_notify
    AFTER INSERT OR UPDATE ON forecast_journal
    FOR EACH ROW EXECUTE FUNCTION trg_forecast_journal_notify();

CREATE OR REPLACE FUNCTION trg_forecast_results_notify() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('lct_ml_forecast_result',
        json_build_object(
            'forecast_journal_id', NEW.forecast_journal_id,
            'forecast_name', NEW.forecast_name,
            'dispatcher_object_id', NEW.dispatcher_object_id,
            'status', CASE WHEN NEW.is_cancelled THEN 'cancelled'
                           WHEN NEW.is_erroneous THEN 'error'
                           ELSE 'done' END)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_forecast_results_notify ON forecast_results;
CREATE TRIGGER trg_forecast_results_notify
    AFTER INSERT OR UPDATE ON forecast_results
    FOR EACH ROW EXECUTE FUNCTION trg_forecast_results_notify();
