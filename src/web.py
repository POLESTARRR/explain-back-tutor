#!/usr/bin/env python3
"""Local web dashboard — score history, coverage, and review schedule.

Read-only by design: studying happens in the terminal, this just visualizes it.
Binds to localhost only; nothing is exposed to your network.

    python src/web.py          # then open http://127.0.0.1:5000
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.concepts import ConceptStore  # noqa: E402
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
            "average": averages.get(name),
            "attempts": len(history),
            "latest": history[-1]["score"] if history else None,
            "scores": [h["score"] for h in history],
            "due": state.due if state else None,
            "interval_days": state.interval_days if state else 0,
            "ease": round(state.ease, 2) if state else None,
        })

    # Daily average across all concepts, for the trend line.
    by_day: dict[str, list[float]] = defaultdict(list)
    for _, score, ts in attempts:
        by_day[ts[:10]].append(score)
    trend = [
        {"date": day, "average": sum(scores) / len(scores), "count": len(scores)}
        for day, scores in sorted(by_day.items())
    ]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "totals": {
            "loaded": len(concepts),
            "studied": len(averages),
            "attempts": progress.total_attempts(LOCAL_CHAT_ID),
            "due": len(due),
            "overall_average": (sum(averages.values()) / len(averages)) if averages else None,
        },
        "concepts": per_concept,
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
      <th>Concept</th><th class="num">Average</th><th class="num">Attempts</th>
      <th>History</th><th>Next review</th>
    </tr>
    {% for c in data.concepts %}
    <tr>
      <td>{{ c.concept }}</td>
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
    # localhost only — this is a personal dashboard, not a service.
    app.run(host="127.0.0.1", port=5000, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
