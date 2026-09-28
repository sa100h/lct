#!/usr/bin/env bash
#
# check-forecast.sh — единый чек: сработал ли прогноз (forecast_journal)
# честно и без ошибок в ml-broker + ml-service.
#
# Проверяет по journal (forecast_journal.id):
#   1) ml-service:  GET /healthz, GET /status (все 4 модели trained)
#   2) ml-broker:   GET /healthz, GET /stats (status=running, notifier_connected=true)
#   3) forecast_journal: status=done, end_composition_time, не cancelled
#   4) ml_predict_queue: все строки journal = done (0 failed, 0 pending/running)
#   5) result: валидный Prediction — risk_score/probability in [0,1],
#      predicted_label bool, model_version non-empty, category совпадает
#   6) forecast_results: ровно 1 строка на каждый dispatcher_object_id,
#      is_erroneous=false, is_cancelled=false
#   7) покрытие: каналы (subject_id) из queue == каналы из forecast_description
#   8) реплей (опц.): независимый POST /predict по данным из queue
#
# Использование:
#   PGPASSWORD='...' \
#   DB_DSN='postgresql://app_service:***@127.0.0.1:5432/app_db' \
#   ML_URL='http://127.0.0.1:8000' \
#   BROKER_URL='http://127.0.0.1:8080' \
#   ./check-forecast.sh <journal_id>
#
# journal_id можно опустить — проверяется последний forecast_journal.
# SKIP_REPLAY=1 ./check-forecast.sh <id> — без реплейного POST /predict.
# CHECK_MAX_MINUTES=N — warn если цикл > N минут (default 60).
#
# Выход: 0 = OK · 1 = WARN · 2 = FAIL · 3 = окружение / БД / journal не найден
set -uo pipefail

JOURNAL_ID="${1:-}"
DB_DSN="${DB_DSN:-postgresql://app_service:***@127.0.0.1:5432/app_db}"
PGPASSWORD="${PGPASSWORD:-}"
ML_URL="${ML_URL%/}"
BROKER_URL="${BROKER_URL%/}"
SKIP_REPLAY="${SKIP_REPLAY:-0}"
CHECK_MAX_MINUTES="${CHECK_MAX_MINUTES:-60}"

# --------------------------- вывод -----------------------------------------
RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YEL=$'\033[1;33m'; BLD=$'\033[1;34m'; NC=$'\033[0m'
FAILS=(); WARNS=()
ok()  { printf '%s[OK]   %s\n' "$GREEN" "$1"; }
warn(){ printf '%s[WARN] %s\n' "$YEL"  "$1"; WARNS+=("$1"); }
fail(){ printf '%s[FAIL] %s\n' "$RED"  "$1"; FAILS+=("$1"); }
blit(){ printf '%s %s\n' "$BLD" "$1"; }
sec(){  printf '\n%s---- %s\n' "$BLD" "$1"; }

# --------------------------- helpers ----------------------------------------
# SQL через psql: -tA tab-separated, без headers, без prompts, stdout -> stdout
sql() {
  PGPASSWORD="${PGPASSWORD:-}" psql -w -q -tA -v ON_ERROR_STOP=1 \
      -c "$1" "$DB_DSN" 2>/dev/null
}
sql_int() {
  local res
  res="$(sql "SELECT COALESCE(($1), 0)::int; ")"
  [[ "$res" =~ ^[0-9]+$ ]] || res="0"
  printf '%s' "$res"
}

