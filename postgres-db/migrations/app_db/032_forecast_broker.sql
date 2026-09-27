-- Forecast broker schema after 030.
-- Idempotent by design; the migration runner may retry a deployment.

-- Fixed service account used as user_dispatcher_id for broker results.
INSERT INTO users (id, login, is_active)
VALUES (
    '77d902da-9f82-40cf-9674-926d4c04243d'::uuid,
    'ml_broker',
    true
)
ON CONFLICT (id) DO UPDATE
SET login = EXCLUDED.login,
    is_active = EXCLUDED.is_active;

ALTER TABLE forecast_results
    DROP CONSTRAINT IF EXISTS uq_forecast_results_name;
ALTER TABLE forecast_results
    DROP CONSTRAINT IF EXISTS uq_forecast_results_journal_object;
ALTER TABLE forecast_results
    ADD CONSTRAINT uq_forecast_results_journal_object
    UNIQUE (forecast_journal_id, dispatcher_object_id);
CREATE INDEX IF NOT EXISTS idx_forecast_results_journal_object
    ON forecast_results (forecast_journal_id, dispatcher_object_id);

ALTER TABLE ml_predict_queue
    DROP CONSTRAINT IF EXISTS uq_forecast_queue_dedup;
ALTER TABLE ml_predict_queue
    ADD CONSTRAINT uq_forecast_queue_dedup
    UNIQUE (forecast_journal_id, subject_id, category, as_of);
ALTER TABLE ml_predict_queue
    DROP CONSTRAINT IF EXISTS ml_predict_queue_status_chk;
ALTER TABLE ml_predict_queue
    ADD CONSTRAINT ml_predict_queue_status_chk
    CHECK (status IN ('pending', 'running', 'done', 'failed', 'cancelled'));
CREATE INDEX IF NOT EXISTS idx_ml_predict_queue_journal_status
    ON ml_predict_queue (forecast_journal_id, status, id)
    WHERE forecast_journal_id IS NOT NULL;

ALTER TABLE forecast_journal
    DROP CONSTRAINT IF EXISTS forecast_journal_status_chk;
ALTER TABLE forecast_journal
    ADD CONSTRAINT forecast_journal_status_chk
    CHECK (status IN ('pending', 'running', 'done', 'error', 'cancelled'));
