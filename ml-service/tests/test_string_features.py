from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


def test_predict_rejects_non_numeric_feature_as_model_error(monkeypatch):
    class Engine:
        def predict(self, *args):
            raise ValueError("Feature 'value' must be numeric")

    app.state.engine = Engine()
    response = TestClient(app).post(
        "/predict",
        json={"category": "fire-risk", "subject_id": "120578", "current_features": {"value": "open"}},
    )
    assert response.status_code == 422
    assert "must be numeric" in response.json()["detail"]
