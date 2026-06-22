"""
app/analyzer.py
───────────────
Core analysis engine.

Takes raw data from github_api.py and produces a structured
AnalysisResult dict that the API endpoint returns directly as JSON.

Pipeline
--------
    raw profile  ─┐
    raw repos    ─┼──► analyze_profile()     → profile section
                  ├──► analyze_repositories() → repos section
                  ├──► analyze_languages()    → languages section
    raw events   ─┼──► analyze_activity()    → activity section
                  └──► compute_score()        → score / strengths / weaknesses

No network calls are made here; all data arrives as plain Python objects.
"""

import logging
from datetime import datetime, timezone
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 – Profile Analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyze_profile(profile: dict) -> dict:
    """
    Extract high-level user profile statistics.

    Parameters
    ----------
    profile : Raw profile dict from GitHub API.

    Returns
    -------
    {
      "username":    str,
      "name":        str | None,
      "bio":         str | None,
      "avatar_url":  str,
      "profile_url": str,
      "location":    str | None,
      "blog":        str | None,
      "company":     str | None,
      "public_repos": int,
      "followers":   int,
      "following":   int,
      "account_age_days":  int,
      "account_created_at": str  (ISO 8601),
    }
    """
    created_at_str = profile.get("created_at", "")
    try:
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        account_age_days = (datetime.now(timezone.utc) - created_at).days
    except (ValueError, AttributeError):
        created_at = None
        account_age_days = 0

    return {
        "username":          profile.get("login", ""),
        "name":              profile.get("name"),
        "bio":               profile.get("bio"),
        "avatar_url":        profile.get("avatar_url", ""),
        "profile_url":       profile.get("html_url", ""),
        "location":          profile.get("location"),
        "blog":              profile.get("blog"),
        "company":           profile.get("company"),
        "public_repos":      profile.get("public_repos", 0),
        "followers":         profile.get("followers", 0),
        "following":         profile.get("following", 0),
        "account_age_days":  account_age_days,
        "account_created_at": created_at_str,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 – Repository Analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyze_repositories(repos: list[dict]) -> dict:
    """
    Compute aggregate repository statistics.

    Parameters
    ----------
    repos : List of raw repository dicts from GitHub API.

    Returns
    -------
    {
      "total_repos":          int,
      "total_stars":          int,
      "total_forks":          int,
      "avg_stars_per_repo":   float,
      "most_starred_repo":    { name, stars, url, description } | None,
      "most_forked_repo":     { name, forks, url, description } | None,
      "has_readme_count":     int,   # repos where description is non-empty (proxy)
      "forked_repo_count":    int,
      "original_repo_count":  int,
      "top_repos":            list[{ name, stars, forks, language, url }],
    }
    """
    if not repos:
        return _empty_repo_analysis()

    total_stars = sum(r.get("stargazers_count", 0) for r in repos)
    total_forks = sum(r.get("forks_count", 0) for r in repos)
    total_repos = len(repos)

    # Repos that have a non-empty description act as a documentation proxy.
    has_description_count = sum(1 for r in repos if r.get("description"))

    # Count repos that are forks of another repo.
    forked_repo_count  = sum(1 for r in repos if r.get("fork", False))
    original_repo_count = total_repos - forked_repo_count

    # Most starred / most forked.
    most_starred = max(repos, key=lambda r: r.get("stargazers_count", 0))
    most_forked  = max(repos, key=lambda r: r.get("forks_count", 0))

    def _repo_summary(repo: dict, metric_key: str, metric_label: str) -> dict:
        return {
            "name":        repo.get("name", ""),
            metric_label:  repo.get(metric_key, 0),
            "url":         repo.get("html_url", ""),
            "description": repo.get("description") or "No description provided.",
            "language":    repo.get("language"),
        }

    # Top 5 repos by stars for the frontend cards.
    top_repos = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:5]
    top_repos_summary = [
        {
            "name":     r.get("name", ""),
            "stars":    r.get("stargazers_count", 0),
            "forks":    r.get("forks_count", 0),
            "language": r.get("language"),
            "url":      r.get("html_url", ""),
        }
        for r in top_repos
    ]

    avg_stars = round(total_stars / total_repos, 2) if total_repos else 0.0

    return {
        "total_repos":          total_repos,
        "total_stars":          total_stars,
        "total_forks":          total_forks,
        "avg_stars_per_repo":   avg_stars,
        "most_starred_repo":    _repo_summary(most_starred, "stargazers_count", "stars"),
        "most_forked_repo":     _repo_summary(most_forked, "forks_count", "forks"),
        "has_description_count": has_description_count,
        "forked_repo_count":    forked_repo_count,
        "original_repo_count":  original_repo_count,
        "top_repos":            top_repos_summary,
    }