# GET url -> HTTP_CODE, HTTP_BODY
http_get() {
  local url=$1 tmp
  tmp="$(mktemp -p 2>/dev/null || mktemp)"
  if command -v curl >/dev/null 2>&1; then
    HTTP_CODE="$(curl -sS -m 10 -o "$tmp" -w '%{http_code}' "$url" 2>/dev/null || true)"
  else
    HTTP_CODE=""
  fi
  HTTP_BODY="$(cat "$tmp" 2>/dev/null || true)"
  rm -f "$tmp"
  HTTP_CODE="${HTTP_CODE:-0}"
}
# POST url json-body -> HTTP_CODE, HTTP_BODY
http_post() {
  local url=$1 body_json=$2 tmp
  tmp="$(mktemp -p 2>/dev/null || mktemp)"
  if command -v curl >/dev/null 2>&1; then
    HTTP_CODE="$(curl -sS -m 60 -o "$tmp" -w '%{http_code}' \
        -X POST -H 'Content-Type: application/json' --data-binary "$body_json" "$url" 2>/dev/null || true)"
  else
    HTTP_CODE=""
  fi
  HTTP_BODY="$(cat "$tmp" 2>/dev/null || true)"
  rm -f "$tmp"
  HTTP_CODE="${HTTP_CODE:-0}"
}
# jsonv <json_body> <dotted.path> -> значение (json.dumps для dict/list, null)
jsonv() {
  python3 - "$1" "$2" <<'PY'
import json, sys
body, path = sys.argv[1], sys.argv[2]
try:
    d = json.loads(body)
except Exception:
    d = None
v = d
for k in path.split('.'):
    if isinstance(v, dict):
        v = v.get(k)
    else:
        v = None
if v is None:
    print('null')
elif isinstance(v, (dict, list)):
    print(json.dumps(v))
else:
    print(v)
PY
}

# --------------------------- предполётный осмотр ---------------------------
command -v psql >/dev/null 2>&1 || {
  printf '%s[FAIL] нужен psql — поставь postgresql-client\n' "$RED"
  exit 3
}
if ! command -v curl >/dev/null 2>&1; then
  warn "нет curl — HTTP-проверки пропущены"
fi

printf '%s============================================================\n' "$BLD"
printf '%s  check-forecast · LCT ml-broker + ml-service\n' "$BLD"
printf '%s============================================================\n' "$BLD"
blit "БД:      $DB_DSN (PGPASSWORD: $([ -n "$PGPASSWORD" ] && echo 'задан' || echo 'не задан'))"
blit "ml-svc:  $ML_URL"
blit "broker:  $BROKER_URL"

