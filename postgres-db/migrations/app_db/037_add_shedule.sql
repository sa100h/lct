-- Тип обслуживания
CREATE TABLE service_types (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text not null,								-- 'Название'
	is_non_working boolean not null,
);

INSERT INTO service_types 	(name, is_non_working)
	   VALUES			 	('ТО', true),
							('ТР', true),
							('ТО+ТР', true),
							('Демонтаж', true),
							('Проверка', false),

--		'План-график работ
CREATE TABLE work_schedule (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_type_id INT NOT NULL,  				-- 'ID типа датчика',
    dispatcher_object_id INT NOT NULL,			-- 'ID объекта',
	service_type_id uuid NOT NULL,					-- 'ID объекта',
    start_date DATE,							-- 'Начало работ'
    end_date DATE,								-- 'Окончание работ'
	
	
	CONSTRAINT fk__work_schedule__sensor_types__sensor_type_id__id 
		FOREIGN KEY (sensor_type_id) 
		REFERENCES sensor_types(id),
	 CONSTRAINT fk__work_schedule__dispatcher_objects__dispatcher_object_id__id
		FOREIGN KEY (dispatcher_object_id) 
		REFERENCES dispatcher_objects(id),
	CONSTRAINT fk__work_schedule__service_types__service_type_id__id 
		FOREIGN KEY (service_type_id) 
		REFERENCES service_types(id),
);

