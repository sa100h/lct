from __future__ import annotations

from datetime import datetime, timezone

from app.db import Db


def test_forecast_db_module_has_no_legacy_table_sql():
    source = open(__file__.replace("tests/test_db_forecast.py", "app/db.py"), encoding="utf-8").read()
    assert "FROM predictions" not in source
    assert "FROM sensor_features" not in source


def test_forecast_result_description_keeps_textual_input_outside_ml_result():
    from app.forecast_flow import build_features
    assert build_features("open") == {"value": "open"}
