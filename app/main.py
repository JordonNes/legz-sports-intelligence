from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

APP_VERSION = "0.5.0"
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="LEGZ Sports Intelligence",
    version=APP_VERSION,
    description="Evidence-first sports analysis prototype with explicit uncertainty controls.",
)

ATHLETES = {
    "brett favre": {
        "name": "Brett Favre",
        "sport": "NFL",
        "position": "QB",
        "teams": ["Atlanta Falcons", "Green Bay Packers", "New York Jets", "Minnesota Vikings"],
        "career": {"passing_yards": 71838, "passing_touchdowns": 508, "interceptions": 336},
        "confidence": 0.99,
        "status": "verified historical pilot record",
        "as_of": "career totals",
    },
    "caitlin clark": {
        "name": "Caitlin Clark",
        "sport": "WNBA",
        "position": "Guard",
        "teams": ["Indiana Fever"],
        "career": {},
        "confidence": 0.35,
        "status": "identity-only profile; current statistics not connected",
        "as_of": None,
    },
}

SUPPORTED_LEAGUES = ("MLB", "WNBA", "NFL", "NBA", "NHL", "UFC")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


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
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="Frontend asset missing")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "mode": "prototype",
        "live_data_connected": False,
        "supported_leagues": list(SUPPORTED_LEAGUES),
    }


@app.get("/api/athletes")
def athletes(q: str = "") -> list[dict]:
    normalized = q.lower().strip()
    if not normalized:
        return list(ATHLETES.values())
    return [profile for key, profile in ATHLETES.items() if normalized in key]


@app.post("/api/query")
def query(payload: Question) -> dict:
    normalized = payload.question.lower()
    for key, athlete in ATHLETES.items():
        if key in normalized:
            return {
                "mode": "athlete-analysis",
                "answer": athlete,
                "legz": f"LEGZ found a structured profile for {athlete['name']}.",
                "jinx": "Current-season conclusions remain blocked until timestamped statistics, injuries, lineups, and market data are connected.",
                "confidence": athlete["confidence"],
                "sources": ["validated pilot record"],
            }
    return {
        "mode": "knowledge-gap",
        "answer": "LEGZ does not yet have enough evidence to answer this question.",
        "next_actions": [
            "resolve athlete, team, event, and market identity",
            "collect timestamped approved sources",
            "validate injuries, availability, and market movement",
            "rerun the question",
        ],
        "jinx": "Do not infer or fabricate missing statistics, odds, or availability.",
        "confidence": 0.10,
    }


@app.post("/api/ticket")
def ticket(payload: TicketRequest) -> dict:
    templates = {
        "MLB": ["starting pitcher strikeouts", "team moneyline", "game total"],
        "WNBA": ["lead guard assists", "primary scorer points", "game total"],
        "NFL": ["quarterback passing yards", "team moneyline", "game total"],
        "NBA": ["primary scorer points", "center rebounds", "team moneyline"],
        "NHL": ["goalie saves", "team moneyline", "game total"],
        "UFC": ["fighter moneyline", "fight duration", "significant strikes"],
    }
    return {
        "league": payload.league,
        "risk": payload.risk,
        "status": "PASS",
        "candidate_markets": templates[payload.league],
        "ticket": [],
        "confidence": 0.0,
        "legz": "No live ticket was generated because current odds, injuries, lineups, and schedules are not connected.",
        "jinx": "A multi-leg ticket compounds failure risk. A disciplined PASS is a valid recommendation.",
        "required_inputs": ["event", "sportsbook", "timestamp", "offered line", "price", "availability evidence"],
    }


@app.post("/api/evaluate-market")
def evaluate_market(payload: MarketEvaluation) -> dict:
    edge = payload.projected_value - payload.offered_line
    confidence = max(0.0, min(1.0, 1.0 - payload.uncertainty))
    threshold = 0.5 + (payload.uncertainty * 1.5)
    if abs(edge) < threshold:
        recommendation = "PASS"
    elif edge > 0:
        recommendation = "OVER"
    else:
        recommendation = "UNDER"
    return {
        "league": payload.league,
        "market": payload.market,
        "offered_line": payload.offered_line,
        "projected_value": payload.projected_value,
        "edge": round(edge, 3),
        "uncertainty": payload.uncertainty,
        "confidence": round(confidence, 3),
        "price": payload.price,
        "recommendation": recommendation,
        "jinx": "This evaluates user-supplied numbers only; it does not verify the market, projection, injury status, or price quality.",
    }
