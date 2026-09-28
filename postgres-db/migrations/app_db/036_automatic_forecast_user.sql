-- Use a dedicated author for hourly forecast runs, including existing entries.
INSERT INTO users (id, login, is_active)
VALUES ('40ab0edd-9261-42f2-b6c9-d18f00cf475f'::uuid, 'auto_forecast', true)
ON CONFLICT (id) DO UPDATE
SET login = EXCLUDED.login,
    is_active = EXCLUDED.is_active;

ALTER TABLE forecast_journal DROP CONSTRAINT forecast_journal_origin_chk;

UPDATE forecast_journal
SET user_created_id = '40ab0edd-9261-42f2-b6c9-d18f00cf475f'::uuid
WHERE run_type = 'auto';

ALTER TABLE forecast_journal
    ALTER COLUMN user_created_id SET NOT NULL,
    ADD CONSTRAINT forecast_journal_origin_chk
    CHECK (
        (run_type = 'manual' AND scheduled_hour IS NULL)
        OR (
            run_type = 'auto'
            AND user_created_id = '40ab0edd-9261-42f2-b6c9-d18f00cf475f'::uuid
            AND scheduled_hour IS NOT NULL
        )
    );
