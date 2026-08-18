# Explain-Back Tutor

A terminal study tool built on the Feynman technique: you don't understand
something until you can explain it simply in your own words. You pick a
concept, explain it in plain text, and it grades your explanation against
your own notes — telling you what you got right, where you were vague, and
what you got wrong or left out.

Unlike a flashcard app that tests your *recall*, this grades your
*explanation* — a much harder, more honest test of real understanding.

## How it works

1. You load your notes once (a markdown file, concepts split by `##`
   headings) into the concept store.
2. You type a concept name — e.g. `inflation`.
3. It asks you to explain it and does NOT show you the notes (that would
   defeat the point).
4. You type your explanation.
5. It grades strictly against your source notes and prints structured,
   colorized feedback plus a score out of 10.
6. It tracks your score per concept over time, so `/weak` shows the
   concepts you keep fumbling — your real study priorities.

## Why it's free

- **Grading**: `claude -p` (headless Claude Code) via your Claude
  subscription — NOT the paid per-token API.
- **Interface**: your terminal. No server, no hosting, no ports.
- **Storage**: plain JSON files — no database.

The only credential you need is a Claude Code token. Nothing else costs
anything, and nothing needs to reach your machine from outside.

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
Later, load your real notes the same way. Each concept starts with a
`## Concept Name` heading; everything under it is the source text you'll be
graded against. Add `--replace` to overwrite instead of merge.

### 3. Study
```
python src/study.py
```

## Using it

**Interactive** — `python src/study.py`

Type a concept name, then type your explanation (finish with a blank line):

```
> inflation
  Prices go up over time so your money buys less.
  Central banks raise interest rates to slow it down.

╭──── inflation — 6/10 ─────────────────────────────╮
│ Gets the core mechanism but loses precision on ... │
│                                                    │
│ Correct                                            │
│   • Prices rising and purchasing power falling     │
│ Vague                                              │
│   • Doesn't capture "sustained" vs a one-off rise  │
│ Wrong / missing                                    │
│   • No mention of how rates actually cool spending │
╰────────────────────────────────────────────────────╯
```

Commands: `/list` (all concepts), `/weak` (your lowest averages),
`/help`, `/exit`. `/cancel` backs out mid-explanation.

**One-shot / scriptable** — for piping, aliases, or cron jobs:

```
python src/study.py list
python src/study.py weak
echo "my explanation here" | python src/study.py explain inflation
```

These exit with a real status code (0 ok, 1 failure, 2 usage error), so
they compose properly in shell scripts.

## Running the tests

```
pytest -q
```
70 tests cover the concept store, progress tracking, the conversation
engine, the CLI's command routing and interactive loop, and the grader's
JSON parsing/validation — all with the actual `claude -p` call mocked out,
so the suite runs in a fraction of a second with no network use and no
draw on your subscription. The grading pipeline itself was verified
end-to-end against real `claude -p` calls during development.

## Files

- `src/study.py` — the terminal app (this is what you run)
- `src/conversation.py` — transport-agnostic conversation engine
- `src/concepts.py` — loads/searches your notes
- `src/grader.py` — grades your explanation via `claude -p`
- `src/progress.py` — tracks your scores per concept over time
- `src/load_notes.py` — one-time notes loader
- `sample_notes.md` — 3 ready-made concepts to test with
- `tests/` — unit tests for everything except the live `claude -p` call

## What makes this worth building (and not generic)

Most study tools quiz you — question in, did-you-remember out. This
inverts it: you produce the explanation, and the grading is grounded
strictly in your own source, so it distinguishes "you're vague here" from
"you're wrong here" from "the notes don't cover that." That grounding
discipline — separating unsupported from contradicted — is the same
principle behind a good RAG eval, applied to teaching yourself.

`conversation.py` deliberately knows nothing about the terminal: it takes
a session id and a string, and returns a string. Adding another front end
later (a local web UI, a scheduled reminder, a chat platform) means
writing an adapter, not touching the grading logic.
