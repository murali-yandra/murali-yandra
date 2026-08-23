from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "murali-yandra")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


@dataclass(frozen=True)
class StreakSummary:
    current: int
    current_end: date | None
    longest: int
    longest_start: date | None
    longest_end: date | None


@dataclass(frozen=True)
class UserStats:
    public_repos: int
    total_stars: int
    followers: int
    following: int
    account_created: date
    top_languages: list[tuple[str, int]]


def graphql_request(query: str, variables: dict[str, object]) -> dict[str, object]:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "murali-yandra-profile-artifacts",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode())
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"]))
    return data


def fetch_contribution_days() -> list[dict[str, object]]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=370)

    if not TOKEN:
        return [{"date": (start + timedelta(days=i)).isoformat(), "count": 0} for i in range(371)]

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    data = graphql_request(
        query,
        {
            "login": OWNER,
            "from": datetime.combine(start, datetime.min.time(), timezone.utc).isoformat(),
            "to": datetime.combine(today, datetime.max.time(), timezone.utc).isoformat(),
        },
    )

    days: list[dict[str, object]] = []
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    for week in weeks:
        for item in week["contributionDays"]:
            days.append({"date": item["date"], "count": int(item["contributionCount"])})
    return days


def fetch_lifetime_contributions() -> tuple[int | None, str]:
    if not TOKEN:
        return None, "GitHub Action refreshes this"

    years_query = """
    query($login: String!) {
      user(login: $login) {
        createdAt
        contributionsCollection {
          contributionYears
        }
      }
    }
    """
    years_data = graphql_request(years_query, {"login": OWNER})
    user = years_data["data"]["user"]
    years = sorted(int(year) for year in user["contributionsCollection"]["contributionYears"])
    if not years:
        return 0, "No contributions yet"

    today = datetime.now(timezone.utc).date()
    total = 0
    total_query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
          }
        }
      }
    }
    """
    for year in years:
        start = date(year, 1, 1)
        end = today if year == today.year else date(year, 12, 31)
        data = graphql_request(
            total_query,
            {
                "login": OWNER,
                "from": datetime.combine(start, datetime.min.time(), timezone.utc).isoformat(),
                "to": datetime.combine(end, datetime.max.time(), timezone.utc).isoformat(),
            },
        )
        total += int(
            data["data"]["user"]["contributionsCollection"]["contributionCalendar"][
                "totalContributions"
            ]
        )

    created_at = datetime.fromisoformat(str(user["createdAt"]).replace("Z", "+00:00")).date()
    return total, f"{format_full_date(created_at)} - Present"


def fetch_user_stats() -> UserStats:
    if not TOKEN:
        return UserStats(0, 0, 0, 0, datetime.now(timezone.utc).date(), [])

    query = """
    query($login: String!) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        following { totalCount }
        repositories(ownerAffiliations: OWNER, first: 100, privacy: PUBLIC, orderBy: {field: STARGAZERS, direction: DESC}) {
          totalCount
          nodes {
            stargazerCount
            languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node { name color }
              }
            }
          }
        }
      }
    }
    """
    data = graphql_request(query, {"login": OWNER})
    user = data["data"]["user"]

    total_stars = sum(repo["stargazerCount"] for repo in user["repositories"]["nodes"])
    created_at = datetime.fromisoformat(str(user["createdAt"]).replace("Z", "+00:00")).date()

    lang_sizes: dict[str, int] = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            lang_sizes[name] = lang_sizes.get(name, 0) + edge["size"]

    top_languages = sorted(lang_sizes.items(), key=lambda x: x[1], reverse=True)[:5]

    return UserStats(
        public_repos=user["repositories"]["totalCount"],
        total_stars=total_stars,
        followers=user["followers"]["totalCount"],
        following=user["following"]["totalCount"],
        account_created=created_at,
        top_languages=top_languages,
    )


LANG_COLORS: dict[str, str] = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Shell": "#89e051",
    "SQL": "#e38c00",
    "HCL": "#844fba",
    "Dockerfile": "#384d54",
    "Makefile": "#427819",
    "Jinja": "#a52a22",
    "PLpgSQL": "#336790",
}


def color_for(count: int) -> str:
    if count <= 0:
        return "#161b22"
    if count <= 3:
        return "#0e4429"
    if count <= 7:
        return "#006d32"
    if count <= 14:
        return "#26a641"
    return "#39d353"


def format_full_date(value: date) -> str:
    return f"{value:%b} {value.day}, {value.year}"


def format_compact_date(value: date | None) -> str:
    if not value:
        return "No streak yet"
    return f"{value:%b} {value.day}"


def format_date_range(start: date | None, end: date | None) -> str:
    if not start or not end:
        return "No streak yet"
    if start == end:
        return format_full_date(start)
    return f"{format_full_date(start)} - {format_full_date(end)}"


def format_number(value: int | None) -> str:
    if value is None:
        return "--"
    return f"{value:,}"


def streaks(days: list[dict[str, object]]) -> StreakSummary:
    counts = {date.fromisoformat(str(day["date"])): int(day["count"]) for day in days}
    today = datetime.now(timezone.utc).date()
    cursor = today
    if counts.get(cursor, 0) == 0 and counts.get(cursor - timedelta(days=1), 0) > 0:
        cursor -= timedelta(days=1)

    current = 0
    current_end = cursor if counts.get(cursor, 0) > 0 else None
    while counts.get(cursor, 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    run_start: date | None = None
    longest_start: date | None = None
    longest_end: date | None = None
    for day in sorted(counts):
        if counts[day] > 0:
            if run == 0:
                run_start = day
            run += 1
            if run > longest:
                longest = run
                longest_start = run_start
                longest_end = day
        else:
            run = 0
            run_start = None

    return StreakSummary(current, current_end, longest, longest_start, longest_end)


def contributions_this_month(days: list[dict[str, object]]) -> int:
    today = datetime.now(timezone.utc).date()
    first_of_month = today.replace(day=1)
    return sum(
        int(day["count"])
        for day in days
        if date.fromisoformat(str(day["date"])) >= first_of_month
    )


def write_stats_svg(stats: UserStats) -> None:
    today = datetime.now(timezone.utc).date()
    account_age_days = (today - stats.account_created).days
    if account_age_days >= 365:
        years = account_age_days // 365
        age_text = f"{years} year{'s' if years != 1 else ''}"
    else:
        months = account_age_days // 30
        age_text = f"{months} month{'s' if months != 1 else ''}"

    total_lang_size = sum(size for _, size in stats.top_languages) or 1
    lang_bars = []
    lang_labels = []
    bar_x = 0
    bar_width_total = 230
    for i, (lang, size) in enumerate(stats.top_languages):
        pct = size / total_lang_size
        w = max(pct * bar_width_total, 2)
        color = LANG_COLORS.get(lang, "#8b949e")
        lang_bars.append(
            f'<rect x="{bar_x:.1f}" y="0" width="{w:.1f}" height="8" rx="1" fill="{color}"/>'
        )
        lang_labels.append(
            f'<g transform="translate({i * 90}, 0)">'
            f'<circle r="4" cx="4" cy="4" fill="{color}"/>'
            f'<text x="12" y="8" fill="#8b949e" font-size="11" '
            f'font-family="Segoe UI, Arial, sans-serif">{lang} {pct:.0%}</text>'
            f'</g>'
        )
        bar_x += w

    lang_bar_svg = "\n    ".join(lang_bars)
    lang_label_rows = []
    for row_start in range(0, len(lang_labels), 3):
        row_items = lang_labels[row_start:row_start + 3]
        y_offset = (row_start // 3) * 20
        lang_label_rows.append(
            f'<g transform="translate(0, {y_offset})">'
            + "".join(row_items)
            + '</g>'
        )
    lang_labels_svg = "\n    ".join(lang_label_rows)
    label_rows_count = (len(stats.top_languages) + 2) // 3
    label_block_height = label_rows_count * 20

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="340" height="{180 + label_block_height}" viewBox="0 0 340 {180 + label_block_height}" role="img" aria-labelledby="stats-title stats-desc">
  <title id="stats-title">GitHub Stats</title>
  <desc id="stats-desc">{stats.public_repos} public repos, {stats.total_stars} stars, {stats.followers} followers, on GitHub for {age_text}.</desc>
  <rect width="340" height="{180 + label_block_height}" rx="8" fill="#010409"/>
  <rect x="10" y="10" width="320" height="{160 + label_block_height}" rx="6" fill="#0d1117"/>
  <text x="170" y="40" text-anchor="middle" fill="#f0f6fc" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="800">GitHub Stats</text>
  <g font-family="Segoe UI, Arial, sans-serif" transform="translate(30, 60)">
    <g>
      <text fill="#8b949e" font-size="13">Public Repos</text>
      <text x="200" fill="#58a6ff" font-size="13" font-weight="700" text-anchor="end">{stats.public_repos}</text>
    </g>
    <g transform="translate(0, 24)">
      <text fill="#8b949e" font-size="13">Total Stars</text>
      <text x="200" fill="#58a6ff" font-size="13" font-weight="700" text-anchor="end">{stats.total_stars}</text>
    </g>
    <g transform="translate(0, 48)">
      <text fill="#8b949e" font-size="13">Followers</text>
      <text x="200" fill="#58a6ff" font-size="13" font-weight="700" text-anchor="end">{stats.followers}</text>
    </g>
    <g transform="translate(0, 72)">
      <text fill="#8b949e" font-size="13">On GitHub for</text>
      <text x="200" fill="#58a6ff" font-size="13" font-weight="700" text-anchor="end">{age_text}</text>
    </g>
  </g>
  <g transform="translate(55, 148)">
    {lang_bar_svg}
  </g>
  <g transform="translate(30, {166})">
    {lang_labels_svg}
  </g>
</svg>
"""
    output = ROOT / "assets" / "generated" / "stats.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def write_streak_svg(
    days: list[dict[str, object]], lifetime_total: int | None, contribution_range: str
) -> None:
    summary = streaks(days)
    monthly = contributions_this_month(days)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_display = format_number(lifetime_total)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="175" viewBox="0 0 480 175" role="img" aria-labelledby="title desc">
  <title id="title">Contribution Stats</title>
  <desc id="desc">Lifetime contributions {total_display}, this month {monthly}, current streak {summary.current} days. Updated {updated}.</desc>
  <defs>
    <linearGradient id="fire" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#ff3b30"/>
      <stop offset="0.55" stop-color="#ff7a00"/>
      <stop offset="1" stop-color="#ffd166"/>
    </linearGradient>
  </defs>
  <rect width="480" height="175" rx="8" fill="#010409"/>
  <rect x="8" y="8" width="464" height="159" rx="6" fill="#0d1117"/>
  <text x="240" y="32" text-anchor="middle" fill="#f0f6fc" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="800">Contribution Stats</text>
  <line x1="164" y1="48" x2="164" y2="145" stroke="#21262d" stroke-width="1"/>
  <line x1="320" y1="48" x2="320" y2="145" stroke="#21262d" stroke-width="1"/>
  <g font-family="Segoe UI, Arial, sans-serif" text-anchor="middle">
    <text x="86" y="80" fill="#58a6ff" font-size="28" font-weight="800">{total_display}</text>
    <text x="86" y="104" fill="#f0f6fc" font-size="12" font-weight="700">Total Contributions</text>
    <text x="86" y="124" fill="#8b949e" font-size="10">{contribution_range}</text>
  </g>
  <g font-family="Segoe UI, Arial, sans-serif" text-anchor="middle">
    <text x="242" y="80" fill="#58a6ff" font-size="28" font-weight="800">{monthly}</text>
    <text x="242" y="104" fill="#f0f6fc" font-size="12" font-weight="700">This Month</text>
    <text x="242" y="124" fill="#8b949e" font-size="10">{datetime.now(timezone.utc).strftime("%B %Y")}</text>
  </g>
  <g font-family="Segoe UI, Arial, sans-serif" text-anchor="middle">
    <circle cx="400" cy="70" r="22" fill="none" stroke="#21262d" stroke-width="3"/>
    <circle cx="400" cy="70" r="22" fill="none" stroke="url(#fire)" stroke-width="3.5" stroke-linecap="round"/>
    <text x="400" y="78" fill="#f0f6fc" font-size="18" font-weight="800">{summary.current}</text>
    <text x="400" y="104" fill="#f0f6fc" font-size="12" font-weight="700">Current Streak</text>
    <text x="400" y="124" fill="#8b949e" font-size="10">{format_compact_date(summary.current_end)}</text>
  </g>
  <text x="240" y="158" text-anchor="middle" fill="#484f58" font-family="Segoe UI, Arial, sans-serif" font-size="9">Longest: {summary.longest} days ({format_date_range(summary.longest_start, summary.longest_end)})</text>
