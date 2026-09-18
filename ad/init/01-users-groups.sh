#!/bin/bash
set -e

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

# Создание пользователей
samba-tool user create admin.test "Adm1n-test-2026" \
  --userou="OU=Users" \
  --mail-address="admin.test@lct.ru" || true

samba-tool user create technik.test "Tech1-2026" \
  --userou="OU=Users" \
  --mail-address="technik.test@lct.ru" || true

samba-tool user create dispetcher_ods "D1sp-2026" \
  --userou="OU=Users" \
  --mail-address="dispetcher_ods@lct.ru" || true

samba-tool user create dispetcher_rayon "D1sp-ray-2026" \
  --userou="OU=Users" \
  --mail-address="dispetcher_rayon@lct.ru" || true

# Добавление пользователей в группы
samba-tool group addmembers "Admins" admin.test
samba-tool group addmembers "Dispetchers_ODS" dispetcher_ods
samba-tool group addmembers "Dispetchers_rayon" dispetcher_rayon
samba-tool group addmembers "Technics" technik.test

echo "Пользователи и группы успешно созданы"
