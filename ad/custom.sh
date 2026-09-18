#!/bin/bash
set -x

# 1. Запускаем init.sh в фоне.
#    Он выполнит провижининг домена и в конце сделает exec supervisord,
#    но уже в дочернем процессе, а не заменит наш custom.sh.
echo "Запуск init.sh в фоне..."
/init.sh &
INIT_PID=$!

# 5. Ждём, пока Samba будет готова отвечать по LDAP.
echo "Ожидание готовности Samba..."
READY=0
for i in $(seq 1 60); do
  if ldapsearch -x -H ldap://localhost:389 -b "" -s base >/dev/null 2>&1; then
    echo "Samba готова (попытка $i)"
    READY=1
    break
  fi
  sleep 5
done

if [ "$READY" -ne 1 ]; then
  echo "ОШИБКА: Samba не запустилась за отведённое время"
  exit 1
fi

# 2. Ждём появления smb.conf (создаётся во время провижининга).
echo "Ожидание создания smb.conf..."
SMB_CONF=""
for i in $(seq 1 90); do
#   if [ -f /etc/samba/external/smb.conf ]; then
#     SMB_CONF=/etc/samba/external/smb.conf
#     break
#   fi
  if [ -f /etc/samba/smb.conf ]; then
    SMB_CONF=/etc/samba/smb.conf
    break
  fi
  sleep 2
done

if [ -z "$SMB_CONF" ]; then
  echo "ОШИБКА: smb.conf не найден за отведённое время"
  exit 1
fi
echo "Найден smb.conf: $SMB_CONF"

#sleep 30

# 3. Убеждаемся, что в Samba есть TLS-сертификаты.
#    Samba генерирует их при провижининге, но на всякий случай проверим.
TLS_DIR="/var/lib/samba/private/tls"
mkdir -p "$TLS_DIR"
if [ ! -f "$TLS_DIR/key.pem" ] || [ ! -f "$TLS_DIR/cert.pem" ]; then
  echo "Сертификаты Samba не найдены — генерируем самоподписанные..."
  FQDN="dc1.lct.ru"   # ЗАМЕНИТЕ на FQDN вашего контроллера домена
  openssl req -newkey rsa:2048 -keyout "$TLS_DIR/key.pem" -nodes \
    -x509 -days 3650 -out "$TLS_DIR/cert.pem" \
    -subj "/CN=${FQDN}" 2>/dev/null
  cp "$TLS_DIR/cert.pem" "$TLS_DIR/ca.pem"
  chmod 600 "$TLS_DIR/key.pem"
  chmod 644 "$TLS_DIR/cert.pem" "$TLS_DIR/ca.pem"
fi

# 4. Добавляем TLS-параметры в smb.conf, если их ещё нет.
TLS_DIR="/var/lib/samba/private/tls"

python3 - "$SMB_CONF" "$TLS_DIR" <<'PYEOF'
import re
import sys

smb_conf = sys.argv[1]
tls_dir = sys.argv[2]

# --- Резервная копия ---
import shutil, os
backup = smb_conf + ".bak"
if not os.path.exists(backup):
    shutil.copy2(smb_conf, backup)
    print(f"Создана резервная копия: {backup}")

# --- Читаем файл ---
with open(smb_conf, "r", encoding="utf-8") as f:
    content = f.read()

# --- Проверяем, не добавлены ли уже TLS-параметры ---
if re.search(r'^\s*tls enabled\s*=', content, flags=re.MULTILINE):
    print("TLS-параметры уже присутствуют в smb.conf — пропускаем")
    sys.exit(0)

# --- Формируем блок TLS ---
tls_block = (
    "    tls enabled = yes\n"
    "    tls keyfile = tls/key.pem\n"
    "    tls certfile = tls/cert.pem\n"
    "    tls cafile = tls/ca.pem\n"
)

# --- Ищем секцию [global] ---
m = re.search(r'^\[global\]\s*$', content, flags=re.MULTILINE)
if m:
    insert_pos = m.end()
    # Если сразу после [global] нет \n — добавим
    if insert_pos < len(content) and content[insert_pos] != "\n":
        insert_pos += 1
    else:
        insert_pos += 1
    new_content = content[:insert_pos] + "\n" + tls_block + content[insert_pos:]
else:
    # Секции [global] нет — дописываем в конец
    new_content = content.rstrip() + "\n\n[global]\n" + tls_block

# --- Записываем обратно ---
with open(smb_conf, "w", encoding="utf-8") as f:
    f.write(new_content)
print(f"TLS-параметры добавлены в {smb_conf}")
PYEOF

# 6. Перезапускаем Samba, чтобы она подхватила smb.conf с TLS.
echo "Перезапуск Samba для применения TLS..."
supervisorctl restart samba || true
sleep 8

# 7. Проверяем, что порт 636 слушается.
if netstat -tlnp 2>/dev/null | grep -q ":636"; then
  echo "OK: LDAPS порт 636 слушается"
else
  echo "WARNING: порт 636 не слушается — проверьте smb.conf и сертификаты"
fi

iptables -A INPUT -p tcp --dport 389 -j DROP

# 8. Выполняем скрипт создания пользователей.
#    Вывод пишем и в stdout, и в файл, чтобы было видно в docker logs.
# Запускаем скрипт только если в домене ещё нет пользователя technik.test
if ! samba-tool user show technik.test >/dev/null 2>&1; then
  echo "Первый запуск — создаём пользователей..."
  /usr/local/bin/01-users-groups.sh 2>&1 | tee /user.log
else
  echo "Пользователи уже существуют — пропускаем создание"
fi

# 9. Ждём завершения init.sh (в нём работает supervisord и samba).
wait $INIT_PID