</svg>
"""
    output = ROOT / "assets" / "generated" / "streak.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def write_catapult_svg(days: list[dict[str, object]]) -> None:
    recent = days[-35:]
    cells = []
    row_labels = []
    for index, day in enumerate(recent):
        col = index % 7
        row = index // 7
        count = int(day["count"])
        if col == 0:
            start_date = date.fromisoformat(str(day["date"]))
            end_date = date.fromisoformat(str(recent[min(index + 6, len(recent) - 1)]["date"]))
            if start_date.month == end_date.month:
                label = f"{start_date:%b} {start_date:%d}-{end_date:%d}"
            else:
                label = f"{start_date:%b} {start_date:%d}-{end_date:%b} {end_date:%d}"
            row_labels.append(
                f'<text x="-14" y="{row * 27 + 14}" text-anchor="end" fill="#64748b" '
                f'font-family="Segoe UI, Arial, sans-serif" font-size="9">{label}</text>'
            )
        cells.append(
            f'<rect x="{col * 27}" y="{row * 27}" width="19" height="19" rx="4" fill="{color_for(count)}">'
            f"<title>{day['date']}: {count} contributions</title></rect>"
        )
    total_recent = sum(int(day["count"]) for day in recent)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="260" viewBox="0 0 900 260" role="img" aria-labelledby="title desc">
  <title id="title">Contribution Catapult</title>
  <desc id="desc">A generated catapult animation using recent GitHub contribution counts.</desc>
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#020617"/><stop offset="1" stop-color="#0f172a"/></linearGradient>
    <filter id="glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <rect width="900" height="260" rx="18" fill="url(#bg)"/>
  <rect x="1" y="1" width="898" height="258" rx="18" fill="none" stroke="#1e293b"/>
  <text x="36" y="46" fill="#e2e8f0" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="800">Contribution Catapult</text>
  <text x="36" y="72" fill="#94a3b8" font-family="Segoe UI, Arial, sans-serif" font-size="14">Committing daily, small steps for steady progress.</text>
  <text x="36" y="94" fill="#64748b" font-family="Segoe UI, Arial, sans-serif" font-size="12">Last 35 days: {total_recent} contributions. Updated {updated}.</text>
  <g transform="translate(92 154)">
    <line x1="0" y1="54" x2="180" y2="54" stroke="#334155" stroke-width="8" stroke-linecap="round"/>
    <circle cx="46" cy="54" r="18" fill="#475569"/><circle cx="46" cy="54" r="8" fill="#94a3b8"/>
    <circle cx="132" cy="54" r="18" fill="#475569"/><circle cx="132" cy="54" r="8" fill="#94a3b8"/>
    <line x1="60" y1="46" x2="130" y2="-14" stroke="#38bdf8" stroke-width="10" stroke-linecap="round">
      <animateTransform attributeName="transform" type="rotate" values="0 60 46; -14 60 46; 0 60 46" dur="2.4s" repeatCount="indefinite"/>
    </line>
    <path d="M42 54 92 18 146 54" fill="none" stroke="#64748b" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
  <g filter="url(#glow)">
    <circle r="8" fill="#39d353"><animateMotion dur="2.4s" repeatCount="indefinite" path="M224 136 C330 40, 470 22, 610 86"/><animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.08;0.72;1" dur="2.4s" repeatCount="indefinite"/></circle>
    <circle r="6" fill="#58a6ff"><animateMotion dur="2.4s" begin=".32s" repeatCount="indefinite" path="M224 136 C330 55, 500 44, 650 116"/><animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.08;0.72;1" dur="2.4s" begin=".32s" repeatCount="indefinite"/></circle>
    <circle r="7" fill="#a371f7"><animateMotion dur="2.4s" begin=".64s" repeatCount="indefinite" path="M224 136 C360 70, 520 64, 690 146"/><animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.08;0.72;1" dur="2.4s" begin=".64s" repeatCount="indefinite"/></circle>
  </g>
  <g transform="translate(610 76)">
    <text x="0" y="-20" fill="#e2e8f0" font-family="Segoe UI, Arial, sans-serif" font-size="15" font-weight="700">recent contribution grid</text>
    {"".join(row_labels)}
    {"".join(cells)}
  </g>
</svg>
"""
    output = ROOT / "assets" / "animations" / "contribution-catapult.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def main() -> None:
    days = fetch_contribution_days()
    lifetime_total, contribution_range = fetch_lifetime_contributions()
    stats = fetch_user_stats()
    write_stats_svg(stats)
    write_streak_svg(days, lifetime_total, contribution_range)
    write_catapult_svg(days)


if __name__ == "__main__":
    main()
