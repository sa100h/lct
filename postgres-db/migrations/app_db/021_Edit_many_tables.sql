
--справочник каналов датчиков добавляем 
--		Время добавления Нужно ли???
ALTER TABLE sensor_channels ADD COLUMN loaded_at timestamptz NOT NULL DEFAULT now();


-- Обслуживание датчиков
CREATE TABLE IF NOT EXISTS sensor_maintenance (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
	sensor_channel_id INT NOT NULL, -- 'ID канала датчика, породившего событие',
    note text NOT NULL,              -- 
    mapped_at timestamptz NOT NULL DEFAULT now(),	
	
	CONSTRAINT fk__sensor_maintenance__sensor_channels__sensor_channel_id__id 
		FOREIGN KEY (sensor_channel_id) 
		REFERENCES sensor_channels(id)
);


--Характеристики датчика ( темп, ..)

ALTER TABLE sensor_features ADD COLUMN sensor_channel_id INT NOT NULL;

ALTER TABLE sensor_features 
ADD CONSTRAINT fk__sensor_features__sensor_channels__sensor_channel_id__id 
		FOREIGN KEY (sensor_channel_id) 
		REFERENCES sensor_channels(id);
		
		
UPDATE sensor_features
SET sensor_channel_id = channel_id::integer;

ALTER TABLE sensor_features DROP COLUMN channel_id;



--Журнал прогнозов
ALTER TABLE forecast_journal ADD COLUMN params JSONB;
ALTER TABLE forecast_journal ADD COLUMN status text;


--Заявка
ALTER TABLE requests ADD COLUMN priority integer;
ALTER TABLE requests ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE requests ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

--Удаление таблиц
drop table equipment_channel_map;
drop table channel_directory;

drop table maintenance_requests;
drop table predictions;

drop table sensor_features;
drop table equipment;