# --------------------------- 1. ml-service ----------------------------------
sec "1) ml-service — жив и готов"
if command -v curl >/dev/null 2>&1; then
  http_get "$ML_URL/healthz"
  if [[ "$HTTP_CODE" == "200" ]] && printf '%s' "$HTTP_BODY" | grep -q 'ok'; then
    ok "GET $ML_URL/healthz -> 200 {\"status\":\"ok\"}"
  else
    fail "GET $ML_URL/healthz -> HTTP ${HTTP_CODE} (ожидается 200 ok)"
  fi

  http_get "$ML_URL/status"
  if [[ "$HTTP_CODE" == "200" ]]; then
    trained=$(printf '%s' "$HTTP_BODY" | python3 -c '
import json,sys
try:
    d=json.loads(sys.stdin.read())
    m=d.get("models") or {}
    t=sum(1 for s in m.values() if isinstance(s,dict) and s.get("state")=="trained")
    print("%d/%d" % (t,len(m)))
except Exception:
    print("0/0")')
    missing=$(printf '%s' "$HTTP_BODY" | python3 -c '
import json,sys
try:
    d=json.loads(sys.stdin.read())
    m=d.get("models") or {}
    bad=[k for k,v in m.items() if not (isinstance(v,dict) and s.get("state")=="trained")] if False else [k for k,v in m.items() if not (isinstance(v,dict) and v.get("state")=="trained")]
    print(",".join(bad) if bad else "")
except Exception:
    print("")')
    if [[ "$trained" == "4/4" ]]; then
      ok "/status: все 4 модели trained"
    else
      if [ -n "$missing" ]; then
        warn "/status: моделей trained $trained; NOT trained: $missing (predict по ним упадёт / NaN-lags)"
      else
        warn "/status: trained $trained (ожидается 4/4)"
      fi
    fi
  else
    fail "GET $ML_URL/status -> HTTP ${HTTP_CODE}"
  fi
else
  fail "нет curl — healthz/ml-service не проверяется"
fi

# --------------------------- 2. ml-broker ------------------------------------
sec "2) ml-broker — жив и слушает NOTIFY"
if command -v curl >/dev/null 2>&1; then
  http_get "$BROKER_URL/healthz"
  if [[ "$HTTP_CODE" == "200" ]] && printf '%s' "$HTTP_BODY" | grep -q 'ok'; then
    ok "GET $BROKER_URL/healthz -> 200"
  else
    fail "GET $BROKER_URL/healthz -> HTTP ${HTTP_CODE}"
  fi

  http_get "$BROKER_URL/stats"
  if [[ "$HTTP_CODE" == "200" ]]; then
    stats_status=$(jsonv "$HTTP_BODY" 'status')
    stats_notif=$(jsonv "$HTTP_BODY" 'notifier_connected')
    stats_recon=$(jsonv "$HTTP_BODY" 'notifier_reconnects')
    stats_done=$(jsonv "$HTTP_BODY" 'queue.done')
    stats_failed=$(jsonv "$HTTP_BODY" 'queue.failed')
    stats_retried=$(jsonv "$HTTP_BODY" 'queue.retried')
    blit "   broker stats: status=$stats_status queue{done=${stats_done:-?}, failed=${stats_failed:-?}, retried=${stats_retried:-?}} notifier=$stats_notif reconnects=$stats_recon"
    if [[ "$stats_status" == "running" ]]; then
      ok "status=running"
    else
      warn "status=$stats_status (ожидается running — брокер не в работе?)"
    fi
    if [[ "$stats_notif" == "true" ]]; then
      ok "notifier_connected=true (LISTEN lct_ml_forecast жив)"
    else
      warn "notifier_connected=false — NOTIFY не прослушивается; данные не теряются (polling backstop), latency = POLL_SECONDS (~5 c)"
    fi
  else
    fail "GET $BROKER_URL/stats -> HTTP ${HTTP_CODE}"
  fi
fi

# --------------------------- 3. БД: подключение + sanity --------------------
sec "3) БД: подключение + required schema"
if PGPASSWORD="${PGPASSWORD:-}" psql -w -q -tA -v ON_ERROR_STOP=1 -c "SELECT 1;" "$DB_DSN" >/dev/null 2>&1; then
  ok "подключение установлено"
else
  fail "подключение к $DB_DSN не удалось — проверь DB_DSN / PGPASSWORD / доступ app_service"
  exit 3
fi

tables_ok=$(sql "SELECT count(*) FROM information_schema.tables
  WHERE table_schema='public' AND table_name IN
    ('forecast_journal','ml_predict_queue','forecast_results','sensor_channels')")
tables_ok=${tables_ok:-0}
if [[ "$tables_ok" -eq 4 ]]; then
  ok "required tables: 4/4 (forecast_journal, ml_predict_queue, forecast_results, sensor_channels)"
else
  fail "required tables: $tables_ok/4 — часть schema отсутствует"
fi
user_ok=$(sql "SELECT count(*) FROM pg_users WHERE usename='app_service' OR usename='ml_broker'")
if [[ "${user_ok:-0}" -ge 1 ]]; then
  ok "service user found (app_service / ml_broker)"
else
  warn "service user not found (app_service / ml_broker)"
fi
trg_ok=$(sql "SELECT count(*) FROM pg_trigger WHERE tgname='trg_forecast_journal_notify'")
if [[ "${trg_ok:-0}" -ge 1 ]]; then
  ok "trigger trg_forecast_journal_notify active (NOTIFY fires immediately on INSERT)"
else
  warn "trigger trg_forecast_journal_notify missing — broker relies on polling (latency ~ POLL_SECONDS)"
fi

# --------------------------- 4. forecast_journal ------------------------------
sec "4) forecast_journal"
if [[ -z "$JOURNAL_ID" ]]; then
  JOURNAL_ID=$(sql "SELECT id FROM forecast_journal ORDER BY creation_time DESC LIMIT 1;")
  if [[ -z "$JOURNAL_ID" ]]; then
    fail "forecast_journal empty — no journals"
    exit 3
  else
    warn "journal id not passed — checking latest: $JOURNAL_ID"
  fi
fi

jrow=$(sql "SELECT status, run_type, is_cancelled,
      to_char(creation_time,'YYYY-MM-DD HH24:MI:SS'),
      to_char(start_composition_time,'YYYY-MM-DD HH24:MI:SS'),
      to_char(end_composition_time,'YYYY-MM-DD HH24:MI:SS')
  FROM forecast_journal WHERE id='$JOURNAL_ID'::uuid;")

if [[ -z "$jrow" ]]; then
  fail "journal '$JOURNAL_ID' not found in forecast_journal"
  exit 3
fi
IFS=$'\t' read -r jstatus jrun jcanl jcreate jstart jend <<< "$jrow"

printf '   journal id=%s  run_type=%s  created=%s  start=%s  end=%s  cancelled=%s\n' \
       "$JOURNAL_ID" "$jrun" "$jcreate" "$jstart" "$jend" "$jcanl"

case "$jstatus" in
  done)        ok "journal.status=done (end=$jend)" ;;
  cancelled)   fail "journal.status=cancelled" ;;
  error)       fail "journal.status=error — fan-out or processing failed" ;;
  running)     warn "journal.status=running — broker still processing; re-run after ~POLL_SECONDS" ;;
  pending)     warn "journal.status=pending — broker has not picked it up yet (check notifier/polling)" ;;
  *)           fail "journal.status='$jstatus' (unexpected; expected pending|running|done|error|cancelled)" ;;
