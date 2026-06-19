"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (n) => "$" + (Number(n) || 0).toFixed(n >= 100 ? 0 : 2);
const qs = () => `?project=${$("project").value}&hours=${$("window").value}`;

function setStatus(msg) {
  $("status").textContent = msg;
}

async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

async function loadProjects() {
  const projects = await getJSON("/api/projects");
  const sel = $("project");
  for (const p of projects) {
    const opt = document.createElement("option");
    opt.value = p.slug;
    opt.textContent = p.name;
    sel.appendChild(opt);
  }
}

function populateBackends(modelRows) {
  const sel = $("backend");
  const cur = sel.value;
  const set = new Set(modelRows.map((r) => r.backend).filter(Boolean));
  if (cur !== "all") set.add(cur); // keep the current selection selectable
  const backends = [...set].sort();
  sel.innerHTML =
    '<option value="all">all backends</option>' +
    backends
      .map((b) => `<option value="${b}"${b === cur ? " selected" : ""}>${b}</option>`)
      .join("");
  sel.value = cur;
}

function renderSummary(s, backend, modelRows) {
  let cards;
  if (backend && backend !== "all") {
    // Day-granular backend total from the per-model metrics (see by-model).
    const total = modelRows.reduce((a, r) => a + (Number(r.cost) || 0), 0);
    cards = [
      { label: `total · ${backend}`, value: fmt(total), sub: `${s.window_hours}h window` },
    ];
  } else {
    cards = [
      { label: "total cost", value: fmt(s.total_cost), sub: `${s.window_hours}h window` },
      ...s.projects.map((p) => ({
        label: p.name,
        value: fmt(p.cost),
        sub: `${p.trace_count} traces`,
      })),
    ];
  }
  $("summary-cards").innerHTML = cards
    .map(
      (c) =>
        `<div class="card"><div class="label">${c.label}</div>` +
        `<div class="value">${c.value}</div><div class="sub">${c.sub}</div></div>`
    )
    .join("");
}

function renderTrend(points) {
  const canvas = $("trend");
  const ctx = canvas.getContext("2d");
  const W = (canvas.width = canvas.clientWidth);
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  const costs = points.map((p) => p.cost);
  const max = Math.max(...costs, 1e-9);
  const n = points.length;
  // area fill
  ctx.beginPath();
  ctx.moveTo(0, H);
  points.forEach((p, i) => {
    const x = (i / (n - 1 || 1)) * W;
    const y = H - (p.cost / max) * (H - 8) - 4;
    ctx.lineTo(x, y);
  });
  ctx.lineTo(W, H);
  ctx.closePath();
  ctx.fillStyle = "rgba(91,140,255,.18)";
  ctx.fill();
  // line
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = (i / (n - 1 || 1)) * W;
    const y = H - (p.cost / max) * (H - 8) - 4;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = "#5b8cff";
  ctx.lineWidth = 2;
  ctx.stroke();
}

function renderByAgent(rows) {
  const max = Math.max(...rows.map((r) => r.cost), 1e-9);
  $("by-agent").innerHTML =
    rows
      .slice(0, 15)
      .map(
        (r) =>
          `<div class="bar-row"><span class="name" title="${r.name}">${r.name}</span>` +
          `<span class="bar-track"><span class="bar-fill" style="width:${(r.cost / max) * 100}%"></span></span>` +
          `<span class="cost">${fmt(r.cost)}</span></div>`
      )
      .join("") || '<div class="muted">no data</div>';
}

function renderByModel(rows) {
  const max = Math.max(...rows.map((r) => r.cost), 1e-9);
  $("by-model").innerHTML =
    rows
      .slice(0, 15)
      .map((r) => {
        const tok = `${(r.total_tokens || 0).toLocaleString()} tokens · ${r.observations} obs`;
        return (
          `<div class="bar-row"><span class="name" title="${r.model}">${r.model}</span>` +
          `<span class="bar-track"><span class="bar-fill" style="width:${(r.cost / max) * 100}%"></span></span>` +
          `<span class="cost" title="${tok}">${fmt(r.cost)}</span></div>`
        );
      })
      .join("") || '<div class="muted">no data</div>';
}

function renderHighlights(h) {
  const t = h.most_expensive_trace;
  const s = h.most_expensive_session;
  const rows = [];
  if (t)
    rows.push(
      `<div class="hl"><div class="k">most expensive trace</div>` +
        `<div class="v">${t.name || "?"} — ${fmt(t.cost)}<br><span class="k">${t.id || ""}</span></div></div>`
    );
  if (s)
    rows.push(
      `<div class="hl"><div class="k">most expensive ticket</div>` +
        `<div class="v">${s.session_id} — ${fmt(s.cost)} (${s.count} traces)</div></div>`
    );
  $("highlights").innerHTML = rows.join("") || '<div class="muted">no data</div>';
}

