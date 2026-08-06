from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Any


def american_to_probability(price: int | float) -> float:
    value = float(price)
    return 100.0 / (value + 100.0) if value > 0 else abs(value) / (abs(value) + 100.0)


def _window_end(scope: str) -> datetime:
    now = datetime.now(timezone.utc)
    return now + (timedelta(days=1) if scope == "day" else timedelta(days=7))


def _event_in_window(event: dict[str, Any], scope: str) -> bool:
    raw = event.get("commence_time") or event.get("start_time")
    if not raw:
        return True
    try:
        start = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    now = datetime.now(timezone.utc)
    return now <= start <= _window_end(scope)


def _rank_espn_fallback(odds_payload: dict[str, Any], league: str, limit: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in odds_payload.get("data", []):
        details = str(item.get("details") or "").strip()
        spread = item.get("spread")
        if not details:
            continue
        match = re.match(r"(.+?)\s+([+-]?\d+(?:\.\d+)?)$", details)
        selection = match.group(1).strip() if match else details
        parsed_line = float(match.group(2)) if match else (float(spread) if isinstance(spread, (int, float)) else None)
        magnitude = abs(parsed_line or 0.0)
        confidence = min(0.64, 0.51 + magnitude * 0.012)
        candidates.append({
            "type": "team", "league": league, "event_id": item.get("event_id"),
            "event": item.get("event") or "Scheduled event", "start_time": item.get("start_time"),
            "prediction": f"{selection} spread lean" if parsed_line is not None else f"{selection} market lean",
            "selection": selection, "market": "spread", "line": parsed_line,
            "consensus_probability": None, "confidence": round(confidence, 4),
            "grade": "B" if confidence >= 0.60 else "C", "bookmakers": 1,
            "dispersion": None, "source": odds_payload.get("source", "ESPN embedded odds"),
            "legz": f"LEGZ identifies {selection} from ESPN's published event market. This is a directional market lean, not a multi-book value edge.",
            "jinx": "Jinx downgrades this pick because only one embedded market source is available. Recheck injuries, starters, lineups and the exact current price before acting.",
        })
    return sorted(candidates, key=lambda item: item["confidence"], reverse=True)[:limit]


def rank_schedule_predictions(schedule_events: list[dict[str, Any]], league: str, scope: str, limit: int = 10) -> list[dict[str, Any]]:
    """Free fallback using scheduled matchups and available team records; never presented as a verified market edge."""
    candidates: list[dict[str, Any]] = []
    for event in schedule_events:
        if not _event_in_window(event, scope):
            continue
        home = event.get("home") or {}
        away = event.get("away") or {}
        home_pct = ((home.get("record") or {}).get("win_pct"))
        away_pct = ((away.get("record") or {}).get("win_pct"))
        if home_pct is None and away_pct is None:
            selection = home.get("name") or away.get("name")
            confidence = 0.51
            rationale = "the scheduled home side because no comparable free record data was available"
        else:
            home_adj = (home_pct if home_pct is not None else 0.5) + 0.025
            away_adj = away_pct if away_pct is not None else 0.5
            if home_adj >= away_adj:
                selection, chosen, other = home.get("name"), home_adj, away_adj
            else:
                selection, chosen, other = away.get("name"), away_adj, home_adj
            gap = max(0.0, chosen - other)
            confidence = min(0.67, 0.52 + gap * 0.35)
            rationale = f"the stronger available season record after a small home-court adjustment ({chosen:.3f} vs {other:.3f})"
        if not selection:
            continue
        candidates.append({
            "type": "team", "league": league, "event_id": event.get("id"), "event": event.get("name"),
            "start_time": event.get("start_time"), "prediction": f"{selection} to win",
            "selection": selection, "market": "schedule-model", "line": None,
            "consensus_probability": None, "confidence": round(confidence, 4),
            "grade": "B" if confidence >= 0.60 else "C", "bookmakers": 0,
            "dispersion": None, "source": "ESPN schedule and team records",
            "legz": f"LEGZ leans {selection} based on {rationale}. This is a free statistical matchup projection, not a verified sportsbook price.",
            "jinx": "Jinx warns that season record alone is incomplete. Confirm injuries, expected starters, rest, travel, recent form and any available market line before acting.",
        })
    return sorted(candidates, key=lambda item: item["confidence"], reverse=True)[:limit]


def rank_team_predictions(odds_payload: dict[str, Any], league: str, scope: str, limit: int = 10) -> list[dict[str, Any]]:
    data = odds_payload.get("data", [])
    if data and not any("bookmakers" in event for event in data):
        return _rank_espn_fallback(odds_payload, league, limit)
    candidates: list[dict[str, Any]] = []
    for event in data:
        if not _event_in_window(event, scope):
            continue
        prices: dict[str, list[float]] = defaultdict(list)
        books: dict[str, set[str]] = defaultdict(set)
        for bookmaker in event.get("bookmakers", []):
            book = bookmaker.get("title") or bookmaker.get("key") or "unknown"
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                raw_probs = [(o.get("name"), american_to_probability(o.get("price", 0))) for o in outcomes if o.get("name") and o.get("price")]
                total = sum(prob for _, prob in raw_probs)
                if total <= 0:
                    continue
                for name, prob in raw_probs:
                    prices[name].append(prob / total)
                    books[name].add(book)
        for team, probs in prices.items():
            consensus = mean(probs)
            dispersion = pstdev(probs) if len(probs) > 1 else 0.08
            book_count = len(books[team])
            evidence = min(1.0, book_count / 6.0)
            confidence = max(0.05, min(0.90, consensus * 0.65 + evidence * 0.25 - dispersion * 1.5))
            candidates.append({
                "type": "team", "league": league, "event_id": event.get("id"),
                "event": f"{event.get('away_team')} at {event.get('home_team')}",
                "start_time": event.get("commence_time"), "prediction": f"{team} moneyline",
                "selection": team, "market": "h2h", "consensus_probability": round(consensus, 4),
                "confidence": round(confidence, 4), "grade": "A" if confidence >= 0.72 else "B" if confidence >= 0.62 else "C",
                "bookmakers": book_count, "dispersion": round(dispersion, 4),
                "legz": f"LEGZ sees {team} as the market-consensus side across {book_count} bookmaker(s), with a no-vig consensus probability of {consensus:.1%}.",
                "jinx": "Jinx warns that market consensus is not automatically a profitable edge. Confirm injuries, starters, line movement and the exact offered price before acting.",
            })
    return sorted(candidates, key=lambda item: (item["confidence"], item.get("consensus_probability") or 0, item["bookmakers"]), reverse=True)[:limit]


def rank_player_predictions(player_events: list[dict[str, Any]], league: str, scope: str, limit: int = 10) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for event in player_events:
        if not _event_in_window(event, scope):
            continue
        grouped: dict[tuple[str, str, float], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        books: dict[tuple[str, str, float], set[str]] = defaultdict(set)
        for bookmaker in event.get("bookmakers", []):
            book = bookmaker.get("title") or bookmaker.get("key") or "unknown"
            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "")
                if not market_key.startswith("player_"):
                    continue
                for outcome in market.get("outcomes", []):
                    player, side, point, price = outcome.get("description"), outcome.get("name"), outcome.get("point"), outcome.get("price")
                    if not player or side not in {"Over", "Under"} or point is None or not price:
                        continue
                    key = (market_key, player, float(point))
                    grouped[key][side].append(american_to_probability(price))
                    books[key].add(book)
        for (market_key, player, point), sides in grouped.items():
            side, probs = max(sides.items(), key=lambda item: mean(item[1]))
            opposing = sides.get("Under" if side == "Over" else "Over", [])
            raw = mean(probs)
            opposing_mean = mean(opposing) if opposing else max(0.01, 1.0 - raw)
            fair = raw / (raw + opposing_mean)
            count = len(books[(market_key, player, point)])
            dispersion = pstdev(probs) if len(probs) > 1 else 0.10
            confidence = max(0.05, min(0.82, fair * 0.60 + min(1.0, count / 5.0) * 0.25 - dispersion))
            candidates.append({
                "type": "player", "league": league, "event_id": event.get("id"),
                "event": f"{event.get('away_team')} at {event.get('home_team')}", "start_time": event.get("commence_time"),
                "prediction": f"{player} {side} {point}", "selection": player, "market": market_key,
                "line": point, "side": side.upper(), "consensus_probability": round(fair, 4),
                "confidence": round(confidence, 4), "grade": "A" if confidence >= 0.70 else "B" if confidence >= 0.60 else "C",
                "bookmakers": count, "legz": f"LEGZ identifies a {side.lower()} consensus for {player} at {point}, based on {count} bookmaker(s).",
                "jinx": "Jinx warns that player props are especially sensitive to minutes, role, lineup confirmation, injury news and late price movement.",
            })
    return sorted(candidates, key=lambda item: (item["confidence"], item["consensus_probability"], item["bookmakers"]), reverse=True)[:limit]


def build_report(league: str, scope: str, team_odds: dict[str, Any], player_events: list[dict[str, Any]] | None = None, limit: int = 10, schedule_events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    team = rank_team_predictions(team_odds, league, scope, limit)
    fallback_used = False
    if not team and schedule_events:
        team = rank_schedule_predictions(schedule_events, league, scope, limit)
        fallback_used = bool(team)
    player = rank_player_predictions(player_events or [], league, scope, limit)
    combined = sorted(team + player, key=lambda item: item["confidence"], reverse=True)[:limit]
    source = "ESPN schedule and team records" if fallback_used else team_odds.get("source", "unknown")
    return {
        "league": league, "scope": scope, "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "free-first ranking: multi-book consensus when available, ESPN market lean second, schedule/record projection fallback third",
        "source": source, "fallback_used": fallback_used,
        "top_team_predictions": team, "top_player_predictions": player, "top_overall": combined,
        "legz_summary": f"LEGZ ranked {len(team)} team and {len(player)} player candidates from {source}.",
        "jinx_summary": "Jinx reduces confidence when market prices, player props, injury confirmation or lineup confirmation are missing.",
        "limitations": [
            "Schedule-based selections are matchup projections, not verified betting edges.",
            "Player predictions require verified player markets or a separate statistical projection layer.",
            "Availability, injuries, lineups and prices must be rechecked near event time.",
        ],
    }
