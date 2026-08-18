# Explain-Back Tutor

A terminal study system built on the Feynman technique: you don't understand
something until you can explain it simply in your own words. You pick a
concept, explain it in plain text, and it grades your explanation against
your own notes — telling you what you got right, where you were vague, and
what you got wrong or left out.

Unlike a flashcard app that tests your *recall*, this grades your
*explanation* — a much harder, more honest test of real understanding.

Built for teaching many subjects: load any set of notes, and it schedules
what to review, tracks where you're weak, and flags where your notes
themselves are thin.

## What it does

- **Grades your explanations** against your own notes, separating "vague"
  from "wrong" from "not in the notes at all"
- **Schedules reviews** with spaced repetition (SM-2), so concepts come
  back right before you'd forget them
- **Picks what to study next** — due reviews first, then a weighted mix of
  weak spots, reinforcement, and unexplored concepts
- **Organizes by subject**, so you can scope a session to one of them
- **Flags gaps in your notes** — when you say something true that your
  notes don't cover, that's a note to improve, not a mistake
- **Summarizes each session** to a markdown log you can review later
- **Shows a dashboard** of scores, coverage, and upcoming reviews
- **Reminds you daily** via a native macOS notification
- **Never loses your data** — atomic writes, and a corrupt file is
  quarantined rather than crashing the app or being overwritten

## Why it's free

- **Grading**: `claude -p` (headless Claude Code) via your Claude
  subscription — NOT the paid per-token API.
- **Interface**: your terminal, plus an optional local-only web dashboard.
- **Scheduling**: `launchd`, built into macOS.
- **Storage**: plain JSON files — no database.

The only credential you need is a Claude Code token. Nothing costs
anything, nothing is exposed to the network, and no data leaves your
machine except the grading prompt itself.

## Setup

### 1. Authenticate Claude Code for headless use
```
claude setup-token
claude -p "say hello"     # must print a reply before continuing
```
Put the token in `.env` as `CLAUDE_CODE_OAUTH_TOKEN`.

### 2. Install and load your notes
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in the token above
python src/load_notes.py sample_notes.md    # try the 3 sample concepts first
```
Load your real notes the same way:

```
python src/load_notes.py chemistry.md physics.md      # several files at once
python src/load_notes.py notes.md --subject biology   # tag a whole file
python src/load_notes.py notes.md --replace           # overwrite instead of merge
```

**Notes format** — `## Concept Name` starts a concept, and everything under
it is the source text you'll be graded against. `# Subject Name` groups
every concept beneath it, so one file can hold several subjects:

```markdown
# Chemistry

## Covalent Bonding
Atoms share electron pairs...

## Acids and Bases
A Brønsted acid is a proton donor...

# Physics

## Inertia
An object resists change in its state of motion...
```

A `--subject` flag applies to concepts appearing before any `#` heading.
Concepts with no subject at all are grouped as `uncategorized`.

### 3. Study
```
python src/study.py
```

## Using it

### Interactive

`python src/study.py`, then type a concept name — or `/next` and let it
choose for you. Type your explanation, finish with a blank line:

```
> /next
╭─ Next up ──────────────────────╮
│ photosynthesis                 │
│ due for review                 │
╰────────────────────────────────╯

  Plants take in CO2 and water, and use chlorophyll to capture sunlight...

╭──── photosynthesis — 8/10 ──────────────────────────────╮
│ The mechanism is accurate and well-sequenced...          │
│                                                          │
│ Correct                                                  │
│   • Light reactions occur in the thylakoid membranes     │
│ Vague                                                    │
│   • Never states the overall energy-conversion purpose   │
│ Wrong / missing                                          │
│   • Restricts it to plants — notes include algae too     │
│                                                          │
│ Next review: 2026-08-19                                  │
╰──────────────────────────────────────────────────────────╯
```

Commands: `/next`, `/review`, `/due`, `/list`, `/subjects`, `/focus`,
`/history <concept>`, `/weak`, `/stats`, `/help`, `/exit`. `/cancel` backs
out mid-explanation. On exit you get a session summary and a saved log.

**`/review` is the daily workflow** — it drills straight through every
concept that's due, one after another, and summarizes at the end.

**Focusing on one subject** — `/focus chemistry` scopes `/next`, `/due`,
`/list`, `/weak`, and `/stats` to that subject for the rest of the session;
`/focus` alone clears it. Or start focused:

```
python src/study.py --subject chemistry
```

### One-shot / scriptable

```
python src/study.py list                 # all loaded concepts, with subjects
python src/study.py subjects             # subjects and their coverage
python src/study.py due                  # what's due for review
python src/study.py next                 # what to study now, and why
python src/study.py review               # drill through everything due
python src/study.py weak                 # your lowest averages
python src/study.py stats                # coverage and overall average
python src/study.py history inflation    # every attempt at one concept
echo "my explanation" | python src/study.py explain inflation
```

