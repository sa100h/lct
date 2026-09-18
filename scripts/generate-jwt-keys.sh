#!/usr/bin/env bash
set -euo pipefail

output_directory="${1:-.keys}"
resolved="$(mkdir -p "$output_directory" && cd "$output_directory" && pwd)"
private="$resolved/jwt-private.pem"
public="$resolved/jwt-public.pem"

if [[ -e "$private" || -e "$public" ]]; then
  echo "JWT keys already exist in $resolved; refusing to overwrite them." >&2
  exit 1
fi

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$private"
openssl pkey -in "$private" -pubout -out "$public"
echo "Generated JWT keys in $resolved"
