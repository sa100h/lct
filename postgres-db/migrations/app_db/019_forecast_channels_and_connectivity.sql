-- A journal entry now contains the latest textual reading for each forecast channel.
-- Existing development entries have no reliable channel snapshot and are left empty.
ALTER TABLE forecast_journal RENAME COLUMN forecast_objects TO forecast_channels;
UPDATE forecast_journal SET forecast_channels = '{}'::jsonb;
ALTER TABLE forecast_journal ALTER COLUMN forecast_channels SET NOT NULL;
ALTER TABLE forecast_journal
    ADD CONSTRAINT forecast_journal_channels_object_chk
    CHECK (jsonb_typeof(forecast_channels) = 'object');

ALTER TABLE forecast_journal ALTER COLUMN user_created_id DROP NOT NULL;
ALTER TABLE forecast_journal
    ADD COLUMN run_type text NOT NULL DEFAULT 'manual',
    ADD COLUMN scheduled_hour timestamptz;
ALTER TABLE forecast_journal
    ADD CONSTRAINT forecast_journal_run_type_chk
    CHECK (run_type IN ('manual', 'auto')),
    ADD CONSTRAINT forecast_journal_origin_chk
    CHECK (
        (run_type = 'manual' AND user_created_id IS NOT NULL AND scheduled_hour IS NULL)
        OR (run_type = 'auto' AND user_created_id IS NULL AND scheduled_hour IS NOT NULL)
    );
CREATE UNIQUE INDEX uq_forecast_journal_auto_hour
    ON forecast_journal (scheduled_hour) WHERE run_type = 'auto';

INSERT INTO sensor_statuses (id, name)
SELECT COALESCE(MAX(id), 0) + 1, 'Нет связи' FROM sensor_statuses
ON CONFLICT (name) DO NOTHING;

CREATE INDEX idx_events_log_channel_time_id
    ON events_log (sensor_channel_id, event_datetime DESC, id DESC);
