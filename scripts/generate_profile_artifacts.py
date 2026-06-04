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


def write_streak_svg(
    days: list[dict[str, object]], lifetime_total: int | None, contribution_range: str
) -> None:
    summary = streaks(days)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_display = format_number(lifetime_total)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="520" height="220" viewBox="0 0 520 220" role="img" aria-labelledby="title desc">
  <title id="title">GitHub Streak</title>
  <desc id="desc">Lifetime contributions {total_display}, current streak {summary.current} days, longest streak {summary.longest} days. Updated {updated}.</desc>
  <defs>
    <linearGradient id="fire" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#ff3b30"/>
      <stop offset="0.55" stop-color="#ff7a00"/>
      <stop offset="1" stop-color="#ffd166"/>
    </linearGradient>
  </defs>
  <rect width="520" height="220" rx="8" fill="#010409"/>
  <text x="260" y="40" text-anchor="middle" fill="#f0f6fc" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="800">GitHub Streak</text>
  <rect x="10" y="66" width="500" height="132" rx="6" fill="#0d1117"/>
  <line x1="178" y1="88" x2="178" y2="176" stroke="#d0d7de" stroke-width="1.5"/>
  <line x1="342" y1="88" x2="342" y2="176" stroke="#d0d7de" stroke-width="1.5"/>
  <g font-family="Segoe UI, Arial, sans-serif" text-anchor="middle">
    <text x="94" y="116" fill="#58a6ff" font-size="26" font-weight="800">{total_display}</text>
    <text x="94" y="146" fill="#f0f6fc" font-size="13" font-weight="700">Total Contributions</text>
    <text x="94" y="174" fill="#8b949e" font-size="11">{contribution_range}</text>
  </g>
  <g font-family="Segoe UI, Arial, sans-serif" text-anchor="middle">
    <circle cx="260" cy="116" r="41" fill="none" stroke="#21262d" stroke-width="5"/>
    <circle cx="260" cy="116" r="41" fill="none" stroke="url(#fire)" stroke-width="6" stroke-linecap="round"/>
    <g transform="translate(250 75)">
      <path d="M10 24C2 18 3 10 9 2c1 7 8 7 8 14 3-2 5-6 3-11 8 8 9 17 2 23-4 3-9 2-12-4Z" fill="#ff5a1f"/>
      <path d="M12 25c-4-4-3-9 1-14 1 5 5 5 5 9 2-1 3-4 2-7 5 5 6 10 1 14-3 2-7 1-9-2Z" fill="#ffd166"/>
    </g>
    <text x="260" y="125" fill="#f0f6fc" font-size="30" font-weight="800">{summary.current}</text>
    <text x="260" y="168" fill="#f0f6fc" font-size="13" font-weight="800">Current Streak</text>
    <text x="260" y="190" fill="#8b949e" font-size="11">{format_compact_date(summary.current_end)}</text>
  </g>
  <g font-family="Segoe UI, Arial, sans-serif" text-anchor="middle">
    <text x="426" y="116" fill="#58a6ff" font-size="26" font-weight="800">{summary.longest}</text>
    <text x="426" y="146" fill="#f0f6fc" font-size="13" font-weight="700">Longest Streak</text>
    <text x="426" y="174" fill="#8b949e" font-size="11">{format_date_range(summary.longest_start, summary.longest_end)}</text>
  </g>
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
    write_streak_svg(days, lifetime_total, contribution_range)
    write_catapult_svg(days)


if __name__ == "__main__":
    main()
