#!/usr/bin/env python3
"""Generate first-party GitHub profile visuals from the official GitHub REST API.

Only public account/repository metadata and public events are used. This deliberately
does not label public events as contribution counts or claim private contributions.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

USERNAME = "shamimwhois"
API = "https://api.github.com"
OUT = Path("assets/github-stats")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "shamimwhois-profile-stats",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def api(path: str):
    request = urllib.request.Request(API + path, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API {exc.code} for {path}: {body[:300]}") from exc


def svg_start(width: int, height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
        f'<title id="title">{escape(title)}</title>'
        f'<desc id="desc">Generated from the official GitHub REST API for @{USERNAME}.</desc>'
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#10243a"/><stop offset="1" stop-color="#091522"/>'
        '</linearGradient><linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#66e6c4"/><stop offset="1" stop-color="#83c5ff"/>'
        '</linearGradient></defs>'
        '<rect width="100%" height="100%" rx="22" fill="url(#bg)"/>'
        '<rect x="1" y="1" width="1098" height="calc(100% - 2px)" '
        'rx="21" fill="none" stroke="#29445c"/>'
    )


def text(x, y, value, size=16, color="#edf4fb", weight=500, extra=""):
    return (f'<text x="{x}" y="{y}" fill="{color}" font-family="Inter,Segoe UI,Arial,sans-serif" '
            f'font-size="{size}" font-weight="{weight}" {extra}>{escape(str(value))}</text>')


def write_svg(name: str, content: str):
    (OUT / name).write_text(content + "</svg>\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    user = api(f"/users/{USERNAME}")
    repos = []
    page = 1
    while True:
        batch = api(f"/users/{USERNAME}/repos?type=owner&sort=updated&per_page=100&page={page}")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    # Only non-fork public repositories owned by the profile are used in repo metrics.
    owned = [r for r in repos if not r.get("fork", False) and not r.get("archived", False)]
    languages = Counter(r.get("language") for r in owned if r.get("language"))
    stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
    forks = sum(int(r.get("forks_count") or 0) for r in repos)

    events = api(f"/users/{USERNAME}/events/public?per_page=100")
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=29)).date()
    daily = Counter()
    for event in events:
        stamp = event.get("created_at")
        if not stamp:
            continue
        day = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
        if start <= day <= now.date():
            daily[day.isoformat()] += 1
    days = [(start + timedelta(days=i)).isoformat() for i in range(30)]
    event_total = sum(daily.values())

    data = {
        "generated_at": now.isoformat(timespec="seconds"),
        "username": USERNAME,
        "source": "GitHub REST API",
        "scope": "public profile, public repositories, and public events",
        "profile": {
            "public_repositories": user.get("public_repos", 0),
            "followers": user.get("followers", 0),
            "following": user.get("following", 0),
            "public_gists": user.get("public_gists", 0),
        },
        "repositories": {
            "non_fork_non_archived": len(owned),
            "stars_across_public_repositories": stars,
            "forks_across_public_repositories": forks,
            "primary_language_repository_counts": dict(languages.most_common()),
        },
        "public_events": {
            "window_days": 30,
            "returned_events_in_window": event_total,
            "api_note": "GitHub Events API is capped and is not a complete contribution history.",
            "daily_counts": [{"date": day, "events": daily[day]} for day in days],
        },
    }
    (OUT / "stats.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # Overview: counters are directly sourced from the GitHub user and repository API.
    s = [svg_start(1100, 250, "GitHub public profile overview")]
    s += [text(38, 48, f"@{USERNAME}  /  PUBLIC PROFILE OVERVIEW", 13, "#66e6c4", 750)]
    s += [text(38, 79, "Live data from the GitHub REST API", 22, "#edf4fb", 700)]
    cards = [
        ("PUBLIC REPOSITORIES", user.get("public_repos", 0)),
        ("FOLLOWERS", user.get("followers", 0)),
        ("TOTAL PUBLIC STARS", stars),
        ("TOTAL PUBLIC FORKS", forks),
    ]
    for i, (label, value) in enumerate(cards):
        x = 38 + i * 263
        s.append(f'<rect x="{x}" y="112" width="242" height="94" rx="14" fill="#142c43" stroke="#29445c"/>')
        s.append(text(x + 17, 145, label, 11, "#9aacc0", 700))
        s.append(text(x + 17, 184, f"{value:,}", 30, "#edf4fb", 750))
    s.append(text(38, 231, f"Updated {now.strftime('%Y-%m-%d %H:%M UTC')}  ·  Public data only", 11, "#9aacc0"))
    write_svg("overview.svg", "".join(s))

    # Language chart counts repositories by GitHub's primary language (not code bytes).
    s = [svg_start(1100, 360, "Primary languages across public repositories")]
    s += [text(38, 48, "REPOSITORY LANGUAGE MIX", 13, "#66e6c4", 750)]
    s += [text(38, 79, "Count of repositories by primary language", 22, "#edf4fb", 700)]
    top = languages.most_common(8)
    total = sum(languages.values()) or 1
    palette = ["#66e6c4", "#83c5ff", "#a78bfa", "#f6bd60", "#f28482", "#84a59d", "#cdb4db", "#90be6d"]
    if not top:
        s.append(text(38, 145, "No public repository language data returned.", 15, "#9aacc0"))
    for i, (language, count) in enumerate(top):
        y = 126 + i * 28
        s.append(text(40, y + 14, language, 13, "#d9e6f2", 600))
        s.append(f'<rect x="230" y="{y}" width="700" height="13" rx="6" fill="#20384e"/>')
        s.append(f'<rect x="230" y="{y}" width="{max(3, 700 * count / max(c for _, c in top)):.1f}" height="13" rx="6" fill="{palette[i % len(palette)]}"/>')
        s.append(text(955, y + 13, f"{count} repos  ·  {count / total * 100:.1f}%", 12, "#9aacc0", 600))
    s.append(text(38, 338, f"Based on {len(owned)} non-fork, non-archived public repositories · GitHub API primary-language field", 10, "#9aacc0"))
    write_svg("languages.svg", "".join(s))

    # Public event chart is explicitly labelled as events, never as contributions.
    s = [svg_start(1100, 330, "Public GitHub events in the latest 30 days")]
    s += [text(38, 48, "PUBLIC ACTIVITY / LAST 30 DAYS", 13, "#66e6c4", 750)]
    s += [text(38, 79, f"{event_total:,} public events returned by GitHub", 22, "#edf4fb", 700)]
    max_value = max(daily.values(), default=1) or 1
    base_y, chart_h, bar_w, gap = 255, 135, 20, 15
    for i, day in enumerate(days):
        count = daily[day]
        height = chart_h * count / max_value if count else 2
        x = 40 + i * (bar_w + gap)
        y = base_y - height
        s.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{height:.1f}" rx="5" fill="url(#accent)" opacity="{0.35 + (0.65 * count / max_value if count else 0.08):.2f}"/>')
    s.append(text(40, 282, start.isoformat(), 10, "#9aacc0"))
    s.append(text(930, 282, now.date().isoformat(), 10, "#9aacc0"))
    s.append(text(38, 311, "Events API is capped at 100 recent events; this is not a complete contribution calendar or streak.", 10, "#9aacc0"))
    write_svg("activity.svg", "".join(s))

    print(f"Generated profile visuals for @{USERNAME}: {len(repos)} repos fetched, {event_total} recent public events.")
    print(f"API rate limit remaining: {api('/rate_limit')['rate']['remaining']}")


if __name__ == "__main__":
    main()
