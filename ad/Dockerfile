# Используем официальный образ как базу
FROM nowsci/samba-domain:latest

COPY ad/custom.sh /custom.sh
# Копируем наш скрипт инициализации в директорию
COPY ad/init/01-users-groups.sh /usr/local/bin/01-users-groups.sh

# Убеждаемся, что скрипт исполняемый
RUN chmod +x /custom.sh /usr/local/bin/01-users-groups.sh

# Переопределяем точку входа
ENTRYPOINT ["/custom.sh"]