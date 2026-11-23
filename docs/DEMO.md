# SIM-006 demo guide

## Launch (this is the demo UI)

```bash
venv/bin/python -m uvicorn sim_006.api:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000/app/**

> **Do not use the Streamlit UI for the demo.** `streamlit run sim_006/streamlit_app.py` (port 8501) is the older
> interface. Before presenting, check nothing is listening on 8501: `ss -ltnp | grep 8501` (empty output is good).

Everything the page shows comes from this one process: the status pills read `GET /health` and `GET /rules`, and every
verdict is a real `POST /evaluate`.

## Offline fallback (venue Wi-Fi down)

The command above *is* the offline mode. Nothing is fetched from the internet: the six font files are bundled in
`frontend/fonts/` (SIL OFL, licences alongside) and the page makes no external requests. This was checked by loading the
page with every non-localhost request blocked: zero attempted, all fonts loaded, scenarios ran.

Before leaving for the venue: run the launch command once and click through the six scenarios.

## Docker (one command: API + UI)

```bash
docker compose up --build api
# open http://localhost:8000/app/
```

- The image runs as an unprivileged user (UID 10001) on Python 3.12 and has a health check against `/health`
  (`docker compose ps` shows `healthy` after about 15 s).
- `0.0.0.0` is only the bind address inside the container. What is published to your machine is the `8000:8000` mapping in
  `docker-compose.yml`.
- A plain `docker compose up` would also run the `test` service. Name `api` as above.
- The old Streamlit service now sits behind a compose profile (`legacy-streamlit`), so it does **not** start by default.
- Teardown: `docker compose down`.

## Public hosting on Render (NOT created yet, plan only, awaiting approval)

Nothing below has been run. Creating the service puts an unauthenticated `POST /evaluate` on the public internet. The
data is synthetic and every response carries `"simulated": true`, but treat the URL as public.

| Item | Value |
|---|---|
| Runtime | Docker (uses the repo `Dockerfile`) |
| Instance type | **Starter**, 0.5 CPU / 512 MB, **$7 per month** (plan ID `0.5c-512mb`) |
| Why not Free | Render docs: a Free web service "spins down" after 15 minutes without traffic and takes "about one minute" to start again |
| Health check path | `/health` |
| Environment variables | none required. Render supplies `PORT` (default 10000) and the image reads it |
| Public URL shape | `https://<service-name>.onrender.com/app/` |

Sources: [pricing](https://render.com/pricing) (Starter, $7/month, 512 MB, 0.5 CPU, read from the page's embedded plan data),
[free-tier limits](https://render.com/docs/free), [web services](https://render.com/docs/web-services). Confirm the price
on the pricing page again on the day you create it.

Teardown: Render dashboard, open the service, Settings, Delete Web Service. Billing for it stops when it is deleted.

## 60-second demo script

Start with the page open and the pills green. Say one line per step, then click.

| Time | Click | Say |
|---|---|---|
| 0:00 | (open `/app/`) | "These pills are live: the API answered health, and it loaded 8 detection rules." |
| 0:08 | **Clean pass** | "A normal battery event. All eight rules pass, so the gate is PASS." |
| 0:18 | **Voltage warning** | "58 volts is just over the 56-volt limit. Not an alarm yet: amber WARN, and only R-05 lights up." |
| 0:28 | **Replay attack** | "Same sequence number sent twice. R-01 fails, the gate goes HARD FAIL, and failures sort to the top." |
| 0:38 | point at **Backend proof** line, then scroll to the panel | "No mock. This is the exact request, the raw response, HTTP 200, and the real round-trip time." |
| 0:48 | **Impossible SOC**, then **Explain this result** | "State of charge jumped 30 percent with no charger. The explanation is a deterministic fallback, and it never changes the verdict." |

Other scenarios if asked: **Missing timestamp** (R-02), **Firmware tampering** (R-04).

## Pre-demo checklist

1. `ss -ltnp | grep 8501` shows nothing (old Streamlit not running).
2. Launch command running, `http://localhost:8000/app/` loads, all four pills present, first is green.
3. Click **Voltage warning** once: the big lamp must be amber and say WARN.
4. Browser zoom 100%. For a large room, 125% still lays out cleanly.
5. Keyboard works if the mouse fails: Tab to a scenario, Enter runs it.

## If something goes wrong

| Symptom | Fix |
|---|---|
| Page says "API unreachable" | The server is not running or the port is taken: restart the launch command, or use `--port 8001` and open that port. |
| `Address already in use` | Something else holds 8000: `ss -ltnp | grep 8000`, stop it, relaunch. |
| Blank page at `/` | Open `/app/` (with the trailing path). `/` redirects there. |
