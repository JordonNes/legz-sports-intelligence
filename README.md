# LEGZ Sports Intelligence

LEGZ Sports Intelligence (LSI) is the persistent, evidence-first sports intelligence brain supporting LEGZ & JINX predictions. LIVE publishes; LSI remembers, evaluates and learns.

## Governing workflow

**ARCHIVE → PUBLISH → UPDATE → RESOLVE → SCORE → LEARN**

Before LEGZ & JINX LIVE replaces odds, props or recommendations, LSI should preserve the prediction-time market, LEGZ/JINX opinion, confidence, sources and contextual variables. Completed events are resolved against actual results and closing markets for recaps, calibration and long-term model learning.

## Current capabilities

- Athlete profile lookup and question routing
- Explicit knowledge-gap responses
- MLB, WNBA, NFL, NBA, NHL and UFC market templates
- Live/free-first schedules, odds, injuries and lineup integrations where available
- User-supplied market evaluation with uncertainty-sensitive PASS thresholds
- **NFL Coach DNA** influence scoring and fingerprints
- Coach/player before-under-after correlation comparisons
- Evidence stages: observed → correlated → persistent → controlled → predictive
- FastAPI browser interface and API
- Automated pytest suite and GitHub Actions workflow
- Docker, Render and Railway deployment configuration

## NFL Coach DNA

LSI treats HC, OC, DC, special teams coordinator and actual offensive/defensive play callers as primary coaching roles, with key position coaches as secondary influences. Coach DNA is designed to measure tendencies such as pass/rush rate, pace, RB workload concentration, target distribution, personnel usage, red-zone behavior, fourth-down aggression, defensive pressure/coverage tendencies and game-state behavior.

Every tendency should retain season/team context, sample size, baseline, confidence, evidence stage and source provenance. Scores are evidence summaries—not causal claims.

API endpoints:

- `POST /api/intelligence/nfl/coach-dna/score`
- `POST /api/intelligence/nfl/coach-dna/fingerprint`
- `POST /api/intelligence/nfl/coach-dna/player-comparison`

## Sports priority

Primary: NFL, NCAA Football, MLB, NHL, NBA, WNBA, NCAA Basketball, FIBA, NASCAR.

Secondary but supported: Tennis, MMA/UFC, Boxing, FIFA, Track & Field.

## Next data-foundation work

1. Persistent source registry and provenance store.
2. Immutable prediction/market snapshot ledger.
3. Results and recap reconciliation.
4. Historical coach/staff assignments and coaching-tree ingestion.
5. Player/team/coach knowledge graph.
6. Correlation and opportunity engine with recency/sample controls.
7. Calibration, CLV, Brier/log-loss and LEGZ-vs-JINX performance reporting.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`. API documentation is available at `/docs`.

## Test

```bash
pytest -q
```

## Deployment

The repository includes a Dockerfile plus Render and Railway configuration. Deploy from `main` after tests pass and verify `/api/health`.
