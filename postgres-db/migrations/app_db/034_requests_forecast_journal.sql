ALTER TABLE requests
    ADD COLUMN IF NOT EXISTS forecast_journal_id uuid;

ALTER TABLE requests
    ADD COLUMN IF NOT EXISTS dispatcher_objects_id json;

ALTER TABLE requests
    DROP CONSTRAINT IF EXISTS fk__requests__forecast_results__forecast_id__id;

ALTER TABLE requests
    ALTER COLUMN forecast_id DROP NOT NULL;

ALTER TABLE requests
    ALTER COLUMN execution_description DROP NOT NULL;

UPDATE requests
SET forecast_journal_id = (
    SELECT r.forecast_journal_id
    FROM forecast_results r
    WHERE r.id = requests.forecast_id
)
WHERE forecast_journal_id IS NULL AND forecast_id IS NOT NULL;

ALTER TABLE requests
    DROP CONSTRAINT IF EXISTS fk__requests__forecast_journal__forecast_journal_id__id;

ALTER TABLE requests
    ADD CONSTRAINT fk__requests__forecast_journal__forecast_journal_id__id
    FOREIGN KEY (forecast_journal_id) REFERENCES forecast_journal(id);

ALTER TABLE requests
    ADD CONSTRAINT fk__requests__forecast_results__forecast_id__id
    FOREIGN KEY (forecast_id) REFERENCES forecast_results(id);

CREATE INDEX IF NOT EXISTS idx_requests_forecast_journal
    ON requests (forecast_journal_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM requests WHERE forecast_journal_id IS NULL) THEN
        ALTER TABLE requests ALTER COLUMN forecast_journal_id SET NOT NULL;
    END IF;
END $$;