esac

if [[ "$jstatus" == "done" ]]; then
  dur_epoch=$(sql "SELECT floor(extract(epoch from (end_composition_time - creation_time)))::int
                   FROM forecast_journal WHERE id='$JOURNAL_ID'::uuid;")
  dur_epoch=${dur_epoch:-0}
  if [[ "$dur_epoch" =~ ^[0-9]+$ ]]; then
    dur_min=$(( dur_epoch / 60 ))
    dur_sec=$(( dur_epoch % 60 ))
    blit "   cycle creation->end: ${dur_min} m ${dur_sec} s"
    if (( dur_min > CHECK_MAX_MINUTES )); then
      warn "cycle > $CHECK_MAX_MINUTES min — possible ml-service bottleneck"
    fi
  fi
fi

# --------------------------- 5. ml_predict_queue ------------------------------
sec "5) ml_predict_queue — rows for this journal"
totalq=$(sql_int "SELECT count(*) FROM ml_predict_queue WHERE forecast_journal_id='$JOURNAL_ID'::uuid")
doneq2=$(sql_int "SELECT count(*) FROM ml_predict_queue WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='done'")
failedq2=$(sql_int "SELECT count(*) FROM ml_predict_queue WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='failed'")
openq2=$(sql_int "SELECT count(*) FROM ml_predict_queue WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status IN ('pending','running')")
ret2=$(sql_int "SELECT count(*) FROM ml_predict_queue WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='done' AND attempts>1")
dupc=$(sql_int "SELECT count(*) FROM (SELECT subject_id, category, as_of FROM ml_predict_queue WHERE forecast_journal_id='$JOURNAL_ID'::uuid GROUP BY 1,2,3 HAVING count(*)>1) x")

if [[ "${totalq:-0}" -eq 0 ]]; then
  fail "rows in ml_predict_queue: 0 — forecast_channels empty or all channels unknown"
else
  printf '   total=%s done=%s failed=%s open(pending/running)=%s dedup_dups=%s\n' \
         "$totalq" "${doneq2:-0}" "${failedq2:-0}" "${openq2:-0}" "${dupc:-0}"
  if [[ "${failedq2:-0}" -gt 0 ]]; then
    fail "failed rows: $failedq2"
    sql "SELECT id, subject_id, category, attempts, substring(coalesce(error,''),'',200)
         FROM ml_predict_queue
         WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='failed'
         ORDER BY id LIMIT 5;" | while IFS=$'\t' read -r rid rs rcat rat errs; do
      [[ -z "$errs" || "$errs" == "null" ]] && errs="(no error set)"
      blit "     failed row $rid: cat=$rcat attempts=$rat err=$errs"
    done
  fi
  if [[ "${openq2:-0}" -gt 0 ]]; then
    fail "open rows (pending/running): $openq2 — journal finished but broker didn't process them (orphaned)"
  fi
  if [[ "${doneq2:-0}" -eq "${totalq:-0}" ]]; then
    ok "all $totalq queue rows = done (dedup dups=$dupc)"
    if [[ "${ret2:-0}" -gt 0 ]]; then
      pct=$(( ret2 * 100 / totalq ))
      blit "   retries (attempts>1): $ret2 (${pct}%) — acceptable; >5% suggests ml-service instability"
      if (( pct > 5 )); then
        warn "retry ratio ${pct}% > 5% — ml-service unstable during the cycle"
      fi
    fi
  else
    fail "$doneq2/$totalq done — not all rows processed"
  fi
fi
doneq_final=${doneq2:-0}

# --------------------------- 6. result — valid Prediction (Python) ------------
sec "6) result — valid Prediction JSON (checked in Python)"
if [[ "${doneq_final:-0}" -gt 0 ]]; then
  # Fetch all done rows as a single jsonb array (safe for multi-line JSON fields).
  results_json=$(sql "SELECT json_agg(jsonb_build_object(
    'id', id::text,
    'category', category,
    'attempts', attempts,
    'result', result
  ))
  FROM ml_predict_queue
  WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='done';")

  out="$(printf '%s' "${results_json:-[]}" | python3 - <<'PY'
