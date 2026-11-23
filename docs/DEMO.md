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

## Public hosting on Render (approved plan; creation needs your Render login)

Creating the service puts an unauthenticated `POST /evaluate` on the public internet. The data is synthetic and every
response carries `"simulated": true`, but treat the URL as private (see "Before and after the demo").

| Item | Value |
|---|---|
| Service name | `sim006-demo` |
| Repo / branch | `saisiddi/SIM-006_Detection_Rule_Simulator`, branch `feat/demo-ui` (`main` does not have the frontend yet) |
| Runtime | Docker, `./Dockerfile` |
| Instance type | **Starter**, 0.5 CPU / 512 MB, **$7 per month** |
| Why not Free | Render docs: a Free web service "spins down" after 15 minutes without traffic and takes "about one minute" to start again |
| Health check path | `/health` |
| Auto-Deploy | **Off**, so later pushes cannot change the live demo |
| Environment variables | none. Render supplies `PORT` and the image reads it |
| Public URL | `https://sim006-demo.onrender.com/app/` (Render adds a suffix if the name is taken; use the URL it shows) |

Sources: [pricing](https://render.com/pricing), [free-tier limits](https://render.com/docs/free),
[web services](https://render.com/docs/web-services), [deploys / auto-deploy](https://render.com/docs/deploys),
[health checks](https://render.com/docs/health-checks).

### Create it (one time, in the Render dashboard)

Button labels can differ slightly from this list; the values are what matter.

1. Sign in at https://dashboard.render.com.
2. **New +**, **Web Service**, **Git Provider**. If GitHub is not connected, choose **Connect GitHub**, install the Render
   GitHub app, and grant it access to the `SIM-006_Detection_Rule_Simulator` repository only.
3. Select the repository, **Connect**.
4. Fill in: **Name** `sim006-demo`; **Branch** `feat/demo-ui`; **Language / Runtime** `Docker`; **Dockerfile Path**
   `./Dockerfile`; **Region** the one closest to the venue; **Instance Type** `Starter` ($7 / month).
5. Open **Advanced**: set **Health Check Path** to `/health`; set **Auto-Deploy** to **Off**. Add no environment variables.
6. **Create Web Service**. Wait for the deploy log to end with the service **Live** (the first Docker build takes a few
   minutes). If it fails, copy the last 30 lines of the log.
7. Copy the `https://....onrender.com` URL shown under the service name and keep it to yourself.
8. Verify from your laptop (checks `/health`, the `/` redirect, and all six scenarios against the public URL):

   ```bash
   venv/bin/python scripts/verify_demo.py https://sim006-demo.onrender.com
   ```

To redeploy on purpose later: service page, **Manual Deploy**, **Deploy latest commit** (Auto-Deploy stays Off).

### Teardown

Render dashboard, open the service, **Settings**, scroll to the bottom, **Delete Web Service**. Check the **Billing** page
afterwards to confirm no instance is still running.

## Before and after the demo

**The URL must not be shared publicly.** `POST /evaluate` has no authentication. The data is synthetic, but anyone who
has the link can send requests to a billed instance. Show the URL to the panel; do not post it in chats, issues, or the PR.

**About 30 minutes before presenting: resume the service.**

1. Render dashboard, open `sim006-demo`. If it is suspended, use the **Resume** button on the service page.
2. Wait until the service shows **Live** (a resumed service redeploys, so allow several minutes; that is why the lead time
   is 30 minutes).
3. Check from your laptop: `curl -s https://sim006-demo.onrender.com/health` returns `{"status":"ok","simulated":true}`.
4. Run `venv/bin/python scripts/verify_demo.py https://sim006-demo.onrender.com` and confirm `RESULT: ALL OK`.
5. Open `/app/`, click **Voltage warning** once, and confirm the big lamp is amber and says WARN.
6. Keep the offline fallback ready (launch command at the top of this file) in case the venue network fails.

**Right after presenting: suspend the service.**

1. Render dashboard, open `sim006-demo`, **Settings**, scroll to the bottom, **Suspend Web Service**, confirm.
2. Confirm the service shows **Suspended**.
3. Check the **Billing** page.

Note: Render's docs that I could read describe suspending and resuming Free services and sandboxes, but give no click path
or billing statement for a paid web service. The button names above are what the dashboard normally calls them; if they
differ, look under the service's **Settings**. If you do not plan to demo again soon, delete the service instead.

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
