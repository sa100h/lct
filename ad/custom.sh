#!/bin/bash
set -e

: "${AD_BIND_PASSWORD:?AD_BIND_PASSWORD must be set}"
: "${AD_TLS_HOSTNAME:=dc1.lct.ru}"

# 1. Запускаем init.sh в фоне.
#    Он выполнит провижининг домена и запустит supervisord в дочернем процессе.
echo "Запуск init.sh в фоне..."
/init.sh &
INIT_PID=$!

# 2. Ждём, пока Samba будет готова отвечать по LDAP.
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

# 3. Ждём появления smb.conf (создаётся во время провижининга).
echo "Ожидание создания smb.conf..."
SMB_CONF=""
for i in $(seq 1 90); do
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

# 4. Проверяем самоподписанный сертификат с DNS-именем в SAN.
#    При необходимости выпускаем новый. Приватный ключ остаётся в томе Samba;
#    в общий том для app-service передаём только публичный сертификат.
TLS_DIR="/var/lib/samba/private/tls"
mkdir -p "$TLS_DIR"
if [ ! -f "$TLS_DIR/key.pem" ] || [ ! -f "$TLS_DIR/cert.pem" ] ||
   ! openssl x509 -in "$TLS_DIR/cert.pem" -noout -checkend 86400 >/dev/null 2>&1 ||
   ! openssl x509 -in "$TLS_DIR/cert.pem" -noout -ext subjectAltName 2>/dev/null | grep -Fq "DNS:${AD_TLS_HOSTNAME}"; then
  echo "Создаём самоподписанный LDAPS-сертификат для ${AD_TLS_HOSTNAME}..."
  openssl req -newkey rsa:3072 -keyout "$TLS_DIR/key.pem" -nodes \
    -x509 -sha256 -days 365 -out "$TLS_DIR/cert.pem" \
    -subj "/CN=${AD_TLS_HOSTNAME}" \
    -addext "subjectAltName=DNS:${AD_TLS_HOSTNAME}" \
    -addext "extendedKeyUsage=serverAuth" \
    -addext "keyUsage=digitalSignature,keyEncipherment" \
    -addext "basicConstraints=critical,CA:FALSE" >/dev/null 2>&1
  cp "$TLS_DIR/cert.pem" "$TLS_DIR/ca.pem"
  chmod 600 "$TLS_DIR/key.pem"
  chmod 644 "$TLS_DIR/cert.pem" "$TLS_DIR/ca.pem"
fi
cp "$TLS_DIR/cert.pem" "$TLS_DIR/ca.pem"
mkdir -p /ad-public-certificates
cp "$TLS_DIR/cert.pem" /ad-public-certificates/ldaps.pem
chmod 644 /ad-public-certificates/ldaps.pem

# 5. Обновляем TLS-параметры в smb.conf при каждом запуске.

python3 - "$SMB_CONF" <<'PYEOF'
import re
import sys

smb_conf = sys.argv[1]

# --- Резервная копия ---
import shutil, os
backup = smb_conf + ".bak"
if not os.path.exists(backup):
    shutil.copy2(smb_conf, backup)
    print(f"Создана резервная копия: {backup}")

# --- Читаем файл ---
with open(smb_conf, "r", encoding="utf-8") as f:
    content = f.read()

# --- Удаляем прежние TLS-параметры, включая относительные пути из старой версии ---
content = re.sub(
    r'^[ \t]*(?:tls (?:enabled|keyfile|certfile|cafile)|ldap server require strong auth)[ \t]*=.*\n?',
    '', content, flags=re.MULTILINE)

# --- Формируем блок TLS ---
tls_block = (
    "    tls enabled = yes\n"
    "    tls keyfile = /var/lib/samba/private/tls/key.pem\n"
    "    tls certfile = /var/lib/samba/private/tls/cert.pem\n"
    "    tls cafile = /var/lib/samba/private/tls/ca.pem\n"
    "    ldap server require strong auth = yes\n"
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

# 6. Перезапускаем Samba, чтобы она применила сертификат и настройки TLS.
echo "Перезапуск Samba для применения TLS..."
supervisorctl restart samba || true
sleep 8

# 7. Проверяем LDAPS-соединение, сертификат и имя сервера.
LDAPS_READY=0
for i in $(seq 1 20); do
  if openssl s_client -brief -connect 127.0.0.1:636 \
      -servername "$AD_TLS_HOSTNAME" \
      -CAfile /ad-public-certificates/ldaps.pem \
      -verify_hostname "$AD_TLS_HOSTNAME" -verify_return_error \
      </dev/null >/dev/null 2>&1; then
    LDAPS_READY=1
    break
  fi
  sleep 2
done
if [ "$LDAPS_READY" -ne 1 ]; then
  echo "ОШИБКА: LDAPS не прошёл проверку сертификата и имени сервера"
  exit 1
fi
echo "OK: LDAPS сертификат и имя сервера проверены"

# 8. Создаём недостающие учётные записи и группы.
#    Вывод пишем в docker logs и /user.log. Скрипт проверяет каждую запись,
#    поэтому сервисную учётную запись можно добавить без удаления тома AD.
/usr/local/bin/01-users-groups.sh 2>&1 | tee /user.log

# 9. Ждём завершения init.sh (в нём работает supervisord и Samba).
wait $INIT_PID
