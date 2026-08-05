# LEGZ Sports Intelligence

LEGZ is an evidence-first sports analysis prototype. It separates verified records, user-supplied assumptions, and missing knowledge; Jinx challenges unsupported confidence.

## Current capabilities

- Athlete profile lookup and question routing
- Explicit knowledge-gap responses
- MLB, WNBA, NFL, NBA, NHL, and UFC market templates
- User-supplied market evaluation with uncertainty-sensitive PASS thresholds
- FastAPI browser interface and API
- Automated pytest suite and GitHub Actions workflow
- Docker, Render, and Railway deployment configuration

## Important limitation

No live odds, injuries, lineups, schedules, or licensed statistics feeds are connected. The ticket endpoint therefore returns `PASS` instead of inventing live recommendations.

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

The repository includes a Dockerfile plus Render and Railway configuration. Connect the repository to the selected hosting provider, confirm the health check at `/api/health`, and deploy from `main` after review.

## Production roadmap

1. Add timestamped schedules, rosters, injuries, lineups, and odds ingestion.
2. Record source provenance and freshness for every analytical input.
3. Build league-specific projection models and calibration reports.
4. Add authentication, persistence, observability, and rate limiting.
5. Conduct responsible-gambling, privacy, licensing, and jurisdictional review before public wagering recommendations.
