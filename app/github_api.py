"""
app/github_api.py
─────────────────
Thin wrapper around the public GitHub REST API v3.
All network calls live here; no business logic.

Responsibilities
----------------
* Fetch user profile          → GET /users/{username}
* Fetch user repositories     → GET /users/{username}/repos  (paginated)
* Fetch recent public events  → GET /users/{username}/events/public
* Fetch per-repo language map → GET /repos/{owner}/{repo}/languages

Rate-limit note
───────────────
Unauthenticated requests are capped at 60 req/hour per IP.
Set the GITHUB_TOKEN environment variable to raise the limit to 5 000/hour.

    export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

The token is read once at module load time so the header dict is reused
across every request.
"""

import os
import logging
from typing import Optional

import requests

#  logging 
logger = logging.getLogger(__name__)

#  constants 
BASE_URL = "https://api.github.com"

# Maximum repositories to retrieve (GitHub caps individual pages at 100).
MAX_REPOS = 100

# Maximum pages of events to retrieve (30 events per page).
MAX_EVENT_PAGES = 3


def _build_headers() -> dict:
    """
    Construct request headers.
    Injects a Bearer token when GITHUB_TOKEN is present in the environment.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        logger.debug("GitHub token detected – using authenticated requests.")
    else:
        logger.debug("No GITHUB_TOKEN found – using unauthenticated requests (60 req/hr).")
    return headers


# Build headers once at import time; reused for every call.
_HEADERS = _build_headers()


#  helpers 

def _get(url: str, params: Optional[dict] = None) -> Optional[dict | list]:
    """
    Perform a GET request and return the parsed JSON body.

    Returns
    -------
    Parsed JSON (dict or list) on success.
    None if the resource was not found (404) or the user has no content (204).
    
    Raises
    ------
    requests.HTTPError  for non-404 HTTP errors (e.g. 403 rate-limited, 5xx).
    requests.RequestException for network-level failures.
    """
    try:
        response = requests.get(url, headers=_HEADERS, params=params, timeout=10)

        # User / resource not found – caller can decide what to do.
        if response.status_code == 404:
            logger.warning("Resource not found: %s", url)
            return None

        # No content (edge case for empty event streams).
        if response.status_code == 204:
            return []

        # Surface API errors (rate limits return 403 with a message body).
        if response.status_code == 403:
            body = response.json()
            message = body.get("message", "Unknown 403 error")
            logger.error("GitHub API 403: %s", message)
            raise requests.HTTPError(f"GitHub API error: {message}", response=response)

        response.raise_for_status()
        return response.json()

    except requests.Timeout:
        logger.error("Request timed out: %s", url)
        raise
    except requests.ConnectionError:
        logger.error("Connection error while reaching: %s", url)
        raise


#  public API 

def fetch_user_profile(username: str) -> Optional[dict]:
    """
    Fetch the public profile of a GitHub user.

    Parameters
    ----------
    username : GitHub login name (case-insensitive).

    Returns
    -------
    dict  – raw profile payload from GitHub, e.g.:
            {
              "login": "torvalds",
              "name": "Linus Torvalds",
              "public_repos": 6,
              "followers": 235000,
              "following": 0,
              "created_at": "2011-09-03T15:26:22Z",
              "bio": "...",
              "avatar_url": "...",
              ...
            }
    None  – if the user does not exist.
    """
    url = f"{BASE_URL}/users/{username}"
    logger.info("Fetching profile for '%s'", username)
    return _get(url)


def fetch_user_repos(username: str) -> list[dict]:
    """
    Fetch all public repositories for a user (up to MAX_REPOS).

    Uses sort=updated so the most recently touched repos come first,
    which gives better signal for activity analysis.

    Parameters
    ----------
    username : GitHub login name.

    Returns
    -------
    list[dict] – each dict is a repository object, e.g.:
                 {
                   "name": "linux",
                   "stargazers_count": 190000,
                   "forks_count": 56000,
                   "language": "C",
                   "description": "...",
                   "has_wiki": true,
                   "default_branch": "master",
                   ...
                 }
    """
    url = f"{BASE_URL}/users/{username}/repos"
    params = {
        "type": "owner",       # Only repos owned by the user, not org forks.
        "sort": "updated",
        "direction": "desc",
        "per_page": MAX_REPOS,
    }
    logger.info("Fetching repositories for '%s'", username)
    result = _get(url, params=params)
    return result if result else []


def fetch_recent_events(username: str) -> list[dict]:
    """
    Fetch recent public events (activity) for a user.

    GitHub returns up to 300 events (10 pages × 30 per page), but events
    older than 90 days are removed.  We collect MAX_EVENT_PAGES pages which
    is sufficient for activity scoring.

    Parameters
    ----------
    username : GitHub login name.

    Returns
    -------
    list[dict] – each dict is an event object, e.g.:
                 {
                   "type": "PushEvent",
                   "created_at": "2024-05-01T12:00:00Z",
                   "repo": {"name": "user/repo"},
                   "payload": { ... }
                 }
    """
    events: list[dict] = []
    for page in range(1, MAX_EVENT_PAGES + 1):
        url = f"{BASE_URL}/users/{username}/events/public"
        params = {"per_page": 30, "page": page}
        logger.info("Fetching events page %d for '%s'", page, username)
        page_data = _get(url, params=params)

        if not page_data:          # Empty page → no more events.
            break
        events.extend(page_data)

        if len(page_data) < 30:    # Partial page → last page reached.
            break

    return events


def fetch_repo_languages(owner: str, repo_name: str) -> dict[str, int]:
    """
    Fetch the language breakdown (in bytes) for a single repository.

    Parameters
    ----------
    owner     : Repository owner login.
    repo_name : Repository name.

    Returns
    -------
    dict[str, int] – mapping of language name → bytes of code, e.g.:
                     {"Python": 45230, "Shell": 1800}
    Empty dict on failure or if repo has no detected language.
    """
    url = f"{BASE_URL}/repos/{owner}/{repo_name}/languages"
    result = _get(url)
    return result if isinstance(result, dict) else {}
