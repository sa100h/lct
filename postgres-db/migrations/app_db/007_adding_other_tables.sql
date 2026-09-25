
-- Пользователи
ALTER TABLE users ADD COLUMN dispatcher_object_id INT ;

ALTER TABLE users 
ADD CONSTRAINT fk__users__dispatcher_objects__dispatcher_object_id__id 
	FOREIGN KEY (dispatcher_object_id) 
	REFERENCES dispatcher_objects(id); -- 'ID объекта, за которым закреплен пользователь',


-- Статусы заявок
CREATE TABLE request_statuses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE -- 'Название статуса заявки (например, "Новая", "В работе", "Закрыта")'
);


-- Журнал прогнозов
CREATE TABLE forecast_journal (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL, -- 'Описание журнала/пакета прогнозов',
    user_created_id uuid NOT NULL, -- 'ID пользователя, создавшего журнал',
    forecast_objects JSONB  NULL,-- 'Список объектов прогноза в формате JSON',
    creation_time TIMESTAMP  NOT NULL, -- 'Время создания журнала',
    start_composition_time TIMESTAMP NULL,  -- 'Время начала составления прогноза',
    end_composition_time TIMESTAMP NULL,-- 'Время окончания составления прогноза',
	
    CONSTRAINT fk__forecast_journal__users__user_created_id__id 
		FOREIGN KEY (user_created_id) 
		REFERENCES users(id)
);
-- Индексы для внешних ключей в таблице forecast_journal
CREATE INDEX idx_forecast_journal_creator ON forecast_journal(user_created_id);

-- Результаты прогнозов
CREATE TABLE forecast_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    forecast_journal_id uuid  NOT NULL,-- 'ID журнала, к которому относится прогноз',
    forecast_name TEXT NOT NULL,-- 'Название прогноза',
    forecast_description JSONB NOT NULL,-- 'Описание прогноза',
    dispatcher_object_id INT NOT NULL,-- 'ID объекта прогноза',
    user_dispatcher_id uuid NOT NULL,-- 'ID диспетчера, ответственного за прогноз',
    is_erroneous BOOLEAN NOT NULL,-- 'Флаг ошибочного прогноза',
    is_cancelled BOOLEAN NOT NULL,-- 'Флаг отмененного прогноза',
	
    CONSTRAINT fk__forecast_results__forecast_journal__forecast_journal_id__id
		FOREIGN KEY (forecast_journal_id) 
		REFERENCES forecast_journal(id),
    CONSTRAINT fk__forecast_results__dispatcher_objects__dispatcher_object_id__id
		FOREIGN KEY (dispatcher_object_id) 
		REFERENCES dispatcher_objects(id),
    CONSTRAINT fk__forecast_results__users__user_dispatcher_id__id 
		FOREIGN KEY (user_dispatcher_id) 
		REFERENCES users(id)
);
-- Индексы для внешних ключей в таблице forecast_results
CREATE INDEX idx_forecast_results_journal ON forecast_results(forecast_journal_id);
CREATE INDEX idx_forecast_results_object ON forecast_results(dispatcher_object_id);
CREATE INDEX idx_forecast_results_dispatcher ON forecast_results(user_dispatcher_id);



-- Промежуточная таблица для связи многие-ко-многим между прогнозами и событиями
CREATE TABLE forecast_events_link (
    forecast_id uuid NOT NULL, -- 'ID прогноза из таблицы forecast_results',
    event_id BIGINT NOT NULL,-- 'ID события из таблицы events_log',
	
    CONSTRAINT pk__forecast_events_link__forecast_id__event_id
		PRIMARY KEY (forecast_id, event_id),
    CONSTRAINT fk_forecast_events_link__forecast_results__forecast_id__id
		FOREIGN KEY (forecast_id) REFERENCES forecast_results(id),
    CONSTRAINT fk_forecast_events_link__events_log__event_id__id
		FOREIGN KEY (event_id) REFERENCES events_log(id)
);

-- Индексы для ускорения выборки по отдельным полям связи
CREATE INDEX idx_forecast_events_link_forecast ON forecast_events_link(forecast_id);
CREATE INDEX idx_forecast_events_link_event ON forecast_events_link(event_id);



-- Заявки
CREATE TABLE requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    forecast_id uuid  NOT NULL, -- 'ID прогноза, на основании которого создана заявка (может быть NULL)',
    request_description TEXT  NOT NULL, -- 'Описание заявки',
    user_dispatcher_id uuid  NOT NULL, -- 'ID диспетчера, создавшего заявку',
    user_technician_id uuid  NOT NULL, -- 'ID техника, назначенного на выполнение',
    dispatcher_object_id INT  NOT NULL, -- 'ID объекта, к которому относится заявка',
    execution_description TEXT  NOT NULL, -- 'Описание выполнения заявки',
    request_status_id uuid  NOT NULL, -- 'ID статуса заявки',
	
    CONSTRAINT fk__requests__forecast_results__forecast_id__id
		FOREIGN KEY (forecast_id) 
		REFERENCES forecast_results(id),
    CONSTRAINT fk__requests__users__user_dispatcher_id__id
		FOREIGN KEY (user_dispatcher_id) 
		REFERENCES users(id),
    CONSTRAINT fk__requests__users__user_technician_id__id
		FOREIGN KEY (user_technician_id) 
		REFERENCES users(id),
    CONSTRAINT fk__requests__dispatcher_objects__dispatcher_object_id__id
		FOREIGN KEY (dispatcher_object_id) 
		REFERENCES dispatcher_objects(id),
    CONSTRAINT fk__requests__request_statuses__request_status_id__id
		FOREIGN KEY (request_status_id) 
		REFERENCES request_statuses(id)
);
-- Индексы для внешних ключей в таблице requests
CREATE INDEX idx_requests_forecast ON requests(forecast_id);
CREATE INDEX idx_requests_dispatcher ON requests(user_dispatcher_id);
CREATE INDEX idx_requests_technician ON requests(user_technician_id);
CREATE INDEX idx_requests_object ON requests(dispatcher_object_id);
CREATE INDEX idx_requests_status ON requests(request_status_id);