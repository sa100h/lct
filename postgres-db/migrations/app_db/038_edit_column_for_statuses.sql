--довавляем в forecast_journal  статус approved (одобрена)
-- Сначала удаляем старое ограничение
ALTER TABLE forecast_journal DROP CONSTRAINT forecast_journal_status_chk;

-- Затем добавляем новое
ALTER TABLE forecast_journal 
	ADD CONSTRAINT forecast_journal_status_chk 
	CHECK (status IN ('pending', 'running', 'done', 'error', 'cancelled','approved'));

-- добавляем пользователя и время одобрения журнала
ALTER TABLE forecast_journal ADD COLUMN user_approved_id uuid NULL;	

ALTER TABLE forecast_journal 
	ADD CONSTRAINT fk__forecast_journal__users__user_approved_id__id 
		FOREIGN KEY (user_approved_id) 
		REFERENCES users(id);

ALTER TABLE forecast_journal ADD COLUMN approved_time TIMESTAMP NULL;	

--довавляем полу bool, что создана заяка для результата
ALTER TABLE forecast_results ADD COLUMN is_request_created boolean default FALSE;	