Most commands take `--subject S` to scope them; `weak` also takes
`--limit N`. These exit with real status codes (0 ok, 1 failure, 2 usage
error), so they compose in shell scripts and cron jobs. `--help` works on
the top level and on every subcommand.

### Web dashboard

```
python src/web.py               # then open http://127.0.0.1:5050
python src/web.py --port 8080   # if that port is taken
```

Read-only view of scores over time, per-subject rollups, per-concept
history, coverage, and the review queue. Binds to localhost only — it is
not reachable from your network. There's also a `/api/data` JSON endpoint.

(It defaults to port 5050 rather than 5000 because macOS AirPlay Receiver
occupies 5000, which makes a dashboard on that port fail confusingly.)

### Daily reminders (macOS)

```
./scheduling/install_reminder.sh          # daily at 19:00
./scheduling/install_reminder.sh 9 30     # daily at 09:30
./scheduling/install_reminder.sh --uninstall
```

Installs a `launchd` agent that posts a notification naming what's due. It
stays silent when you're caught up — a reminder that fires when there's
nothing to do just teaches you to ignore reminders.

## How the scheduling works

Scores map onto SM-2's quality scale (a 10-point score halves into SM-2's
0–5). Score 6+ counts as a pass and pushes the next review further out
(1 day → 6 days → multiplied by an ease factor). Score 5 or below is a
lapse: the interval resets to 1 day and the ease drops, so a concept you
keep fumbling keeps coming back.

`next` honors due reviews above everything else. Only when nothing is due
does it fall back to a weighted mix — 60% weak concepts, 30% reinforcing
strong ones, 10% something you've never tried.

## Your data

Everything lives in `data/` as plain JSON and markdown you can read, edit,
back up, or delete:

- `data/concepts.json` — your loaded notes
- `data/progress.json` — score history and review schedule
- `data/sessions/*.md` — one markdown log per study session

Both JSON stores are written atomically (temp file + rename), so a crash or
a full disk can't leave you with a half-written file. If a file is ever
found corrupt anyway, it's moved aside as `*.corrupt-<timestamp>` and the
app starts clean instead of crashing or overwriting it — your data is
always recoverable by hand.

Grading failures are retried automatically (they're usually a timeout or
the model returning prose instead of JSON). If every retry fails, your
explanation is written to `data/unsent/` rather than lost, so a long answer
never disappears because of a hiccup.

Store formats have changed twice as features landed; both migrations run
automatically on load, so older files keep working.

## Running the tests

```
pytest
```
225 tests cover the concept store and its subject grouping, spaced-repetition
scheduling, progress tracking, both store migrations, atomic writes and
corruption recovery, grader retries and explanation preservation, session
summaries, the review drill, per-concept history, the CLI's argument parsing
and interactive loop, subject scoping, the web dashboard, and the reminder —
all with the `claude -p` call mocked, so the suite runs in well under a
second with no network use and no draw on your subscription. The grading
pipeline was verified end-to-end against real `claude -p` calls during
development.

CI runs the suite on Python 3.10–3.13 on every push.

## Files

| File | Purpose |
|---|---|
| `src/study.py` | the terminal app — this is what you run |
| `src/scheduler.py` | SM-2 spaced repetition + adaptive concept selection |
| `src/progress.py` | score history and review state |
| `src/grader.py` | grades an explanation via `claude -p` |
| `src/concepts.py` | loads/searches your notes, groups them by subject |
| `src/storage.py` | atomic JSON writes and corruption recovery |
| `src/session.py` | session recording and markdown summaries |
| `src/conversation.py` | transport-agnostic conversation engine |
| `src/load_notes.py` | notes loader |
| `src/web.py` | local read-only dashboard |
| `scheduling/remind.py` | macOS notification about what's due |
| `scheduling/install_reminder.sh` | installs/removes the launchd agent |
| `tests/` | 200 tests |

## What makes this worth building (and not generic)

Most study tools quiz you — question in, did-you-remember out. This
inverts it: you produce the explanation, and the grading is grounded
strictly in your own source, so it distinguishes "you're vague here" from
"you're wrong here" from "the notes don't cover that." That grounding
discipline — separating unsupported from contradicted — is the same
principle behind a good RAG eval, applied to teaching yourself.

The notes-gap detection falls out of that discipline for free, and is the
part that matters most if you teach: it tells you where *your material* is
thin, not just where your understanding is.

`conversation.py` and `scheduler.py` deliberately know nothing about the
terminal. Adding another front end means writing an adapter, not touching
the grading or scheduling logic.
