import { SCENARIOS } from "./scenarios.js";

const $ = (id) => document.getElementById(id);
const LABEL = { PASS: "Pass", WARN: "Warn", HARD_FAIL: "Hard fail" };
const RANK = { HARD_FAIL: 0, WARN: 1, PASS: 2 };
const ICON = {
  PASS: '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.8 2.8L16 9.5"/>',
  WARN: '<path d="M12 4 2.8 20h18.4z"/><path d="M12 10v4.5M12 17.6v.1"/>',
  HARD_FAIL: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6m0-6-6 6"/>',
  IDLE: '<path d="M6 12h12"/>',
};
const svg = (name, cls = "") =>
  `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICON[name]}</svg>`;
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const state = { rules: [], last: null, active: null, running: false };

/* ---------- HTTP ---------- */
async function call(method, path, body) {
  const t0 = performance.now();
  try {
    const res = await fetch(path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = text; }
    return { path, method, status: res.status, ok: res.ok, ms: Math.round(performance.now() - t0), data };
  } catch {
    return { path, method, status: 0, ok: false, ms: Math.round(performance.now() - t0), data: null, network: true };
  }
}

// Turn FastAPI 400/422 bodies into one plain sentence.
function plainError(r) {
  if (r.network) return "Can't reach the API. Check that the server is running, then try again.";
  const d = r.data;
  if (r.status === 422 && d && Array.isArray(d.detail)) {
    return "The API rejected the request: " + d.detail
      .map((e) => `${(e.loc || []).filter((p) => p !== "body").join(".") || "request"} — ${e.msg}`)
      .join("; ") + ".";
  }
  if (r.status === 400 && d && typeof d === "object") {
    return `The API rejected the rule selection: ${d.detail || d.error || "invalid rule IDs"}.`;
  }
  if (r.status >= 500) return `The API had an internal error (HTTP ${r.status}). Try again.`;
  return `Unexpected response from the API (HTTP ${r.status}).`;
}

/* ---------- status pills (real data from /health and /rules) ---------- */
function setPills(items) {
  $("pills").innerHTML = items
    .map((p) => {
      const icon = p.state === "bad" ? "HARD_FAIL" : p.state === "ok" ? "PASS" : "IDLE";
      return `<li class="pill" data-state="${p.state}">${svg(icon, "pill-icon")}<span>${esc(p.text)}</span></li>`;
    })
    .join("");
}
let aiPill = { state: "note", text: "AI explanations: on request" };
function renderPills(health, rules) {
  const up = health && health.ok && health.data && health.data.status === "ok";
  setPills([
    up ? { state: "ok", text: `API reachable (${health.ms} ms)` } : { state: "bad", text: "API unreachable" },
    up && rules && rules.ok
      ? { state: "ok", text: `Engine: live API · ${rules.data.rules.length} rules loaded` }
      : { state: "bad", text: "Engine: not loaded" },
    up && health.data.simulated ? { state: "note", text: "Simulator: simulated data only" } : { state: "bad", text: "Simulator: unknown" },
    aiPill,
  ]);
  state.health = health; state.rulesRes = rules;
}

/* ---------- rendering ---------- */
function lampHtml(r, idle) {
  const cls = idle ? "idle" : r.result;
  const chip = idle
    ? `<span class="chip">${svg("IDLE")}Not run</span>`
    : `<span class="chip">${svg(r.result)}${LABEL[r.result]}</span>`;
  return `<li class="lamp ${cls}${idle ? "" : " lit"}"><div class="lamp-head"><span class="lid">${esc(r.rule_id)}</span>${chip}</div>` +
    `<h4 class="lname">${esc(r.rule_name)}</h4><p class="ldetail">${esc(idle ? r.description : r.detail)}</p></li>`;
}

function renderIdleLamps() {
  $("lamps").innerHTML = state.rules.map((r) => lampHtml(r, true)).join("");
  $("lamps-note").textContent = state.rules.length ? `${state.rules.length} loaded from the API` : "";
}