def _empty_repo_analysis() -> dict:
    return {
        "total_repos": 0, "total_stars": 0, "total_forks": 0,
        "avg_stars_per_repo": 0.0,
        "most_starred_repo": None, "most_forked_repo": None,
        "has_description_count": 0,
        "forked_repo_count": 0, "original_repo_count": 0,
        "top_repos": [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 – Language Analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyze_languages(repos: list[dict]) -> dict:
    """
    Derive language usage from each repository's `language` field.

    Note: GitHub's per-repo `language` field reports only the *primary*
    language. For a richer breakdown, you would call
    github_api.fetch_repo_languages() for each repo, but that costs one
    extra API request per repo and can exhaust unauthenticated rate limits.
    The primary-language approach is a good balance for a portfolio tool.

    Parameters
    ----------
    repos : List of raw repository dicts.

    Returns
    -------
    {
      "language_counts":      { "Python": 12, "JavaScript": 5, … },
      "language_percentages": { "Python": 63.2, "JavaScript": 26.3, … },
      "total_language_repos": int,   # repos with a detected language
      "unique_languages":     int,
      "primary_language":     str | None,
    }
    """
    language_counts: Counter = Counter()

    for repo in repos:
        lang = repo.get("language")
        if lang:
            language_counts[lang] += 1

    total = sum(language_counts.values())

    if total == 0:
        return {
            "language_counts": {},
            "language_percentages": {},
            "total_language_repos": 0,
            "unique_languages": 0,
            "primary_language": None,
        }

    language_percentages = {
        lang: round((count / total) * 100, 1)
        for lang, count in language_counts.most_common()
    }

    primary_language = language_counts.most_common(1)[0][0] if language_counts else None

    return {
        "language_counts":      dict(language_counts.most_common()),
        "language_percentages": language_percentages,
        "total_language_repos": total,
        "unique_languages":     len(language_counts),
        "primary_language":     primary_language,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 – Activity Analysis
# ═══════════════════════════════════════════════════════════════════════════

# Event types that signal active, meaningful contribution.
_CONTRIBUTION_EVENTS = {
    "PushEvent",
    "PullRequestEvent",
    "IssuesEvent",
    "CreateEvent",
    "IssueCommentEvent",
    "PullRequestReviewEvent",
    "CommitCommentEvent",
    "ReleaseEvent",
}


def analyze_activity(events: list[dict], repos: list[dict]) -> dict:
    """
    Derive activity metrics from public events and repo metadata.

    Parameters
    ----------
    events : List of raw event dicts from GitHub API.
    repos  : List of raw repository dicts (for updated_at timestamps).

    Returns
    -------
    {
      "total_events":            int,
      "contribution_events":     int,   # pushes, PRs, issues, etc.
      "event_type_breakdown":    { "PushEvent": 12, … },
      "push_event_count":        int,
      "recent_push_repos":       list[str],   # repos pushed to recently
      "days_since_last_activity": int | None,
      "is_recently_active":      bool,        # activity in last 30 days
      "recently_updated_repos":  int,         # repos updated in last 30 days
    }
    """
    if not events:
        return _empty_activity_analysis(repos)

    event_types: Counter = Counter(e.get("type", "Unknown") for e in events)
    contribution_count = sum(
        count for etype, count in event_types.items()
        if etype in _CONTRIBUTION_EVENTS
    )

    # Most recent event timestamp.
    days_since_last: int | None = None
    try:
        latest_event_str = events[0].get("created_at", "")
        if latest_event_str:
            latest_event = datetime.fromisoformat(latest_event_str.replace("Z", "+00:00"))
            days_since_last = (datetime.now(timezone.utc) - latest_event).days
    except (ValueError, AttributeError):
        pass

    is_recently_active = (days_since_last is not None and days_since_last <= 30)

    # Repos that received a push recently.
    recent_push_repos: list[str] = []
    for event in events:
        if event.get("type") == "PushEvent":
            repo_name = event.get("repo", {}).get("name", "")
            if repo_name and repo_name not in recent_push_repos:
                recent_push_repos.append(repo_name)
    recent_push_repos = recent_push_repos[:5]   # keep top 5

    # Repos updated within the last 30 days (from repo metadata).
    recently_updated_repos = _count_recently_updated_repos(repos, days=30)

    return {
        "total_events":             len(events),
        "contribution_events":      contribution_count,
        "event_type_breakdown":     dict(event_types.most_common()),
        "push_event_count":         event_types.get("PushEvent", 0),
        "recent_push_repos":        recent_push_repos,
        "days_since_last_activity": days_since_last,
        "is_recently_active":       is_recently_active,
        "recently_updated_repos":   recently_updated_repos,
    }


def _count_recently_updated_repos(repos: list[dict], days: int = 30) -> int:
    """Count repos whose `updated_at` timestamp falls within the last `days`."""
    count = 0
    now = datetime.now(timezone.utc)
    for repo in repos:
        updated_str = repo.get("updated_at", "")
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            if (now - updated).days <= days:
                count += 1
        except (ValueError, AttributeError):
            pass
    return count


def _empty_activity_analysis(repos: list[dict]) -> dict:
    recently_updated = _count_recently_updated_repos(repos, days=30)
    return {
        "total_events": 0, "contribution_events": 0,
        "event_type_breakdown": {}, "push_event_count": 0,
        "recent_push_repos": [],
        "days_since_last_activity": None,
        "is_recently_active": False,
        "recently_updated_repos": recently_updated,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5 – Portfolio Score (0–100)
# ═══════════════════════════════════════════════════════════════════════════

def compute_score(
    profile_data: dict,
    repo_data: dict,
    lang_data: dict,
    activity_data: dict,
) -> dict:
    """
    Calculate an overall portfolio score out of 100.

    Scoring Rubric
    ──────────────
    Category               Max pts  Notes
    ─────────────────────────────────────────────────────────────────────
    Followers & reach          15   log-scaled; 100 followers → ~10 pts
    Repository volume          10   more original repos → higher score
    Stars earned               15   log-scaled; 100 total stars → ~10 pts
    Documentation quality      15   % repos with descriptions
    Language diversity         10   unique languages across repos
    Recent activity            20   events + recency + updated repos
    Account maturity           10   account age in years
    Community engagement        5   following ≥ 5 and followers > 0
    ─────────────────────────────────────────────────────────────────────
    Total                     100
    """
    import math

    score = 0
    strengths: list[str] = []
    weaknesses: list[str] = []

    # ── 1. Followers & Reach (15 pts) ──────────────────────────────────
    followers = profile_data.get("followers", 0)
    if followers >= 500:
        pts = 15
    elif followers >= 100:
        pts = 10 + round(math.log10(followers / 100) * 5)
    elif followers >= 10:
        pts = 5 + round(math.log10(followers / 10) * 5)
    elif followers >= 1:
        pts = max(1, round(math.log10(followers + 1) * 5))
    else:
        pts = 0

    pts = min(pts, 15)
    score += pts

    if followers >= 100:
        strengths.append(f"Strong community reach with {followers:,} followers")
    elif followers >= 10:
        strengths.append(f"Growing follower base ({followers} followers)")
    else:
        weaknesses.append("Low follower count – consider sharing your work publicly")

    # ── 2. Repository Volume (10 pts) ───────────────────────────────────
    original_repos = repo_data.get("original_repo_count", 0)
    if original_repos >= 20:
        pts = 10
    elif original_repos >= 10:
        pts = 7
    elif original_repos >= 5:
        pts = 5
    elif original_repos >= 2:
        pts = 3
    else:
        pts = 1 if original_repos == 1 else 0

    score += pts

    if original_repos >= 15:
        strengths.append(f"Prolific creator with {original_repos} original repositories")
    elif original_repos >= 5:
        strengths.append(f"Solid portfolio of {original_repos} original repositories")
    elif original_repos == 0:
        weaknesses.append("No original repositories found – start building!")
    else:
        weaknesses.append(f"Only {original_repos} original repo(s) – create more to showcase skills")

    # ── 3. Stars Earned (15 pts) ────────────────────────────────────────
    total_stars = repo_data.get("total_stars", 0)
    if total_stars >= 1000:
        pts = 15
    elif total_stars >= 100:
        pts = 10 + round(math.log10(total_stars / 100) * 5)
    elif total_stars >= 10:
        pts = 5 + round(math.log10(total_stars / 10) * 5)
    elif total_stars >= 1:
        pts = max(1, round(math.log10(total_stars + 1) * 5))
    else:
        pts = 0

    pts = min(pts, 15)
    score += pts

    if total_stars >= 100:
        strengths.append(f"High community approval – {total_stars:,} total stars earned")
    elif total_stars >= 10:
        strengths.append(f"Work is gaining recognition ({total_stars} stars across repos)")
    else:
        weaknesses.append("Repositories have few stars – promote your work to gain visibility")

    # ── 4. Documentation Quality (15 pts) ───────────────────────────────
    total_repos = repo_data.get("total_repos", 0)
    desc_count  = repo_data.get("has_description_count", 0)
    doc_ratio   = desc_count / total_repos if total_repos else 0

    pts = round(doc_ratio * 15)
    score += pts

    if doc_ratio >= 0.8:
        strengths.append(f"Excellent documentation – {round(doc_ratio*100)}% of repos have descriptions")
    elif doc_ratio >= 0.5:
        strengths.append(f"Most repos are documented ({round(doc_ratio*100)}% have descriptions)")
    else:
        missing = total_repos - desc_count
        weaknesses.append(
            f"{missing} repo(s) lack a description – add READMEs and descriptions"
        )

    # ── 5. Language Diversity (10 pts) ──────────────────────────────────
    unique_langs = lang_data.get("unique_languages", 0)
    if unique_langs >= 5:
        pts = 10
    elif unique_langs >= 3:
        pts = 7
    elif unique_langs == 2:
        pts = 4
    elif unique_langs == 1:
        pts = 2
    else:
        pts = 0

    score += pts

    if unique_langs >= 5:
        strengths.append(f"Highly versatile – proficient in {unique_langs} programming languages")
    elif unique_langs >= 3:
        strengths.append(f"Diverse skill set covering {unique_langs} languages")
    elif unique_langs <= 1:
        weaknesses.append(
            "Limited language diversity – explore new languages to broaden your profile"
        )

    # ── 6. Recent Activity (20 pts) ─────────────────────────────────────
    contribution_events  = activity_data.get("contribution_events", 0)
    is_recently_active   = activity_data.get("is_recently_active", False)
    recently_updated_repos = activity_data.get("recently_updated_repos", 0)
    days_since_last      = activity_data.get("days_since_last_activity")

    pts = 0

    # Contribution events sub-score (up to 10 pts).
    if contribution_events >= 30:
        pts += 10
    elif contribution_events >= 15:
        pts += 7
    elif contribution_events >= 5:
        pts += 4
    elif contribution_events >= 1:
        pts += 2

    # Recency sub-score (up to 5 pts).
    if is_recently_active:
        pts += 5
    elif days_since_last is not None:
        if days_since_last <= 90:
            pts += 2

    # Recently updated repos sub-score (up to 5 pts).
    if recently_updated_repos >= 5:
        pts += 5
    elif recently_updated_repos >= 2:
        pts += 3
    elif recently_updated_repos >= 1:
        pts += 1

    pts = min(pts, 20)
    score += pts

    if is_recently_active and contribution_events >= 15:
        strengths.append(
            f"Very active contributor – {contribution_events} contribution events recently"
        )
    elif is_recently_active:
        strengths.append("Recently active on GitHub")
    elif days_since_last is None or days_since_last > 90:
        weaknesses.append("No recent public activity – commit and contribute more regularly")
    else:
        weaknesses.append(f"Low recent activity (last event {days_since_last} days ago)")

    # ── 7. Account Maturity (10 pts) ────────────────────────────────────
    age_days = profile_data.get("account_age_days", 0)
    age_years = age_days / 365

    if age_years >= 5:
        pts = 10
    elif age_years >= 3:
        pts = 7
    elif age_years >= 1:
        pts = 4
    elif age_years >= 0.5:
        pts = 2
    else:
        pts = 1

    score += pts

    if age_years >= 5:
        strengths.append(f"Established GitHub presence ({int(age_years)} years on the platform)")
    elif age_years >= 2:
        strengths.append(f"Solid GitHub tenure ({int(age_years)} years)")
    else:
        weaknesses.append("Account is relatively new – consistency over time will strengthen the score")

    # ── 8. Community Engagement (5 pts) ─────────────────────────────────
    following = profile_data.get("following", 0)
    if following >= 5 and followers >= 1:
        pts = 5
        strengths.append("Actively engaged with the developer community")
    elif following >= 1:
        pts = 2
    else:
        pts = 0
        weaknesses.append("Not following other developers – engage with the community")

    score += pts

    # ── Final ────────────────────────────────────────────────────────────
    score = max(0, min(100, score))   # clamp to [0, 100]
    grade = _score_to_grade(score)

    return {
        "score":      score,
        "grade":      grade,
        "strengths":  strengths,
        "weaknesses": weaknesses,
    }


def _score_to_grade(score: int) -> str:
    """Map numeric score to a letter grade."""
    if score >= 90: return "S"
    if score >= 80: return "A"
    if score >= 65: return "B"
    if score >= 50: return "C"
    if score >= 35: return "D"
    return "F"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6 – Top-level Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def run_full_analysis(
    profile: dict,
    repos: list[dict],
    events: list[dict],
) -> dict[str, Any]:
    """
    Orchestrate all analysis steps and return a single unified result dict.

    This is the only function main.py needs to call.

    Parameters
    ----------
    profile : Raw profile dict from github_api.fetch_user_profile()
    repos   : Raw repo list from github_api.fetch_user_repos()
    events  : Raw event list from github_api.fetch_recent_events()

    Returns
    -------
    {
      "profile":    { … },
      "repositories": { … },
      "languages":  { … },
      "activity":   { … },
      "score":      { score, grade, strengths, weaknesses }
    }
    """
    logger.info("Running full analysis for '%s'", profile.get("login", "unknown"))

    profile_data  = analyze_profile(profile)
    repo_data     = analyze_repositories(repos)
    lang_data     = analyze_languages(repos)
    activity_data = analyze_activity(events, repos)
    score_data    = compute_score(profile_data, repo_data, lang_data, activity_data)

    return {
        "profile":      profile_data,
        "repositories": repo_data,
        "languages":    lang_data,
        "activity":     activity_data,
        "score":        score_data,
    }