function renderReconcile(rows) {
  $("reconcile").innerHTML = rows
    .map((r) => {
      if (!r.configured)
        return `<div class="recon-row"><span>${r.project}</span><span class="muted" style="grid-column: 2 / -1">no OpenRouter key configured</span></div>`;
      if (r.error)
        return `<div class="recon-row"><span>${r.project}</span><span class="drift" style="grid-column: 2 / -1">${r.error}</span></div>`;
      const bal = r.balance ? `bal ${fmt(r.balance.remaining)}` : "";
      if (r.detail)
        return `<div class="recon-row"><span>${r.project}</span><span class="muted">${r.detail}</span><span class="muted">${bal}</span><span></span><span></span></div>`;
      const pill = r.within_tolerance
        ? '<span class="pill ok">clean</span>'
        : '<span class="pill bad">drift</span>';
      return (
        `<div class="recon-row"><span>${r.project}</span>` +
        `<span class="muted">provider ${fmt(r.provider_delta_usd)}</span>` +
        `<span class="muted">traced ${fmt(r.langfuse_cost_usd)}` +
        (r.langfuse_total_cost_usd != null &&
        Math.abs(r.langfuse_total_cost_usd - r.langfuse_cost_usd) > 1e-9
          ? ` (all ${fmt(r.langfuse_total_cost_usd)})`
          : "") +
        `</span>` +
        `<span class="${r.within_tolerance ? "ok" : "drift"}">Δ ${fmt(r.drift_usd)}</span>` +
        `<span>${pill} <span class="muted">${bal}</span></span></div>`
      );
    })
    .join("");
}

// Best-effort warning banner from the last (scheduled or manual) reconcile.
async function loadReconBanner() {
  const el = $("recon-banner");
  if (!el) return;
  try {
    const last = await getJSON("/api/reconcile/last");
    if (!last || last.status !== "warning") {
      el.hidden = true;
      return;
    }
    const bad = (last.results || []).filter(
      (r) => r.error || r.within_tolerance === false,
    );
    const when = last.generated_at
      ? new Date(last.generated_at).toLocaleString()
      : "";
    const items = bad
      .map((r) =>
        r.error
          ? `${r.project}: ${r.error}`
          : `${r.project}: Δ ${fmt(r.drift_usd)} (provider ${fmt(
              r.provider_delta_usd,
            )} vs traced ${fmt(r.langfuse_cost_usd)})`,
      )
      .join(" · ");
    el.innerHTML = `<b>⚠ cost reconciliation drift</b> — ${items} <span class="banner-when">checked ${when}</span>`;
    el.hidden = false;
  } catch (_e) {
    el.hidden = true;
  }
}

async function refresh() {
  setStatus("loading…");
  try {
    const backend = $("backend").value;
    // The fine-grained (trace-based) trend can't be split by backend; when a
    // backend is selected, use the day-granular per-backend trend instead.
    const trendPath =
      backend === "all"
        ? "/api/trend" + qs()
        : "/api/backend-trend" + qs() + "&backend=" + encodeURIComponent(backend);
    const [s, trend, agents, models, hi] = await Promise.all([
      getJSON("/api/summary" + qs()),
      getJSON(trendPath),
      getJSON("/api/by-agent" + qs()),
      getJSON("/api/by-model" + qs()),
      getJSON("/api/highlights" + qs()),
    ]);
    populateBackends(models);
    const modelRows =
      backend === "all" ? models : models.filter((m) => m.backend === backend);
    renderSummary(s, backend, modelRows);
    renderTrend(trend);
    renderByAgent(agents);
    renderByModel(modelRows);
    renderHighlights(hi);
    setStatus("updated " + new Date().toLocaleTimeString());
  } catch (e) {
    setStatus("error: " + e.message);
  }
}

async function runReconcile() {
  setStatus("reconciling…");
  try {
    const rows = await getJSON("/api/reconcile?project=" + $("project").value);
    renderReconcile(rows);
    await loadReconBanner();
    setStatus("reconciled " + new Date().toLocaleTimeString());
  } catch (e) {
    setStatus("reconcile error: " + e.message);
  }
}

$("refresh").onclick = refresh;
$("project").onchange = refresh;
$("backend").onchange = refresh;
$("window").onchange = refresh;
$("reconcile-btn").onclick = runReconcile;

(async () => {
  await loadProjects();
  await refresh();
  await loadReconBanner();
})();
