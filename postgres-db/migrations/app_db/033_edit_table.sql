-- Роли
CREATE TABLE roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE -- 'Название роли'
);


-- Добавить роли
--		'Название роли',	
INSERT INTO roles 	(name)
	   VALUES		('Admins'),
					('Dispetchers_ODS'),
					('Dispetchers_rayon'),
					('Technics');
	   
-- Пользователю добавил роль	   

ALTER TABLE users ADD COLUMN role_id uuid ;


ALTER TABLE users 
ADD CONSTRAINT fk__users__roles__role_id__id 
	FOREIGN KEY (role_id) 
	REFERENCES roles(id); -- 'ID роли',
	
-- 1 Объект для заявки в несколько
ALTER TABLE requests ADD COLUMN dispatcher_objects_id json ;	
ALTER TABLE requests DROP COLUMN dispatcher_object_id;	

