from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "murali-yandra")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


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
    payload = json.dumps(
        {
            "query": query,
            "variables": {
                "login": OWNER,
                "from": datetime.combine(start, datetime.min.time(), timezone.utc).isoformat(),
                "to": datetime.combine(today, datetime.max.time(), timezone.utc).isoformat(),
            },
        }
    ).encode()
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

    days: list[dict[str, object]] = []
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    for week in weeks:
        for item in week["contributionDays"]:
            days.append({"date": item["date"], "count": int(item["contributionCount"])})
    return days


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


def streaks(days: list[dict[str, object]]) -> tuple[int, int, int]:
    counts = {date.fromisoformat(str(day["date"])): int(day["count"]) for day in days}
    today = datetime.now(timezone.utc).date()
    cursor = today
    if counts.get(cursor, 0) == 0 and counts.get(cursor - timedelta(days=1), 0) > 0:
        cursor -= timedelta(days=1)

    current = 0
    while counts.get(cursor, 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    for day in sorted(counts):
        if counts[day] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    one_year_ago = today - timedelta(days=365)
    total = sum(count for day, count in counts.items() if day >= one_year_ago)
    return current, longest, total


def write_streak_svg(days: list[dict[str, object]]) -> None:
    current, longest, total = streaks(days)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="520" height="180" viewBox="0 0 520 180" role="img" aria-labelledby="title desc">
  <title id="title">GitHub streaks</title>
  <desc id="desc">Current streak {current} days, longest streak {longest} days, total contributions {total} in the last year.</desc>
  <rect width="520" height="180" rx="18" fill="#0d1117"/>
  <rect x="1" y="1" width="518" height="178" rx="18" fill="none" stroke="#30363d"/>
  <text x="28" y="42" fill="#e6edf3" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="800">GitHub Streaks</text>
  <g transform="translate(28 78)">
    <rect width="135" height="58" rx="12" fill="#161b22" stroke="#30363d"/>
    <text x="18" y="25" fill="#39d353" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="800">{current}</text>
    <text x="18" y="45" fill="#c9d1d9" font-family="Segoe UI, Arial, sans-serif" font-size="12">Current streak</text>
    <rect x="154" width="135" height="58" rx="12" fill="#161b22" stroke="#30363d"/>
    <text x="172" y="25" fill="#58a6ff" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="800">{longest}</text>
    <text x="172" y="45" fill="#c9d1d9" font-family="Segoe UI, Arial, sans-serif" font-size="12">Longest streak</text>
    <rect x="308" width="155" height="58" rx="12" fill="#161b22" stroke="#30363d"/>
    <text x="326" y="25" fill="#a371f7" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="800">{total}</text>
    <text x="326" y="45" fill="#c9d1d9" font-family="Segoe UI, Arial, sans-serif" font-size="12">Contributions</text>
  </g>
  <text x="28" y="166" fill="#6e7681" font-family="Segoe UI, Arial, sans-serif" font-size="11">Updated {updated}</text>
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
    write_streak_svg(days)
    write_catapult_svg(days)


if __name__ == "__main__":
    main()
