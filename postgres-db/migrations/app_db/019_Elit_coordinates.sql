-- -- Справочник объектов диспетчера
-- 	Изменяю координаты из DOUBLE PRECISION в text
ALTER TABLE dispatcher_objects ALTER COLUMN coordinates TYPE text;

-- Обновляю координаты в формат: широта; долгота
-- Москва: 55.75583° с. ш.; 37.61778° в. д..
Update dispatcher_objects
	SET coordinates = '55.75583; 37.61778'
