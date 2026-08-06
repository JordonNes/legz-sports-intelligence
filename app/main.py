from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.data_sources import LEAGUES, LiveDataError, LiveSportsClient
from app.predictions import build_report

APP_VERSION = "0.7.1"
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SUPPORTED_LEAGUES = tuple(LEAGUES)
live = LiveSportsClient()

app = FastAPI(title="LEGZ Sports Intelligence", version=APP_VERSION,
              description="Evidence-first sports analysis with free-first live sources, ranked predictions, and explicit uncertainty controls.")

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
        "status": "ok", "version": APP_VERSION, "mode": "free-first-ranked-intelligence",
        "live_data_connected": True, "supported_leagues": list(SUPPORTED_LEAGUES),
        "providers": {
            "schedules": "MLB Stats API + ESPN",
            "odds": "The Odds API when valid; ESPN fallback",
            "injuries": "ESPN",
            "lineups": "MLB live feed + ESPN event summary",
            "prediction_fallback": "ESPN schedule + team records",
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

@app.get("/api/live/{league}/player-odds")
def player_odds(league: str, max_events: int = Query(default=5, ge=1, le=10)) -> dict:
    return _call(lambda: live.player_odds(league, max_events))

@app.get("/api/live/{league}/injuries")
def injuries(league: str) -> dict:
    return _call(lambda: live.injuries(league))

@app.get("/api/live/{league}/events/{event_id}/lineup")
def lineup(league: str, event_id: str) -> dict:
    return _call(lambda: live.lineup(league, event_id))

@app.get("/api/predictions/{league}")
def predictions(
    league: str,
    scope: Literal["day", "week"] = "day",
    limit: int = Query(default=10, ge=1, le=10),
    include_players: bool = True,
    max_player_events: int = Query(default=5, ge=1, le=10),
) -> dict:
    normalized = league.upper()
    if normalized not in LEAGUES:
        raise HTTPException(404, f"Unsupported league: {league}")
    team_odds = _call(lambda: live.odds(normalized))
    player_payload = _call(lambda: live.player_odds(normalized, max_player_events)) if include_players else {"data": []}
    days = 2 if scope == "day" else 8
    schedule_events = []
    schedule_sources = []
    for offset in range(days):
        payload = _call(lambda offset=offset: live.schedules(normalized, date.today() + timedelta(days=offset)))
        schedule_events.extend(payload.get("data", []))
        schedule_sources.append(payload.get("source"))
    unique_events = {str(event.get("id") or event.get("name")): event for event in schedule_events}
    report = build_report(normalized, scope, team_odds, player_payload.get("data", []), limit, list(unique_events.values()))
    report["sources"] = {
        "team_odds": team_odds.get("source"),
        "player_odds": player_payload.get("source"),
        "schedules": sorted(set(source for source in schedule_sources if source)),
        "team_usage": team_odds.get("usage", {}),
        "player_usage": player_payload.get("usage", {}),
    }
    return report

@app.post("/api/ticket")
def ticket(payload: TicketRequest) -> dict:
    report = predictions(payload.league, "day", 10, True, 5)
    picks = report["top_overall"]
    max_legs = {"conservative": 2, "balanced": 3, "aggressive": 5}[payload.risk]
    threshold = {"conservative": 0.68, "balanced": 0.60, "aggressive": 0.54}[payload.risk]
    eligible = [pick for pick in picks if pick["confidence"] >= threshold and pick.get("market") != "schedule-model"]
    return {
        "league": payload.league, "risk": payload.risk,
        "status": "READY" if eligible else "PASS", "ticket": eligible[:max_legs],
        "confidence": round(sum(item["confidence"] for item in eligible[:max_legs]) / max(1, len(eligible[:max_legs])), 4),
        "legz": "LEGZ excludes schedule-only projections from automatic tickets because no verified market price is attached.",
        "jinx": "Jinx warns that parlay legs compound risk and may be correlated. Recheck prices, injuries and lineups immediately before use.",
        "report": report,
    }

@app.post("/api/evaluate-market")
def evaluate_market(payload: MarketEvaluation) -> dict:
    edge = payload.projected_value - payload.offered_line
    threshold = 0.5 + (payload.uncertainty * 1.5)
    recommendation = "PASS" if abs(edge) < threshold else ("OVER" if edge > 0 else "UNDER")
    return {
        "league": payload.league, "market": payload.market,
        "offered_line": payload.offered_line, "projected_value": payload.projected_value,
        "edge": round(edge, 3), "uncertainty": payload.uncertainty,
        "confidence": round(max(0, min(1, 1 - payload.uncertainty)), 3),
        "price": payload.price, "recommendation": recommendation,
        "jinx": "This evaluates supplied numbers; it does not prove projection quality or market validity.",
    }
