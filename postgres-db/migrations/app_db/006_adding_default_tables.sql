-- Справочник типов инженерных систем
CREATE TABLE engineering_systems (
    id INT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE -- 'Название инженерной системы'
);

-- Справочник типов датчиков
CREATE TABLE sensor_types (
    id INT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE, -- 'Название типа датчика',
    engineering_system_id INT NOT NULL, -- 'ID типа инженерной системы, к которой относится датчик',
   
	CONSTRAINT fk__sensor_types__engineering_system_types__engineering_system_id__id 
		FOREIGN KEY (engineering_system_id) 
		REFERENCES engineering_systems(id)
);

-- Справочник видов объектов
CREATE TABLE object_types (
	id INT PRIMARY KEY,
	name TEXT NOT NULL UNIQUE -- 'Название вида объекта'
);

-- Справочник объектов диспетчера
CREATE TABLE dispatcher_objects (
	id INT PRIMARY KEY,
	hierarchy_level INT NOT NULL, -- 'Уровень иерархии объекта',
	parent_id INT NULL, -- 'ID родительского объекта',
	object_type_id INT NOT NULL, -- 'ID вида объекта',
	dispatcher_object_name TEXT NOT NULL, -- 'Диспетчерское название объекта',
	coordinates DOUBLE PRECISION  NOT NULL, -- 'Координаты объекта',

	CONSTRAINT fk__dispatcher_objects__dispatcher_objects__parent_id__id 
		FOREIGN KEY (parent_id) 
		REFERENCES dispatcher_objects(id),
    CONSTRAINT fk__dispatcher_objects__object_types__object_type_id__id 
		FOREIGN KEY (object_type_id) 
		REFERENCES object_types(id)
);

-- Индексы для внешних ключей в таблице dispatcher_objects
CREATE INDEX idx_dispatcher_objects_parent ON dispatcher_objects(parent_id);
CREATE INDEX idx_dispatcher_objects_type ON dispatcher_objects(object_type_id);


-- Статусы датчиков
CREATE TABLE sensor_statuses (
    id INT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE -- 'Название статуса датчика (например, "Норма", "Тревога")'
);

-- Справочник каналов датчиков
CREATE TABLE sensor_channels (
    id INT PRIMARY KEY,
    sensor_type_id INT NOT NULL,  -- 'ID типа датчика',
    sensor_name TEXT NOT NULL, -- 'Имя/метка конкретного датчика',
    dispatcher_object_id INT NOT NULL,  -- 'ID объекта, к которому привязан датчик',
    sensor_status_id INT NOT NULL, -- 'Текущий статус датчика',
    
	CONSTRAINT fk__sensor_channels__sensor_types__sensor_type_id__id 
		FOREIGN KEY (sensor_type_id) 
		REFERENCES sensor_types(id),
    CONSTRAINT fk__sensor_channels__dispatcher_objects__dispatcher_object_id__id 
		FOREIGN KEY (dispatcher_object_id) 
		REFERENCES dispatcher_objects(id),
    CONSTRAINT fk__sensor_channels__sensor_statuses__sensor_status_id__id 
		FOREIGN KEY (sensor_status_id) 
		REFERENCES sensor_statuses(id)
);
-- Индексы для внешних ключей в таблице sensor_channels
CREATE INDEX idx_sensor_channels_type ON sensor_channels(sensor_type_id);
CREATE INDEX idx_sensor_channels_object ON sensor_channels(dispatcher_object_id);
CREATE INDEX idx_sensor_channels_status ON sensor_channels(sensor_status_id);


-- Журнал событий
CREATE TABLE events_log (
    id BIGINT PRIMARY KEY,
    sensor_channel_id INT NOT NULL, -- 'ID канала датчика, породившего событие',
    event_datetime TIMESTAMP  NOT NULL, -- 'Дата и время события',
    is_alarm BOOLEAN NOT NULL, -- 'Флаг тревожного события',
    sensor_value TEXT NULL, -- 'Значение датчика в момент события',
    
	CONSTRAINT fk__events_log_channel__sensor_channels__sensor_channel_id__id 
		FOREIGN KEY (sensor_channel_id) 
		REFERENCES sensor_channels(id)
);

-- Индексы для внешних ключей в таблице events_log
CREATE INDEX idx_events_log_channel ON events_log(sensor_channel_id);
CREATE INDEX idx_events_log_datetime ON events_log(event_datetime); -- Полезен для выборки по времени
CREATE INDEX idx_events_log_alarm ON events_log(is_alarm); -- Полезен для фильтрации тревог
