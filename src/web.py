#!/usr/bin/env python3
"""Local web dashboard — score history, coverage, and review schedule.

Read-only by design: studying happens in the terminal, this just visualizes it.
Binds to localhost only; nothing is exposed to your network.

    python src/web.py              # then open http://127.0.0.1:5050
    python src/web.py --port 8080  # if 5050 is taken
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.concepts import UNCATEGORIZED, ConceptStore  # noqa: E402
from src.gamification import (  # noqa: E402
    ALL_BADGES,
    current_streak,
    earned_badges,
    level_for_xp,
    longest_streak,
    total_xp,
)
from src.progress import ProgressStore  # noqa: E402
from src.study import LOCAL_CHAT_ID  # noqa: E402

app = Flask(__name__)


def build_dashboard_data() -> dict:
    """Assemble everything the dashboard renders, from the same JSON stores the CLI uses."""
    concepts = ConceptStore()
    progress = ProgressStore()

    averages = progress.averages(LOCAL_CHAT_ID)
    states = progress.review_states(LOCAL_CHAT_ID)
    due = progress.due(LOCAL_CHAT_ID)
    attempts = progress.all_attempts(LOCAL_CHAT_ID)

    per_concept = []
    for name in concepts.names():
        history = progress.history(LOCAL_CHAT_ID, name)
        state = states.get(name)
        per_concept.append({
            "concept": name,
            "subject": concepts.subject_of(name) or UNCATEGORIZED,
            "average": averages.get(name),
            "attempts": len(history),
            "latest": history[-1]["score"] if history else None,
            "scores": [h["score"] for h in history],
            "due": state.due if state else None,
            "interval_days": state.interval_days if state else 0,
            "ease": round(state.ease, 2) if state else None,
        })

    per_subject = []
    for subject in concepts.subjects():
        names = concepts.names(subject)
        studied = [n for n in names if n in averages]
        per_subject.append({
            "subject": subject,
            "concepts": len(names),
            "studied": len(studied),
            "average": (sum(averages[n] for n in studied) / len(studied)) if studied else None,
            "due": len([c for c, _ in due if c in set(names)]),
        })

    # Daily average across all concepts, for the trend line.
    by_day: dict[str, list[float]] = defaultdict(list)
    for _, score, ts in attempts:
        by_day[ts[:10]].append(score)
    trend = [
        {"date": day, "average": sum(scores) / len(scores), "count": len(scores)}
        for day, scores in sorted(by_day.items())
    ]

    mapping = {name: concepts.subject_of(name) for name in concepts.names()}
    xp = total_xp(attempts)
    level = level_for_xp(xp)
    unlocked = earned_badges(attempts, mapping)
    unlocked_keys = {b.key for b in unlocked}

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "gamification": {
            "xp": xp,
            "level": level.level,
            "xp_into_level": level.xp_into_level,
            "xp_for_next": level.xp_for_next,
            "progress_percent": round(level.progress_fraction * 100),
            "current_streak": current_streak(attempts),
            "longest_streak": longest_streak(attempts),
            "badges": [
                {
                    "name": b.name,
                    "description": b.description,
                    "earned": b.key in unlocked_keys,
                }
                for b in ALL_BADGES
            ],
            "earned_count": len(unlocked),
            "total_count": len(ALL_BADGES),
        },
        "totals": {
            "loaded": len(concepts),
            "studied": len(averages),
            "attempts": progress.total_attempts(LOCAL_CHAT_ID),
            "due": len(due),
            "overall_average": (sum(averages.values()) / len(averages)) if averages else None,
        },
        "concepts": per_concept,
        "subjects": per_subject,
        "due": [{"concept": c, "days_overdue": d} for c, d in due],
        "trend": trend,
    }


@app.get("/api/data")
def api_data():
    return jsonify(build_dashboard_data())


@app.get("/")
def dashboard():
    return render_template_string(TEMPLATE, data=build_dashboard_data())


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Explain-Back Tutor — Dashboard</title>
<style>
  :root {
    --bg: #ffffff; --fg: #1a1a1a; --muted: #666; --line: #e3e3e3;
    --card: #fafafa; --good: #10804a; --mid: #9a6a00; --bad: #b3261e; --accent: #2b5c9b;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #16181c; --fg: #e8e8e8; --muted: #9aa0a6; --line: #2c2f36;
      --card: #1d2026; --good: #4ade80; --mid: #fbbf24; --bad: #f87171; --accent: #7fb0ef;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 2rem 1.25rem; background: var(--bg); color: var(--fg);
    font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .wrap { max-width: 1000px; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
  .sub { color: var(--muted); font-size: .875rem; margin-bottom: 2rem; }
  h2 { font-size: 1.05rem; margin: 2.5rem 0 .75rem; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .75rem; }
  .tile { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 1rem; }
  .tile .label { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
  .tile .value { font-size: 1.75rem; font-weight: 600; margin-top: .35rem; }
  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: .9rem; min-width: 560px; }
  th, td { text-align: left; padding: .6rem .7rem; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 600; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .good { color: var(--good); } .mid { color: var(--mid); } .bad { color: var(--bad); }
  .empty { color: var(--muted); font-style: italic; }
  .spark { display: inline-flex; align-items: flex-end; gap: 2px; height: 22px; }
  .spark i { width: 5px; background: var(--accent); border-radius: 1px; display: block; }
  .bar-track { background: var(--line); border-radius: 3px; height: 7px; width: 100%; max-width: 180px; }
  .bar-fill { background: var(--accent); height: 100%; border-radius: 3px; }
  .pill { background: var(--card); border: 1px solid var(--line); border-radius: 999px;
          padding: .12rem .55rem; font-size: .78rem; color: var(--muted); }
  .dim { color: var(--muted); }
  .small { font-size: .8rem; }
  .level-card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
                padding: 1.1rem; margin-top: 1.5rem; }
  .level-head { display: flex; justify-content: space-between; align-items: flex-start;
                gap: 1rem; flex-wrap: wrap; margin-bottom: .8rem; }
  .level-num { font-size: 2.2rem; font-weight: 700; line-height: 1; color: var(--accent); }
  .level-meta { text-align: right; font-size: .88rem; line-height: 1.7; }
  .bar-track.wide { max-width: none; }
  .badges { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: .6rem; }
  .badge { background: var(--card); border: 1px solid var(--line); border-radius: 9px;
           padding: .7rem .8rem; display: grid; grid-template-columns: auto 1fr;
           grid-template-areas: "mark name" "mark desc"; gap: 0 .55rem; align-items: center; }
  .badge.locked { opacity: .5; }
  .badge-mark { grid-area: mark; font-size: 1.25rem; }
  .badge-name { grid-area: name; font-weight: 600; font-size: .9rem; }
  .badge-desc { grid-area: desc; color: var(--muted); font-size: .76rem; line-height: 1.35; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Explain-Back Tutor</h1>
  <div class="sub">Study dashboard · generated {{ data.generated_at }}</div>

  {% macro grade(v) %}{% if v >= 8 %}good{% elif v >= 5 %}mid{% else %}bad{% endif %}{% endmacro %}

  <div class="tiles">
    <div class="tile"><div class="label">Concepts loaded</div><div class="value">{{ data.totals.loaded }}</div></div>
    <div class="tile"><div class="label">Studied</div><div class="value">{{ data.totals.studied }}</div></div>
    <div class="tile"><div class="label">Total attempts</div><div class="value">{{ data.totals.attempts }}</div></div>
    <div class="tile"><div class="label">Due now</div><div class="value">{{ data.totals.due }}</div></div>
    <div class="tile">
      <div class="label">Overall average</div>
      <div class="value {% if data.totals.overall_average %}{{ grade(data.totals.overall_average) }}{% endif %}">
        {% if data.totals.overall_average %}{{ "%.1f"|format(data.totals.overall_average) }}{% else %}—{% endif %}
      </div>
    </div>
  </div>

  {% set g = data.gamification %}
  <div class="level-card">
    <div class="level-head">
      <div>
        <div class="label">Level</div>
        <div class="level-num">{{ g.level }}</div>
      </div>
      <div class="level-meta">
        <div><strong>{{ g.xp }}</strong> XP total</div>
        <div>{{ g.current_streak }}-day streak <span class="dim">(best {{ g.longest_streak }})</span></div>
        <div>{{ g.earned_count }}/{{ g.total_count }} badges</div>
      </div>
    </div>
    <div class="bar-track wide">
      <div class="bar-fill" style="width: {{ g.progress_percent }}%"></div>
    </div>
    <div class="dim small">{{ g.xp_into_level }}/{{ g.xp_for_next }} XP to level {{ g.level + 1 }}</div>
  </div>

  <h2>Badges</h2>
  <div class="badges">
    {% for b in g.badges %}
    <div class="badge {% if not b.earned %}locked{% endif %}" title="{{ b.description }}">
      <span class="badge-mark">{% if b.earned %}🏅{% else %}🔒{% endif %}</span>
      <span class="badge-name">{{ b.name }}</span>
      <span class="badge-desc">{{ b.description }}</span>
    </div>
    {% endfor %}
  </div>

  {% if data.subjects|length > 1 %}
  <h2>By subject</h2>
  <div class="scroll"><table>
    <tr>
      <th>Subject</th><th class="num">Concepts</th><th class="num">Studied</th>
      <th class="num">Average</th><th class="num">Due</th><th>&nbsp;</th>
    </tr>
    {% for s in data.subjects %}
    <tr>
      <td>{{ s.subject }}</td>
      <td class="num">{{ s.concepts }}</td>
      <td class="num">{{ s.studied }}/{{ s.concepts }}</td>
      <td class="num {% if s.average %}{{ grade(s.average) }}{% endif %}">
        {% if s.average %}{{ "%.1f"|format(s.average) }}{% else %}—{% endif %}
      </td>
      <td class="num">{{ s.due }}</td>
      <td>
        <div class="bar-track">
          <div class="bar-fill" style="width: {{ (s.studied / s.concepts * 100)|round|int }}%"></div>
        </div>
      </td>
    </tr>
    {% endfor %}
  </table></div>
  {% endif %}

  <h2>Due for review</h2>
  {% if data.due %}
  <div class="scroll"><table>
    <tr><th>Concept</th><th class="num">Overdue</th></tr>
    {% for row in data.due %}
    <tr>
      <td>{{ row.concept }}</td>
      <td class="num">{% if row.days_overdue <= 0 %}today{% else %}{{ row.days_overdue }}d{% endif %}</td>
    </tr>
    {% endfor %}
  </table></div>
  {% else %}
  <p class="empty">Nothing due — you're caught up.</p>
  {% endif %}

  <h2>All concepts</h2>
  <div class="scroll"><table>
    <tr>
      <th>Concept</th><th>Subject</th><th class="num">Average</th><th class="num">Attempts</th>
      <th>History</th><th>Next review</th>
    </tr>
    {% for c in data.concepts %}
    <tr>
      <td>{{ c.concept }}</td>
      <td><span class="pill">{{ c.subject }}</span></td>
      <td class="num {% if c.average %}{{ grade(c.average) }}{% endif %}">
        {% if c.average %}{{ "%.1f"|format(c.average) }}{% else %}—{% endif %}
      </td>
      <td class="num">{{ c.attempts }}</td>
      <td>
        {% if c.scores %}
        <span class="spark">
          {% for s in c.scores %}<i style="height: {{ (s / 10 * 22)|round|int or 1 }}px"></i>{% endfor %}
        </span>
        {% else %}<span class="empty">not studied</span>{% endif %}
      </td>
      <td>{% if c.due %}<span class="pill">{{ c.due }}</span>{% else %}<span class="empty">—</span>{% endif %}</td>
    </tr>
    {% endfor %}
  </table></div>

  {% if data.trend %}
  <h2>Daily average</h2>
  <div class="scroll"><table>
    <tr><th>Date</th><th class="num">Average</th><th class="num">Attempts</th><th>&nbsp;</th></tr>
    {% for d in data.trend %}
    <tr>
      <td>{{ d.date }}</td>
      <td class="num {{ grade(d.average) }}">{{ "%.1f"|format(d.average) }}</td>
      <td class="num">{{ d.count }}</td>
      <td>
        <div class="bar-track"><div class="bar-fill" style="width: {{ (d.average / 10 * 100)|round|int }}%"></div></div>
      </td>
    </tr>
    {% endfor %}
  </table></div>
  {% endif %}
</div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Local read-only study dashboard.")
    # 5000 is avoided by default: macOS AirPlay Receiver listens there, which
    # makes the dashboard appear to start and then serve nothing useful.
    parser.add_argument(
        "--port", "-p", type=int, default=int(os.environ.get("PORT", "5050")),
        help="Port to serve on (default 5050, or $PORT)",
    )
    args = parser.parse_args()

    url = f"http://127.0.0.1:{args.port}"
    print(f"Explain-Back Tutor dashboard: {url}  (Ctrl+C to stop)")
    try:
        # localhost only — this is a personal dashboard, not a service.
        app.run(host="127.0.0.1", port=args.port, debug=False)
    except OSError as exc:
        print(f"\nCould not start on port {args.port}: {exc}", file=sys.stderr)
        print(f"Try a different one:  python src/web.py --port {args.port + 1}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
