-- Replace the single placeholder coordinate with an explicit WGS 84 pair.
ALTER TABLE dispatcher_objects RENAME COLUMN coordinates TO latitude;
ALTER TABLE dispatcher_objects ADD COLUMN longitude double precision;

-- Deterministic Moscow-area test coordinates. Production data can replace them
-- without changing the API or schema.
UPDATE dispatcher_objects
SET latitude = 55.60 + ((id / 40) % 30) * 0.01,
    longitude = 37.45 + (id % 40) * 0.01;

ALTER TABLE dispatcher_objects ALTER COLUMN longitude SET NOT NULL;
ALTER TABLE dispatcher_objects
    ADD CONSTRAINT dispatcher_objects_latitude_chk CHECK (latitude BETWEEN -90 AND 90),
    ADD CONSTRAINT dispatcher_objects_longitude_chk CHECK (longitude BETWEEN -180 AND 180);
