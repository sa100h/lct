-- Producer-side channel mapping (decision 2026-09-21).
-- The broker keys purely on subject_id == channel_id (the ml-service channel id);
-- the mapping between app equipment and ML channels is a producer concern.
--
-- Contents:
--   channel_directory       organizer's channel reference (one row per data channel)
--   equipment_channel_map   confirmed equipment <-> channel pairs (1:1 identity)
--   uq on sensor_features   producer-safe dedup key for idempotent upserts

-- Reference of data channels from the organizer's register
-- (ml-data/справочник_каналов_датчиков_NEW.csv). channel_id == subject_id == sensor_features.channel_id.
CREATE TABLE IF NOT EXISTS channel_directory (
    channel_id   text PRIMARY KEY,
    type_system  text,                       -- e.g. «Газовая охрана»
    type_sensor  text,                       -- e.g. «Газовый датчик»
    tag_cabinet  text,                       -- engineer cabinet tag, e.g. 884-1.1.546.2.
    object_id    text,                       -- object id (справочник_объектов_диспетчер)
    sensor_name  text,
    loaded_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_channel_directory_object ON channel_directory (object_id);

-- Confirmed equipment <-> channel mapping. By decision equipment.external_id is the
-- channel id, so pairs are identity (1:1); the table records the confirmation
-- so joins have a verifiable source instead of an implicit assumption.
CREATE TABLE IF NOT EXISTS equipment_channel_map (
    equipment_external_id text NOT NULL,      -- == equipment.external_id (organizer register)
    channel_id            text NOT NULL REFERENCES channel_directory(channel_id),
    note                  text,
    mapped_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (equipment_external_id, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_equipment_channel_map_channel ON equipment_channel_map (channel_id);

-- Producer-safe dedup: one observation per (channel, timestamp).
-- Producers upsert with ON CONFLICT (channel_id, as_of); re-delivery is idempotent
-- and the queue fan-out trigger stays deduped via uq_queue_dedup downstream.
ALTER TABLE sensor_features
    ADD CONSTRAINT uq_sensor_features_channel_asof UNIQUE (channel_id, as_of);