import json, sys
raw = sys.stdin.read()
try:
    arr = json.loads(raw) if raw.strip() else []
except Exception:
    arr = []
bad = 0
stubs = 0
scored = 0
lines = []
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)
for r in arr:
    res = r.get('result')
    # Stub row: channel outside the category's training set -> result
    # {"applicable": false, ...}; in forecast_description it becomes
    # status_code="unpredictable". Valid without risk_score.
    if isinstance(res, dict) and res.get('applicable') is False:
        stubs += 1
        continue
    problems = []
    scored += 1
    if not isinstance(res, dict):
        problems.append('result is not a JSON object')
    else:
        rs = res.get('risk_score')
        pr = res.get('probability')
        pl = res.get('predicted_label')
        mv = res.get('model_version')
        if not (_num(rs) and 0 <= rs <= 1):
            problems.append('risk_score out-of-range/missing (must be 0..1 number)')
        if not (_num(pr) and 0 <= pr <= 1):
            problems.append('probability out-of-range/missing (must be 0..1 number)')
        if not isinstance(pl, bool):
            problems.append('predicted_label not bool')
        if not (isinstance(mv, str) and mv.strip()):
            problems.append('model_version missing/empty')
        cat = res.get('category')
        if cat is not None and cat != r.get('category'):
            problems.append("category mismatch (queue=%s, result=%s)" % (r.get('category'), cat))
    if problems:
        bad += 1
        if len(lines) < 5:
            lines.append('BAD %s cat=%s | %s' % (r.get('id'), r.get('category'), '; '.join(problems)))
print(bad)
print("stubs=%d scored=%d" % (stubs, scored))
for l in lines:
    print(l)
