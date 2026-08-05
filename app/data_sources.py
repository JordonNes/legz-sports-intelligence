from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

import httpx

LEAGUES = {
    "MLB": ("baseball", "mlb", "baseball_mlb"),
    "WNBA": ("basketball", "wnba", "basketball_wnba"),
    "NBA": ("basketball", "nba", "basketball_nba"),
    "NFL": ("football", "nfl", "americanfootball_nfl"),
    "NHL": ("hockey", "nhl", "icehockey_nhl"),
    "UFC": ("mma", "ufc", "mma_mixed_martial_arts"),
}

class LiveDataError(RuntimeError):
    pass

class LiveSportsClient:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def _get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LiveDataError(str(exc)) from exc

    def schedules(self, league: str, on_date: date | None = None) -> dict[str, Any]:
        league = league.upper()
        if league not in LEAGUES:
            raise LiveDataError(f"Unsupported league: {league}")
        if league == "MLB":
            return self._mlb_schedule(on_date)
        sport, espn_league, _ = LEAGUES[league]
        params = {"dates": (on_date or date.today()).strftime("%Y%m%d"), "limit": 100}
        raw = self._get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{espn_league}/scoreboard", params=params)
        events = []
        for event in raw.get("events", []):
            competition = (event.get("competitions") or [{}])[0]
            teams = {}
            for competitor in competition.get("competitors", []):
                side = competitor.get("homeAway")
                team = competitor.get("team", {})
                teams[side] = {"name": team.get("displayName"), "abbreviation": team.get("abbreviation"), "score": competitor.get("score")}
            odds = []
            for item in competition.get("odds") or []:
                odds.append({"provider": (item.get("provider") or {}).get("name"), "details": item.get("details"), "over_under": item.get("overUnder"), "spread": item.get("spread")})
            events.append({"id": event.get("id"), "name": event.get("name"), "start_time": event.get("date"), "status": ((event.get("status") or {}).get("type") or {}).get("description"), "home": teams.get("home"), "away": teams.get("away"), "venue": (competition.get("venue") or {}).get("fullName"), "broadcasts": [b.get("names", []) for b in competition.get("broadcasts", [])], "odds": odds})
        return self._result("ESPN scoreboard JSON", events, raw.get("day", {}).get("date"))

    def _mlb_schedule(self, on_date: date | None) -> dict[str, Any]:
        target = (on_date or date.today()).isoformat()
        raw = self._get("https://statsapi.mlb.com/api/v1/schedule", params={"sportId": 1, "date": target, "hydrate": "probablePitcher,team,venue,linescore"})
        events = []
        for bucket in raw.get("dates", []):
            for game in bucket.get("games", []):
                teams = game.get("teams", {})
                events.append({"id": game.get("gamePk"), "name": f"{teams.get('away', {}).get('team', {}).get('name')} at {teams.get('home', {}).get('team', {}).get('name')}", "start_time": game.get("gameDate"), "status": (game.get("status") or {}).get("detailedState"), "home": {"name": teams.get("home", {}).get("team", {}).get("name"), "score": teams.get("home", {}).get("score"), "probable_pitcher": (teams.get("home", {}).get("probablePitcher") or {}).get("fullName")}, "away": {"name": teams.get("away", {}).get("team", {}).get("name"), "score": teams.get("away", {}).get("score"), "probable_pitcher": (teams.get("away", {}).get("probablePitcher") or {}).get("fullName")}, "venue": (game.get("venue") or {}).get("name")})
        return self._result("MLB Stats API", events, target)

    def odds(self, league: str) -> dict[str, Any]:
        league = league.upper()
        api_key = os.getenv("THE_ODDS_API_KEY")
        if api_key:
            _, _, sport_key = LEAGUES[league]
            raw = self._get(f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds", params={"apiKey": api_key, "regions": os.getenv("ODDS_REGIONS", "us"), "markets": os.getenv("ODDS_MARKETS", "h2h,spreads,totals"), "oddsFormat": "american", "dateFormat": "iso"})
            return self._result("The Odds API", raw)
        schedules = self.schedules(league)
        embedded = []
        for event in schedules["data"]:
            for odd in event.get("odds", []):
                embedded.append({"event_id": event.get("id"), "event": event.get("name"), **odd})
        return self._result("ESPN embedded odds", embedded, note="Limited coverage; add THE_ODDS_API_KEY for multi-book odds.")

    def injuries(self, league: str) -> dict[str, Any]:
        league = league.upper()
        bdl_key = os.getenv("BALLDONTLIE_API_KEY")
        if bdl_key and league in {"MLB", "NBA", "NFL", "NHL"}:
            prefix = {"NBA": "", "MLB": "mlb/", "NFL": "nfl/", "NHL": "nhl/"}[league]
            raw = self._get(f"https://api.balldontlie.io/{prefix}v1/player_injuries", headers={"Authorization": bdl_key})
            return self._result("BALLDONTLIE", raw.get("data", []))
        sport, espn_league, _ = LEAGUES[league]
        raw = self._get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{espn_league}/injuries")
        return self._result("ESPN injuries JSON", raw.get("injuries", raw.get("items", raw)))

    def lineup(self, league: str, event_id: str) -> dict[str, Any]:
        league = league.upper()
        if league == "MLB":
            raw = self._get(f"https://statsapi.mlb.com/api/v1.1/game/{event_id}/feed/live")
            box = (raw.get("liveData") or {}).get("boxscore") or {}
            teams = box.get("teams", {})
            return self._result("MLB Stats API live game feed", {"home": teams.get("home", {}).get("battingOrder", []), "away": teams.get("away", {}).get("battingOrder", []), "players": teams}, note="Official batting orders generally appear near game time.")
        sport, espn_league, _ = LEAGUES[league]
        raw = self._get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{espn_league}/summary", params={"event": event_id})
        return self._result("ESPN event summary JSON", {"rosters": raw.get("rosters", []), "injuries": raw.get("injuries", []), "odds": raw.get("odds", []), "competitions": raw.get("header", {}).get("competitions", [])}, note="Confirmed starters may not be published until close to event time.")

    @staticmethod
    def _result(source: str, data: Any, as_of: str | None = None, note: str | None = None) -> dict[str, Any]:
        return {"source": source, "retrieved_at": datetime.now(timezone.utc).isoformat(), "as_of": as_of, "note": note, "data": data}
