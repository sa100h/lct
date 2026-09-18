#!/bin/bash
set -e

: "${AD_BIND_PASSWORD:?AD_BIND_PASSWORD must be set for the read-only service account}"

echo "Ожидание готовности Samba AD DC..."
sleep 20

# Создание организационных подразделений (OU)
samba-tool ou create "OU=Users" || true
samba-tool ou create "OU=Groups" || true
samba-tool ou create "OU=ServiceAccounts" || true

# Создание групп
samba-tool group add "Admins" --groupou="OU=Groups" || true
samba-tool group add "Dispetchers_ODS" --groupou="OU=Groups" || true
samba-tool group add "Dispetchers_rayon" --groupou="OU=Groups" || true
samba-tool group add "Technics" --groupou="OU=Groups" || true

# Создание сервисной учётной записи для чтения состояния и групп пользователей.
# Не добавляем её в привилегированные группы.
if ! samba-tool user show lct-app-bind >/dev/null 2>&1; then
  samba-tool user create lct-app-bind "$AD_BIND_PASSWORD" --userou="OU=ServiceAccounts"
fi

# Создание пользователей
if ! samba-tool user show admin.test >/dev/null 2>&1; then
  samba-tool user create admin.test "Adm1n-test-2026" \
    --userou="OU=Users" --mail-address="admin.test@lct.ru"
fi

if ! samba-tool user show technik.test >/dev/null 2>&1; then
  samba-tool user create technik.test "Tech1-2026" \
    --userou="OU=Users" --mail-address="technik.test@lct.ru"
fi

if ! samba-tool user show dispetcher_ods >/dev/null 2>&1; then
  samba-tool user create dispetcher_ods "D1sp-2026" \
    --userou="OU=Users" --mail-address="dispetcher_ods@lct.ru"
fi

if ! samba-tool user show dispetcher_rayon >/dev/null 2>&1; then
  samba-tool user create dispetcher_rayon "D1sp-ray-2026" \
    --userou="OU=Users" --mail-address="dispetcher_rayon@lct.ru"
fi

# Добавление пользователей в группы
ensure_member() {
  local group="$1"
  local user="$2"
  if ! samba-tool group listmembers "$group" | grep -Fxq "$user"; then
    samba-tool group addmembers "$group" "$user"
  fi
}

ensure_member "Admins" admin.test
ensure_member "Dispetchers_ODS" dispetcher_ods
ensure_member "Dispetchers_rayon" dispetcher_rayon
ensure_member "Technics" technik.test

echo "Пользователи и группы успешно созданы"
