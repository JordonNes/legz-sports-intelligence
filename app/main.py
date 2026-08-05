from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.data_sources import LEAGUES, LiveDataError, LiveSportsClient

APP_VERSION = "0.6.0"
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SUPPORTED_LEAGUES = tuple(LEAGUES)
live = LiveSportsClient()

app = FastAPI(title="LEGZ Sports Intelligence", version=APP_VERSION,
              description="Evidence-first sports analysis with live source adapters and explicit uncertainty controls.")

class TicketRequest(BaseModel):
    league: Literal["MLB", "WNBA", "NFL", "NBA", "NHL", "UFC"]
    risk: Literal["conservative", "balanced", "aggressive"] = "balanced"

class MarketEvaluation(BaseModel):
    league: Literal["MLB", "WNBA", "NFL", "NBA", "NHL", "UFC"]
    market: str = Field(min_length=3, max_length=200)
    offered_line: float
    projected_value: float
    uncertainty: float = Field(ge=0.0, le=1.0)
    price: int | None = Field(default=None, ge=-10000, le=10000)

@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    path = STATIC_DIR / "index.html"
    if not path.exists():
        raise HTTPException(500, "Frontend asset missing")
    return HTMLResponse(path.read_text(encoding="utf-8"))

@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "mode": "live-data-foundation",
        "live_data_connected": True,
        "supported_leagues": list(SUPPORTED_LEAGUES),
        "providers": {
            "schedules": "MLB Stats API + ESPN",
            "odds": "The Odds API when keyed; ESPN fallback",
            "injuries": "BALLDONTLIE when keyed; ESPN fallback",
            "lineups": "MLB live feed + ESPN event summary",
        },
    }

def _call(fn):
    try:
        return fn()
    except LiveDataError as exc:
        raise HTTPException(status_code=502, detail={"message": "Live provider unavailable", "error": str(exc)}) from exc

@app.get("/api/live/{league}/schedule")
def schedule(league: str, on_date: date | None = Query(default=None)) -> dict:
    return _call(lambda: live.schedules(league, on_date))

@app.get("/api/live/{league}/odds")
def odds(league: str) -> dict:
    return _call(lambda: live.odds(league))

@app.get("/api/live/{league}/injuries")
def injuries(league: str) -> dict:
    return _call(lambda: live.injuries(league))

@app.get("/api/live/{league}/events/{event_id}/lineup")
def lineup(league: str, event_id: str) -> dict:
    return _call(lambda: live.lineup(league, event_id))

@app.post("/api/ticket")
def ticket(payload: TicketRequest) -> dict:
    schedule_data = _call(lambda: live.schedules(payload.league))
    odds_data = _call(lambda: live.odds(payload.league))
    return {
        "league": payload.league,
        "risk": payload.risk,
        "status": "DATA_READY" if schedule_data["data"] and odds_data["data"] else "PASS",
        "schedule": schedule_data,
        "odds": odds_data,
        "ticket": [],
        "confidence": 0.0,
        "legz": "Live events and available odds were retrieved. Automated selections remain disabled until a validated projection and backtesting layer is added.",
        "jinx": "Current data is not the same as a proven edge. Confirm injuries, starters, timestamps, book, and price before acting.",
    }

@app.post("/api/evaluate-market")
def evaluate_market(payload: MarketEvaluation) -> dict:
    edge = payload.projected_value - payload.offered_line
    threshold = 0.5 + (payload.uncertainty * 1.5)
    recommendation = "PASS" if abs(edge) < threshold else ("OVER" if edge > 0 else "UNDER")
    return {
        "league": payload.league,
        "market": payload.market,
        "offered_line": payload.offered_line,
        "projected_value": payload.projected_value,
        "edge": round(edge, 3),
        "uncertainty": payload.uncertainty,
        "confidence": round(max(0, min(1, 1 - payload.uncertainty)), 3),
        "price": payload.price,
        "recommendation": recommendation,
        "jinx": "This evaluates supplied numbers; it does not prove projection quality or market validity.",
    }
