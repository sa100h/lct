-- Names are display values, not stable identifiers. The organizer's reference
-- legitimately contains duplicate object and sensor names; ids remain unique.
ALTER TABLE dispatcher_objects
    DROP CONSTRAINT IF EXISTS dispatcher_objects_dispatcher_object_name_key;
ALTER TABLE sensor_channels
    DROP CONSTRAINT IF EXISTS sensor_channels_sensor_name_key;
