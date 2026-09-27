-- справочник каналов датчиков
ALTER TABLE sensor_channels
    ADD COLUMN IF NOT EXISTS loaded_at timestamptz NOT NULL DEFAULT now();

-- обслуживание датчиков
CREATE TABLE IF NOT EXISTS sensor_maintenance (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_channel_id int NOT NULL,
    note text NOT NULL,
    mapped_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE sensor_maintenance
    DROP CONSTRAINT IF EXISTS fk__sensor_maintenance__sensor_channels__sensor_channel_id__id;
ALTER TABLE sensor_maintenance
    ADD CONSTRAINT fk__sensor_maintenance__sensor_channels__sensor_channel_id__id
    FOREIGN KEY (sensor_channel_id) REFERENCES sensor_channels(id);

-- Legacy sensor_features is removed below; no ALTER/UPDATE is needed.

-- журнал прогнозов
ALTER TABLE forecast_journal ADD COLUMN IF NOT EXISTS params jsonb;
ALTER TABLE forecast_journal ADD COLUMN IF NOT EXISTS status text;

-- заявки
ALTER TABLE requests ADD COLUMN IF NOT EXISTS priority integer;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE requests ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- удаление устаревших таблиц
DROP TABLE IF EXISTS equipment_channel_map;
DROP TABLE IF EXISTS channel_directory;
DROP TABLE IF EXISTS maintenance_requests;
DROP TABLE IF EXISTS predictions;
DROP TABLE IF EXISTS sensor_features;
DROP TABLE IF EXISTS equipment;
