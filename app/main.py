"""
app/main.py
───────────
FastAPI application entry point.

Endpoints
─────────
GET  /                         → Serves index.html (the frontend SPA)
GET  /api/analyze/{username}   → Returns the full JSON analysis for a user
GET  /api/health               → Simple liveness check

Static / template mounts
─────────────────────────
/static  →  ../static/   (CSS, images, favicons, etc.)
/        →  ../templates/ (Jinja2; only index.html is rendered)

Run locally
───────────
    cd github-portfolio-analyzer
    uvicorn app.main:app --reload --port 8000
"""

import logging
from pathlib import Path

import requests as req_lib
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.github_api import fetch_user_profile, fetch_user_repos, fetch_recent_events
from app.analyzer import run_full_analysis

#  Logging 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

#  Path helpers 

ROOT = Path(__file__).resolve().parent.parent

TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR    = ROOT / "static"

#  FastAPI app 
app = FastAPI(
    title="GitHub Portfolio Analyzer",
    description="Analyze any public GitHub profile and generate a portfolio score.",
    version="1.0.0",
)

# Mount /static so the browser can fetch style.css, scripts, images, etc.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Jinja2 template engine for rendering index.html.
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))



# Routes


@app.get("/")
async def serve_frontend(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/health", tags=["meta"])
async def health_check():
    """Quick liveness probe."""
    return {"status": "ok", "service": "github-portfolio-analyzer"}


@app.get("/api/analyze/{username}", tags=["analysis"])
async def analyze_user(username: str):
    """
    Fetch and analyze a GitHub user's public portfolio.

    Parameters
    ----------
    username : GitHub login (e.g. `torvalds`, `gvanrossum`).

    Returns
    -------
    200 – Full analysis JSON:
    {
      "profile":       { … },
      "repositories":  { … },
      "languages":     { … },
      "activity":      { … },
      "score":         { "score": int, "grade": str, "strengths": […], "weaknesses": […] }
    }

    404 – {"detail": "GitHub user '{username}' not found."}
    429 – {"detail": "GitHub API rate limit exceeded. Add a GITHUB_TOKEN env var."}
    502 – {"detail": "GitHub API error: …"}
    """
    #  1. Sanitise input 
    username = username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username must not be empty.")

    # GitHub usernames: 1–39 chars, alphanumeric + hyphens, no leading/trailing hyphen.
    import re
    if not re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,37}[a-zA-Z0-9])?$", username):
        raise HTTPException(status_code=400, detail=f"'{username}' is not a valid GitHub username.")

    #  2. Fetch data from GitHub 
    try:
        logger.info("Starting analysis for username='%s'", username)

        # Profile – if this returns None the user doesn't exist.
        profile = fetch_user_profile(username)
        if profile is None:
            raise HTTPException(
                status_code=404,
                detail=f"GitHub user '{username}' not found.",
            )

        # Repos and events – errors here are handled below.
        repos  = fetch_user_repos(username)
        events = fetch_recent_events(username)

    except HTTPException:
        raise  # Re-raise our own HTTP exceptions.

    except req_lib.HTTPError as exc:
        # Detect rate-limit specifically for a friendlier message.
        if exc.response is not None and exc.response.status_code == 403:
            raise HTTPException(
                status_code=429,
                detail=(
                    "GitHub API rate limit exceeded. "
                    "Set the GITHUB_TOKEN environment variable to increase your limit."
                ),
            )
        logger.exception("GitHub API HTTP error for user '%s'", username)
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")

    except req_lib.ConnectionError:
        logger.exception("Network error fetching data for '%s'", username)
        raise HTTPException(
            status_code=502,
            detail="Could not reach the GitHub API. Check your network connection.",
        )

    except req_lib.Timeout:
        logger.exception("Timeout fetching data for '%s'", username)
        raise HTTPException(status_code=504, detail="GitHub API request timed out. Try again.")

    except Exception as exc:
        logger.exception("Unexpected error analyzing '%s'", username)
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")

    #  3. Run analysis 
    result = run_full_analysis(profile, repos, events)

    logger.info(
        "Analysis complete for '%s' – score=%d grade=%s",
        username,
        result["score"]["score"],
        result["score"]["grade"],
    )

    return JSONResponse(content=result)
