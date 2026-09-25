-- Event feed timestamps carry an explicit UTC offset. The table is empty when
-- this migration is introduced; UTC is specified explicitly for deterministic
-- conversion in every PostgreSQL session time zone.
ALTER TABLE events_log
    ALTER COLUMN event_datetime TYPE TIMESTAMPTZ
    USING event_datetime AT TIME ZONE 'UTC';