PY
)"
  badcnt=$(printf '%s\n' "$out" | head -n1)
  [[ "$badcnt" =~ ^[0-9]+$ ]] || badcnt=0
  stubinfo=$(printf '%s\n' "$out" | sed -n '2p')
  stubs=${stubinfo#stubs=}; stubs=${stubs%% *}
  scored=${stubinfo##*scored=}
  if [[ "${stubs:-0}" -gt 0 ]]; then
    warn "unpredictable stub rows (applicable=false -> status_code=unpredictable in description): $stubs"
  fi
  if [[ "${badcnt:-0}" -eq 0 ]]; then
    ok "scored rows valid: $scored (risk_score/probability in [0,1], predicted_label bool, model_version non-empty); stubs: ${stubs:-0}"
  else
    fail "invalid result rows: $badcnt"
    printf '%s\n' "$out" | tail -n +3 | while IFS= read -r line; do
      [[ -n "$line" ]] && blit "     $line"
    done
  fi
else
  blit "   (skip: no done rows in queue)"
fi

# --------------------------- 7. forecast_results -----------------------------
sec "7) forecast_results — one row per object"
if [[ "${doneq_final:-0}" -gt 0 ]]; then
  expected_obj=$(sql_int "SELECT count(DISTINCT dispatcher_object_id)
      FROM ml_predict_queue
      WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='done'
        AND dispatcher_object_id IS NOT NULL")
  have_obj=$(sql_int "SELECT count(DISTINCT dispatcher_object_id)
      FROM forecast_results
      WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND is_cancelled=false
        AND dispatcher_object_id IS NOT NULL")
  have_err=$(sql_int "SELECT count(*)
      FROM forecast_results
      WHERE forecast_journal_id='$JOURNAL_ID'::uuid
        AND ( is_cancelled=true OR is_erroneous=true )")
  printf '   dispatcher_object_id: queue(dedup)=%s, forecast_results=%s, is_erroneous/cancelled=%s\n' \
         "${expected_obj:-0}" "${have_obj:-0}" "${have_err:-0}"
  if [[ "${expected_obj:-0}" -eq 0 ]]; then
    warn "dispatcher_object_id=0 in all done queue rows — forecast_description will be empty (no objects)"
  else
    if [[ "${expected_obj:-0}" -eq "${have_obj:-0}" && "${have_err:-0}" -eq 0 ]]; then
      ok "forecast_results: exactly $expected_obj objects, is_erroneous=false, is_cancelled=false"
    else
      fail "forecast_results: expected $expected_obj objects, found $have_obj; is_erroneous/cancelled=$have_err"
    fi
  fi
else
  blit "   (skip: no done rows)"
fi

# --------------------------- 8. coverage channels -----------------------------
sec "8) coverage — channels in queue == channels in forecast_description"
if [[ "${doneq_final:-0}" -gt 0 ]]; then
  cnts=$(sql "SELECT
    (SELECT count(DISTINCT subject_id) FROM ml_predict_queue
       WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='done' AND subject_id IS NOT NULL),
    (SELECT count(DISTINCT k) FROM (
       SELECT jsonb_object_keys(forecast_description->'channels') AS k
       FROM forecast_results
       WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND is_cancelled=false
     ) x WHERE k IS NOT NULL AND trim(k) != '')")
  IFS=$'\t' read -r cov_left cov_right <<< "$cnts"
  cov_left=${cov_left:-0}; cov_right=${cov_right:-0}
  if [[ "${cov_left:-0}" -eq 0 ]]; then
    warn "no subject_id in done queue rows (all NULL) — coverage not checkable"
  elif [[ "${cov_left:-0}" -eq "${cov_right:-0}" && "${cov_left:-0}" -gt 0 ]]; then
    ok "all $cov_left channels in queue are present in forecast_description (100% coverage)"
  else
    fail "channel coverage: queue=$cov_left, forecast_description=$cov_right (must match)"
    sql "SELECT DISTINCT a.subject_id
         FROM (SELECT DISTINCT subject_id FROM ml_predict_queue
                WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='done' AND subject_id IS NOT NULL) a
         WHERE a.subject_id NOT IN (
            SELECT DISTINCT k::text
            FROM (SELECT jsonb_object_keys(forecast_description->'channels') AS k
                  FROM forecast_results
                  WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND is_cancelled=false) x
            WHERE k IS NOT NULL AND trim(k) != ''
         )
         ORDER BY a.subject_id LIMIT 10;" | while IFS=$'\t' read -r s; do
      [[ -n "$s" ]] && blit "     channel ONLY in queue: $s"
    done
    sql "SELECT DISTINCT x.k::text AS s
         FROM (SELECT jsonb_object_keys(forecast_description->'channels') AS k
               FROM forecast_results
               WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND is_cancelled=false) x
         WHERE x.k IS NOT NULL AND trim(x.k) != ''
           AND x.k::text NOT IN (
              SELECT DISTINCT subject_id FROM ml_predict_queue
              WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='done'
              AND subject_id IS NOT NULL
            )
         ORDER BY x.s LIMIT 10;" | while IFS=$'\t' read -r s; do
      [[ -n "$s" ]] && blit "     channel ONLY in results: $s"
    done
  fi
fi

# --------------------------- 9. replay POST /predict --------------------------
sec "9) replay /predict (independent ml-service check using queue data)"
if [[ "${SKIP_REPLAY:-0}" == "1" ]]; then
  blit "   SKIP_REPLAY=1 — replay skipped"
elif [[ "${doneq_final:-0}" -gt 0 ]] && command -v curl >/dev/null 2>&1; then
  replay_row=$(sql "SELECT category, subject_id, features::text
      FROM ml_predict_queue
      WHERE forecast_journal_id='$JOURNAL_ID'::uuid AND status='done'
      ORDER BY id LIMIT 1;")
  if [[ -n "$replay_row" ]]; then
    IFS=$'\t' read -r rc rs rf <<< "$replay_row"
    payload=$(python3 - "$rc" "$rs" "$rf" <<'PY'
import json, sys
cat, subj, feats = sys.argv[1], sys.argv[2], sys.argv[3]
try: feats = json.loads(feats) if feats else {}
except Exception: feats = {}
print(json.dumps({"category": cat, "subject_id": subj,
  "current_features": feats, "horizon_hours": 24}))
PY
    )
    http_post "$ML_URL/predict" "$payload"
    if [[ "$HTTP_CODE" == "200" ]]; then
      rr=$(jsonv "$HTTP_BODY" 'risk_score')
      rp=$(jsonv "$HTTP_BODY" 'probability')
      rl=$(jsonv "$HTTP_BODY" 'predicted_label')
      rv=$(jsonv "$HTTP_BODY" 'model_version')
      if [[ "$rl" == "true" || "$rl" == "false" ]]; then
        in_range=$(python3 - "$rr" "$rp" <<'PY'
import sys
try:
    rr = float(sys.argv[1]); rp = float(sys.argv[2])
    print("1" if (0 <= rr <= 1 and 0 <= rp <= 1) else "0")
except Exception:
    print("0")
PY
        )
        if [[ "$rv" != "null" && -n "${rv:-}" ]] && [[ "$in_range" == "1" ]]; then
          ok "replay /predict -> 200 (cat=$rc, subj=$rs, risk=$rr, prob=$rp, label=$rl, model_version=$rv)"
        else
          fail "replay /predict -> 200, but invalid fields: risk=$rr prob=$rp label=$rl model_version=$rv"
        fi
      else
        fail "replay /predict -> 200, predicted_label=$rl (expected bool)"
      fi
    else
      blit "   replay body: ${HTTP_BODY:0:200}"
      if [[ "$HTTP_CODE" == "422" ]]; then
        fail "replay /predict -> 422: ${HTTP_BODY:0:200} (ml-service could not predict with queue data)"
      else
        fail "replay /predict -> HTTP $HTTP_CODE: ${HTTP_BODY:0:200}"
      fi
    fi
  else
    blit "   (no queue rows for replay)"
  fi
else
  blit "   (skip: no done rows or no curl)"
fi

# --------------------------- ИТОГ ---------------------------------------------
printf '\n%s============================================================\n' "$BLD"
printf '%s  VERDICT\n' "$BLD"
printf '%s============================================================\n' "$BLD"
nfail=${#FAILS[@]}
nwarn=${#WARNS[@]}

if (( nfail > 0 )); then
  printf '%s FAIL — forecast did NOT complete cleanly: %d critical issues\n' "$RED" "$nfail"
  for msg in "${FAILS[@]}"; do
    printf '%s  - %s%s\n' "$RED" "$msg" "$NC"
  done
  exit 2
elif (( nwarn > 0 )); then
  printf '%s WARN — forecast completed, with notes (%d)\n' "$YEL" "$nwarn"
  for msg in "${WARNS[@]}"; do
    printf '%s  - %s%s\n' "$YEL" "$msg" "$NC"
  done
  exit 1
else
  printf '%s OK — forecast completed correctly and without errors\n' "$GREEN"
  printf '%s  journal=%s, queue=%s done/total, forecast_results=%s objects\n' \
        "$GREEN" "$JOURNAL_ID" "${doneq_final:-0}/${totalq:-0}" "${have_obj:-0}"
  exit 0
fi