function setMaster(kind, word, sub, icon) {
  const m = $("master");
  m.className = `master ${kind}`;
  m.querySelector("svg").innerHTML = ICON[icon];
  $("master-word").textContent = word;
  $("master-sub").textContent = sub;
  if (kind === "PASS" || kind === "WARN" || kind === "HARD_FAIL") {
    m.classList.add("lit");
    m.addEventListener("animationend", () => m.classList.remove("lit"), { once: true });
  }
}

function renderResult(r) {
  const res = r.data;
  const label = res.overall_gate === "HARD_FAIL" ? "HARD FAIL" : res.overall_gate;
  setMaster(res.overall_gate, `Overall gate: ${label}`,
    `${res.gate_reason} · ${res.rules_evaluated} rule${res.rules_evaluated === 1 ? "" : "s"} evaluated`, res.overall_gate);
  $("live").textContent =
    `Overall gate: ${label}. ${res.rules_evaluated} rules evaluated. ${res.gate_reason}`;
  const sorted = [...res.results].sort(
    (a, b) => RANK[a.result] - RANK[b.result] || a.rule_id.localeCompare(b.rule_id));
  $("lamps").innerHTML = sorted.map((x) => lampHtml(x, false)).join("");
  $("lamps-note").textContent = "failures first";
}

function renderError(r, message) {
  setMaster("err", "Request failed", message, "HARD_FAIL");
  $("live").textContent = `Request failed. ${message}`;
}

function renderProof(r, sent) {
  $("p-endpoint").textContent = `${r.method} ${r.path}`;
  $("p-status").textContent = r.network ? "no response" : `${r.status} ${r.ok ? "OK" : "error"}`;
  $("p-latency").textContent = `${r.ms} ms`;
  $("p-request").textContent = JSON.stringify(sent, null, 2);
  $("p-response").textContent = r.network ? "No response received." : typeof r.data === "string" ? r.data : JSON.stringify(r.data, null, 2);
  $("proof-strip").innerHTML = `<a href="#h-proof">Backend proof</a>: ${esc(r.method)} ${esc(r.path)} · ` +
    (r.network ? "no response" : `HTTP ${r.status}`) + ` · ${r.ms} ms`;
  const exp = $("p-expect");
  if (state.active && r.ok) {
    const got = r.data.overall_gate;
    exp.textContent = got === state.active.expect
      ? `expected ${state.active.expect}, backend returned ${got}: match`
      : `expected ${state.active.expect}, backend returned ${got}: MISMATCH`;
  } else {
    exp.textContent = state.active ? "—" : "custom request";
  }
}

function showFormError(msg) {
  const e = $("form-error");
  e.hidden = !msg;
  e.textContent = msg || "";
}

/* ---------- actions ---------- */
function currentScope() {
  return document.querySelector('input[name="scope"]:checked').value;
}

async function run() {
  if (state.running) return;
  showFormError("");
  let payload;
  try {
    payload = JSON.parse($("req").value);
  } catch (e) {
    showFormError(`Invalid JSON: ${e.message}`);
    return;
  }
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    showFormError("The JSON must be an object: { battery_id, event, rule_ids }.");
    return;
  }
  if (currentScope() === "subset") {
    const picked = [...document.querySelectorAll("#rule-picks input:checked")].map((i) => i.value);
    if (!picked.length) { showFormError("Choose at least one rule, or switch to All rules."); return; }
    payload.rule_ids = picked;
  } else {
    payload.rule_ids = "all";
  }

  state.running = true;
  const btn = $("run");
  btn.setAttribute("aria-busy", "true");
  btn.disabled = true;
  btn.textContent = "Evaluating…";
  setMaster("busy", "Evaluating…", "Waiting for the API", "IDLE");

  const r = await call("POST", "/evaluate", payload);

  state.running = false;
  btn.removeAttribute("aria-busy");
  btn.disabled = false;
  btn.textContent = "Run evaluation";
  renderProof(r, payload);

  if (r.ok && r.data && r.data.overall_gate) {
    state.last = r.data;
    renderResult(r);
    $("download").disabled = false;
    $("explain").disabled = false;
    $("explanation").hidden = true;
  } else {
    state.last = null;
    const msg = plainError(r);
    renderError(r, msg);
    showFormError(msg);
    renderIdleLamps();
    $("download").disabled = true;
    $("explain").disabled = true;
  }
  renderPills(state.health, state.rulesRes);
}

