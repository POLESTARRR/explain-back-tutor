# Deploying Feynly

Local use needs none of this. Running `python src/webapp.py` on your own machine
already works, costs nothing, and keeps every note on your disk. This is only for
putting Feynly on a public URL where other people can use it.

## What changes when it is deployed

| | Local | Deployed |
|---|---|---|
| Grading | `claude -p` on your Claude subscription | Gemini free tier |
| Storage | JSON files under `data/` | Turso database |
| Users | one history, yours | one private history per visitor |
| Cost | nothing | nothing |

Grading has to change because a public host has no Claude Code CLI, and your
subscription token must never be shipped to a server strangers can reach.

## Before you start

**Rotate any key you have pasted into a chat, an issue, or a screenshot.**
Create fresh ones and put them straight into the host's secrets panel.

- Gemini key: <https://aistudio.google.com/apikey>
- Turso database: <https://turso.tech>

You will need four values:

| Variable | Where it comes from |
|---|---|
| `GEMINI_API_KEY` | AI Studio |
| `TURSO_DATABASE_URL` | Turso, looks like `libsql://name-user.turso.io` |
| `TURSO_AUTH_TOKEN` | Turso |
| `FLASK_SECRET_KEY` | any long random string, e.g. `python -c "import secrets; print(secrets.token_hex(32))"` |

`FLASK_SECRET_KEY` is not optional. It signs the cookie that tells one visitor
from another. Without a stable secret, sessions break on every restart; with a
guessable one, a forged cookie could read someone else's notes.

## Hugging Face Spaces

1. Sign in at <https://huggingface.co>, then **New Space**.
2. Name it `feynly`, choose **Docker** as the SDK, and pick the free CPU hardware.
3. In **Settings → Variables and secrets**, add the four values above as
   **secrets**, not variables. Also add `LLM_PROVIDER` = `gemini` as a variable.
4. Push this repository to the Space:

   ```
   git remote add space https://huggingface.co/spaces/<your-username>/feynly
   git push space main
   ```

5. Watch the build log. When it finishes, the Space serves on port 7860, which
   the Dockerfile already listens on.

## Render

1. Sign in at <https://render.com>, then **New → Web Service** and connect the
   GitHub repository.
2. Choose **Docker** as the runtime. Render reads the `Dockerfile` as is.
3. Add the four values under **Environment**, plus `LLM_PROVIDER` = `gemini`.
4. Deploy. Render injects `PORT`, which the Dockerfile already honours.

Free web services sleep after about fifteen minutes idle, so the first visit
after a quiet spell takes a while to wake.

## Checking it worked

- Open the URL. The study page should load with no notes yet.
- Go to **Notes**, paste or photograph something, and save it.
- Explain it. A score, XP, and a review date mean grading, the database, and the
  session cookie are all working.
- Open the same URL in a private window. It should look like a brand new account
  with none of your notes. If your notes appear there, stop: the session cookie
  is not doing its job and everyone is sharing one account.

## Running the container yourself

```
docker build -t feynly .
docker run -p 7860:7860 \
  -e GEMINI_API_KEY=... \
  -e TURSO_DATABASE_URL=... \
  -e TURSO_AUTH_TOKEN=... \
  -e FLASK_SECRET_KEY=... \
  feynly
```

## Limits worth knowing

The Gemini free tier allows on the order of a few hundred to a thousand requests
a day depending on the model, and that budget is shared by everyone using your
deployed instance rather than granted per visitor. A class hammering it will hit
the ceiling. The app already falls through a list of models when one is
overloaded, so a busy model shows up as slowness rather than an error.

Prompts sent on the Gemini free tier may be used by Google to improve their
products. Notes and explanations are part of those prompts. That is a real
tradeoff for private teaching material, and the reason local use stays on
`claude -p`, where nothing leaves the machine.
