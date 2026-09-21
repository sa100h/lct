# ML producer contract: channel mapping & feature ingestion

The broker keys **purely on `subject_id`** — the ml-service channel id (string).
The mapping between app equipment and ML channels is a **producer-side concern**
(decision 2026-09-21): the producer writes features, the broker does not know
about equipment at all.

## Identities

| Name | Where | Meaning |
|---|---|---|
| `channel_id` | `sensor_features.channel_id` | channel id from the organizer's register (numeric string, e.g. `196771`) |
| `subject_id` | `ml_predict_queue.subject_id`, `predictions.subject_id` | **== `channel_id`**, passed verbatim to `ml-service /predict` |
| `equipment.external_id` | `equipment.external_id` | the same channel id — the organizer's register id **is** the channel id (1:1) |

`equipment.external_id` is unique (002_lct_domain), so equipment : channel is 1:1.
The identity is recorded explicitly in `equipment_channel_map` (see below) so that
joins between equipment and ML output go through a verifiable table instead of an
implicit assumption.

## Tables (migration `006_channel_mapping.sql`)

- **`channel_directory`** — the organizer's channel reference, one row per data
  channel (`channel_directory.channel_id` PK). Columns: `type_system`, `type_sensor`,
  `tag_cabinet` (engineer cabinet tag), `object_id` (object from
  `справочник_объектов_диспетчер`), `sensor_name`. Loaded from
  `ml-data/справочник_каналов_датчиков_NEW.csv` by
  `scripts/load_channel_directory.py` (idempotent upsert, re-run after register updates).
- **`equipment_channel_map`** — confirmed pairs `(equipment_external_id, channel_id)`,
  PK on both, FK to `channel_directory`. Loaded by
  `scripts/map_equipment_channels.py pairs.csv`
  (columns `equipment_external_id,channel_id,note`). The script refuses unknown
  channel ids and warns on >1 channel per equipment (1:1 invariant).
- **`sensor_features`** gained `UNIQUE (channel_id, as_of)` — producer-safe dedup
  so re-delivery is idempotent; the queue fan-out trigger stays deduped downstream
  via `uq_queue_dedup (category, subject_id, as_of)`.

## Producer writes (idempotent upsert)

```sql
INSERT INTO sensor_features (channel_id, as_of, features)
VALUES ($1, $2, $3)                                   -- $3: jsonb feature vector
ON CONFLICT (channel_id, as_of) DO UPDATE SET features = EXCLUDED.features;
```

- `channel_id` must exist in `channel_directory` (validates the channel universe).
- `as_of` = observation timestamp (UTC). It is the dedup key.
- `features` = feature vector; keys are the category feature names from
  `ml-service/app/models/features.py` (e.g. `temperature_delta_1h`).
- After INSERT the `trg_enqueue_features` trigger fans the row out to the
  predict queue (one row per category) and pings `LISTEN ml_predict`. The
  broker drains the queue → `POST /predict` → upserts `predictions`.

## Equipment ↔ ML output join (for API/frontend)

```sql
SELECT e.id, e.external_id, cd.object_id, cd.tag_cabinet, cd.sensor_name,
       p.category, p.risk_score, p.predicted_label, p.predicted_at
FROM equipment e
JOIN equipment_channel_map m ON m.equipment_external_id = e.external_id
JOIN channel_directory       cd ON cd.channel_id = m.channel_id
JOIN predictions             p  ON p.subject_id   = cd.channel_id
WHERE p.predicted_at >= now() - interval '24 hours';
```

Categories come from `ml-service` (`sensor-failure`, `fire-risk`,
`unauthorized-access`, `infrastructure-wear`).

## Verification facts (2026-09-21)

- `справочник_каналов_датчиков_NEW.csv`: 11 485 channels, all numeric, unique;
  78 objects; 1:1 channel→cabinet tag.
- ML data (sensor-failure ≈ 11 482 channels, fire-risk ≈ 6 830) is a subset of
  the reference — same id universe; channels outside ML coverage simply produce no
  predictions until data appears.