function pickScenario(s) {
  state.active = s;
  document.querySelectorAll("#scenarios .btn").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.id === s.id)));
  $("req").value = JSON.stringify(s.build(), null, 2);
  document.querySelector('input[name="scope"][value="all"]').checked = true;
  $("rule-picks").hidden = true;
  run();
}

async function explain() {
  if (!state.last) return;
  const b = $("explain");
  b.disabled = true;
  b.setAttribute("aria-busy", "true");
  const r = await call("POST", "/explain", { evaluation: state.last });
  b.removeAttribute("aria-busy");
  b.disabled = false;
  const box = $("explanation");
  box.hidden = false;
  if (!r.ok) {
    box.innerHTML = `<h3>Explanation</h3><p>${esc(plainError(r))}</p>`;
    return;
  }
  const x = r.data;
  const provenance = x.ai_generated
    ? "AI-generated text. The verdict above still comes from the rule engine only."
    : "Deterministic fallback: no AI model wrote this. The verdict comes from the rule engine only.";
  aiPill = x.ai_generated
    ? { state: "ok", text: "AI explanations: live model" }
    : { state: "note", text: "AI explanations: deterministic fallback" };
  renderPills(state.health, state.rulesRes);
  box.innerHTML =
    `<h3>Explanation</h3><p class="provenance">${esc(provenance)}</p><p>${esc(x.summary)}</p>` +
    `<p>${esc(x.what_happened)}</p><p>${esc(x.why_it_matters)}</p>` +
    (x.recommended_checks && x.recommended_checks.length
      ? `<h3>Recommended checks</h3><ul>${x.recommended_checks.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : "");
}

function download() {
  if (!state.last) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(state.last, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "sim_006_evaluation_report.json" });
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ---------- boot ---------- */
function buildScenarioButtons() {
  $("scenarios").innerHTML = SCENARIOS
    .map((s) => `<button type="button" class="btn" data-id="${s.id}" aria-pressed="false">${esc(s.label)}</button>`)
    .join("");
  $("scenarios").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-id]");
    if (b) pickScenario(SCENARIOS.find((s) => s.id === b.dataset.id));
  });
}

function buildRulePicks() {
  $("rule-picks").innerHTML = state.rules
    .map((r) => `<label class="check"><input type="checkbox" value="${esc(r.rule_id)}" checked> ${esc(r.rule_id)}</label>`)
    .join("");
}

async function boot() {
  buildScenarioButtons();
  $("req").value = JSON.stringify(SCENARIOS[0].build(), null, 2);
  $("req").addEventListener("input", () => {
    state.active = null;
    document.querySelectorAll("#scenarios .btn").forEach((b) => b.setAttribute("aria-pressed", "false"));
  });
  document.querySelectorAll('input[name="scope"]').forEach((i) =>
    i.addEventListener("change", () => { $("rule-picks").hidden = currentScope() !== "subset"; }));
  $("run").addEventListener("click", run);
  $("explain").addEventListener("click", explain);
  $("download").addEventListener("click", download);

  const [health, rules] = await Promise.all([call("GET", "/health"), call("GET", "/rules")]);
  state.rules = rules.ok ? rules.data.rules : [];
  buildRulePicks();
  renderIdleLamps();
  renderPills(health, rules);
  if (!health.ok) {
    setMaster("err", "API unreachable", plainError(health), "HARD_FAIL");
  }
}

boot();
