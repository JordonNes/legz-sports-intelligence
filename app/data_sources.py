from __future__ import annotations

import os
import re
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

def _sanitize_error(value: str) -> str:
    value = re.sub(r"(?i)(apiKey=)[^&\s'\"]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(authorization[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    return value

class LiveSportsClient:
    PLAYER_MARKETS = {
        "MLB": "batter_hits,batter_total_bases,batter_rbis,batter_runs_scored,pitcher_strikeouts",
        "WNBA": "player_points,player_rebounds,player_assists,player_threes",
        "NBA": "player_points,player_rebounds,player_assists,player_threes",
        "NFL": "player_pass_yds,player_pass_tds,player_rush_yds,player_receptions,player_reception_yds",
        "NHL": "player_points,player_shots_on_goal,player_total_saves",
        "UFC": "fight_method_of_victory,fight_total_rounds",
    }

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def _get_response(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> tuple[Any, dict[str, str]]:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
                usage = {key: response.headers.get(key) for key in ("x-requests-remaining", "x-requests-used", "x-requests-last") if response.headers.get(key) is not None}
                return response.json(), usage
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            try:
                payload = exc.response.json()
                provider_code = payload.get("error_code") or payload.get("message")
            except ValueError:
                provider_code = None
            message = f"Provider request failed with HTTP {status}"
            if provider_code:
                message += f" ({provider_code})"
            raise LiveDataError(_sanitize_error(message)) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LiveDataError(_sanitize_error(str(exc))) from exc

    def _get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        return self._get_response(url, params, headers)[0]

    @staticmethod
    def _record(competitor: dict[str, Any]) -> dict[str, Any] | None:
        records = competitor.get("records") or []
        record = next((r for r in records if r.get("type") in {"total", "overall"}), records[0] if records else None)
        if not record:
            return None
        summary = record.get("summary")
        wins = losses = None
        if summary and "-" in summary:
            try:
                wins, losses = [int(x) for x in summary.split("-")[:2]]
            except (TypeError, ValueError):
                pass
        games = (wins or 0) + (losses or 0)
        return {"summary": summary, "wins": wins, "losses": losses, "win_pct": round(wins / games, 4) if games else None}

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
                teams[side] = {"name": team.get("displayName"), "abbreviation": team.get("abbreviation"), "score": competitor.get("score"), "record": self._record(competitor)}
            odds = [{"provider": (item.get("provider") or {}).get("name"), "details": item.get("details"), "over_under": item.get("overUnder"), "spread": item.get("spread")} for item in (competition.get("odds") or [])]
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

    def _espn_embedded_odds(self, league: str, note: str) -> dict[str, Any]:
        schedules = self.schedules(league)
        embedded = []
        for event in schedules["data"]:
            for odd in event.get("odds", []):
                embedded.append({"event_id": event.get("id"), "event": event.get("name"), "start_time": event.get("start_time"), **odd})
        return self._result("ESPN embedded odds", embedded, note=note)

    def odds(self, league: str) -> dict[str, Any]:
        league = league.upper()
        api_key = os.getenv("THE_ODDS_API_KEY")
        if api_key:
            _, _, sport_key = LEAGUES[league]
            try:
                raw, usage = self._get_response(f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds", params={"apiKey": api_key, "regions": os.getenv("ODDS_REGIONS", "us"), "markets": os.getenv("ODDS_MARKETS", "h2h,spreads,totals"), "oddsFormat": "american", "dateFormat": "iso"})
                return self._result("The Odds API", raw, usage=usage)
            except LiveDataError as exc:
                return self._espn_embedded_odds(league, note=f"The Odds API unavailable ({exc}); using limited ESPN fallback.")
        return self._espn_embedded_odds(league, note="Limited coverage; add a valid THE_ODDS_API_KEY for multi-book odds.")

    def player_odds(self, league: str, max_events: int = 5) -> dict[str, Any]:
        league = league.upper()
        api_key = os.getenv("THE_ODDS_API_KEY")
        if not api_key:
            return self._result("The Odds API", [], note="A valid THE_ODDS_API_KEY is required for player-prop markets.")
        _, _, sport_key = LEAGUES[league]
        try:
            events, usage = self._get_response(f"https://api.the-odds-api.com/v4/sports/{sport_key}/events", params={"apiKey": api_key, "dateFormat": "iso"})
        except LiveDataError as exc:
            return self._result("The Odds API event odds", [], note=f"Player props unavailable ({exc}).")
        output = []
        markets = os.getenv(f"{league}_PLAYER_MARKETS", self.PLAYER_MARKETS.get(league, ""))
        for event in events[: max(1, min(max_events, 10))]:
            try:
                raw, call_usage = self._get_response(f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event['id']}/odds", params={"apiKey": api_key, "regions": os.getenv("ODDS_REGIONS", "us"), "markets": markets, "oddsFormat": "american", "dateFormat": "iso"})
                usage = call_usage or usage
                output.append(raw)
            except LiveDataError:
                continue
        return self._result("The Odds API event odds", output, note=f"Player markets requested for up to {max_events} events.", usage=usage)

    def injuries(self, league: str) -> dict[str, Any]:
        sport, espn_league, _ = LEAGUES[league.upper()]
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
    def _result(source: str, data: Any, as_of: str | None = None, note: str | None = None, usage: dict[str, str] | None = None) -> dict[str, Any]:
        return {"source": source, "retrieved_at": datetime.now(timezone.utc).isoformat(), "as_of": as_of, "note": note, "usage": usage or {}, "data": data}
