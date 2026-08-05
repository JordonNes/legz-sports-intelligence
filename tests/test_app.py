from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_homepage():
    response = client.get("/")
    assert response.status_code == 200
    assert "LEGZ Sports Intelligence" in response.text

def test_health():
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["version"] == "0.5.0"
    assert payload["live_data_connected"] is False
    assert "MLB" in payload["supported_leagues"]

def test_favre_query():
    response = client.post("/api/query", json={"question": "Tell me about Brett Favre"})
    assert response.status_code == 200
    assert response.json()["mode"] == "athlete-analysis"

def test_unknown_creates_gap_response():
    response = client.post("/api/query", json={"question": "Analyze Unknown Prospect XYZ"})
    assert response.json()["mode"] == "knowledge-gap"
    assert response.json()["confidence"] <= 0.1

def test_ticket_passes_without_live_data():
    response = client.post("/api/ticket", json={"league": "WNBA", "risk": "balanced"})
    payload = response.json()
    assert payload["status"] == "PASS"
    assert payload["ticket"] == []

def test_mlb_supported():
    response = client.post("/api/ticket", json={"league": "MLB", "risk": "conservative"})
    assert response.status_code == 200
    assert "starting pitcher strikeouts" in response.json()["candidate_markets"]

def test_market_over():
    response = client.post("/api/evaluate-market", json={"league":"WNBA","market":"points","offered_line":22.5,"projected_value":25.0,"uncertainty":0.1})
    assert response.json()["recommendation"] == "OVER"

def test_market_under():
    response = client.post("/api/evaluate-market", json={"league":"MLB","market":"strikeouts","offered_line":7.5,"projected_value":5.7,"uncertainty":0.1})
    assert response.json()["recommendation"] == "UNDER"

def test_market_pass_on_small_edge():
    response = client.post("/api/evaluate-market", json={"league":"WNBA","market":"assists","offered_line":7.5,"projected_value":7.7,"uncertainty":0.3})
    assert response.json()["recommendation"] == "PASS"

def test_market_validation():
    response = client.post("/api/evaluate-market", json={"league":"WNBA","market":"points","offered_line":22.5,"projected_value":25.0,"uncertainty":2.0})
    assert response.status_code == 422
