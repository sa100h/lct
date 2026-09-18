# ad — Samba AD Domain Controller

Каталог контроллера домена Samba (база `nowsci/samba-domain`). Нужен для аутентификации
пользователей по LDAP/LDAPS: диспетчеры, техники и администраторы логинятся в приложение
по учёткам домена `lct.ru`.

## Что делает `ad/custom.sh` (оркестратор запуска)

По шагам (всё видно в `docker logs lct-ad-1`):

1. Запускает штатный `init.sh` из образа в фоне (провижининг домена → supervisord).
2. Ждёт, пока Samba ответит по LDAP (`ldapsearch` по порту 389, до 5 мин).
3. Ждёт появления `smb.conf`.
4. Проверяет TLS-сертификаты в `/var/lib/samba/private/tls` — при отсутствии
   генерирует самоподписанные (`CN=dc1.lct.ru`, 10 лет).
5. Вписывает в `[global]` секцию `smb.conf` параметры TLS
   (`tls enabled/certfile/keyfile/cafile`) — один раз, с резервной копией `.bak`.
6. Перезапускает Samba и проверяет, что LDAPS (порт 636) слушается.
7. **Блокирует открытый LDAP**: `iptables -A INPUT -p tcp --dport 389 -j DROP` —
   клиенты должны ходить только по LDAPS.
8. При первом старте выполняет `ad/init/01-users-groups.sh` (создание пользователей;
   повторный запуск пропускается по наличию `technik.test`).
9. Удерживает процесс живым (`wait` на `init.sh`).

## Что создаёт `ad/init/01-users-groups.sh`

| Тип | Имя | Группа |
|-----|-----|--------|
| user | `admin.test` | `Admins` |
| user | `technik.test` | `Technics` |
| user | `dispetcher_ods` | `Dispetchers_ODS` |
| user | `dispetcher_rayon` | `Dispetchers_rayon` |

OU: `Users`, `Groups`, `ServiceAccounts`. Пароли пользователей хардкожены в скрипте
(демо-стенд) — при деплое заменить на реальные значения.

## Настройки (`.env`)

| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|------------|
| `DOMAIN` | `lct.ru` | Доменное имя AD-домена |
| `DOMAINPASS` | `ChangeMeNow!2024` | Пароль `Administrator` домена (политика сложности Samba) |
| `HOSTIP` | `172.18.0.3` | IP хоста Docker для DNS-записей |
| `DNSFORWARDER` | `127.0.0.11` | Форвардер DNS (embedded DNS Docker) |
| `JOIN` | `false` | `false` — создать новый домен, `true` — присоединиться к существующему |

## Порты

| Порт | Протокол | Назначение |
|------|----------|------------|
| 53 | tcp+udp | DNS домена |
| 389 | tcp | LDAP (заблокирован извне iptables, только локально) |
| 636 | tcp | LDAPS — основной протокол клиентов |
| 88 | tcp+udp | Kerberos |

## Экземпляр / storage

Объём `ad_data` хранит состояние домена, `ad_config` — конфиги, которые надо
перевыпускать вручную. После `docker compose down -v` домен будет провижинен заново.

## Локальный запуск

```bash
docker compose up -d ad
docker logs -f lct-ad-1          # следим за оркестрацией
ldapsearch -x -H ldaps://<host> -b "dc=lct,dc=ru" -ZZ
```
