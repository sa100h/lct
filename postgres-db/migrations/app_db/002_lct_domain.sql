-- LCT domain schema: equipment registers, alarms, predictions, maintenance requests.
-- Postgres 13+ has gen_random_uuid() built in.

CREATE TABLE IF NOT EXISTS equipment (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category text NOT NULL,                -- sensor | vent-shaft | pump | chamber | hatch
    external_id text NOT NULL UNIQUE,      -- id from the organizer's register
    name text,
    address text,
    district text,
    commissioned_at date,
    last_repair_at date,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alarms (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_external_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    alarm_type text NOT NULL,              -- contact | volume | temperature | smoke | gas
    address text,
    verification_result text,              -- true_alarm | false_alarm | pending
    raw_event jsonb
);
CREATE INDEX IF NOT EXISTS idx_alarms_sensor_time ON alarms (sensor_external_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_alarms_occurred_at ON alarms (occurred_at);

CREATE TABLE IF NOT EXISTS predictions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category text NOT NULL,                -- sensor-failure | fire-risk | unauthorized-access | infrastructure-wear
    subject_id text NOT NULL,
    risk_score numeric(5,4) NOT NULL,
    predicted_label boolean NOT NULL,
    horizon_hours integer NOT NULL DEFAULT 24,
    model_version text,
    predicted_at timestamptz NOT NULL DEFAULT now(),
    feature_importance jsonb
);
CREATE INDEX IF NOT EXISTS idx_predictions_category_time ON predictions (category, predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_subject ON predictions (subject_id, predicted_at DESC);

CREATE TABLE IF NOT EXISTS maintenance_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id uuid REFERENCES predictions (id) ON DELETE SET NULL,
    equipment_external_id text,
    status text NOT NULL DEFAULT 'draft',  -- draft | created | dispatched | closed
    priority integer NOT NULL DEFAULT 0,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_maintenance_status ON maintenance_requests (status, created_at DESC);
