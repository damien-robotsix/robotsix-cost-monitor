import { $, API, QS, esc, fmt, getJSON, setStatus } from './shared.js';

/**
 * @typedef {object} ProjectInfo
 * @property {string} slug
 * @property {string} name
 * @property {boolean} [reconcilable]
 */

/**
 * A component and the Langfuse projects (LLM functions) it owns.
 * @typedef {object} ComponentInfo
 * @property {string} component
 * @property {ProjectInfo[]} projects
 */

/**
 * @typedef {object} Summary
 * @property {number} total_cost
 * @property {number} window_hours
 * @property {ProjectCost[]} projects
 * @property {ComponentCost[]} [components]
 */

/**
 * @typedef {object} ProjectCost
 * @property {string} name
 * @property {string} [slug]
 * @property {string} [component]
 * @property {number} cost
 * @property {number} trace_count
 */

/**
 * @typedef {object} ComponentCost
 * @property {string} component
 * @property {number} cost
 * @property {number} trace_count
 * @property {ProjectCost[]} projects
 */

/**
 * @typedef {object} TrendPoint
 * @property {number} cost
 */

/**
 * @typedef {object} AgentRow
 * @property {string} name
 * @property {number} cost
 * @property {number} [openrouter_cost]
 * @property {number} [subscription_cost]
 * @property {number} [openrouter_count]
 * @property {number} [subscription_count]
 * @property {number} [total_cost]
 * @property {boolean} [marginal_reducible]
 */

/**
 * @typedef {object} ModelRow
 * @property {string} model
 * @property {string} [backend]
 * @property {number} cost
 * @property {number} total_tokens
 * @property {number} observations
 */

/**
 * @typedef {object} Highlights
 * @property {{name?: string, cost: number, id?: string}} [most_expensive_trace]
 * @property {{session_id: string, cost: number, count: number}} [most_expensive_session]
 */

/**
 * @typedef {object} ReconcileRow
 * @property {string} project
 * @property {boolean} [configured]
 * @property {string} [error]
 * @property {string} [detail]
 * @property {number} [provider_delta_usd]
 * @property {number} [langfuse_cost_usd]
 * @property {number} [langfuse_total_cost_usd]
 * @property {number} [drift_usd]
 * @property {boolean} [within_tolerance]
 * @property {boolean} [low_balance]
 * @property {{remaining: number}} [balance]
 */

/**
 * @typedef {object} ReconLast
 * @property {string} [status]
 * @property {string} [generated_at]
 * @property {ReconcileRow[]} [results]
 */

const qs = () =>
  `?${QS.PROJECT}=${/** @type {HTMLSelectElement} */ ($('project')).value}&${QS.HOURS}=${/** @type {HTMLInputElement | HTMLSelectElement} */ ($('window')).value}`;

/**
 * Populate the scope selector from discovered components.
 *
 * Components are top-level options; a component's projects are nested beneath
 * it when it owns more than one, since a lone project would just repeat its
 * component. The backend resolves either level, so this stays purely a display
 * concern — a newly onboarded component appears here with no code change.
 *
 * @returns {Promise<void>}
 */
export async function loadProjects() {
  const components = await getJSON(API.COMPONENTS);
  const sel = $('project');
  for (const c of components) {
    if (c.projects.length > 1) {
      const group = document.createElement('optgroup');
      group.label = c.component;
      const all = document.createElement('option');
      all.value = c.component;
      all.textContent = `${c.component} (all)`;
      group.appendChild(all);
      for (const p of c.projects) {
        const opt = document.createElement('option');
        opt.value = p.slug;
        opt.textContent = p.name;
        group.appendChild(opt);
      }
      sel.appendChild(group);
    } else {
      const opt = document.createElement('option');
      opt.value = c.component;
      opt.textContent = c.component;
      sel.appendChild(opt);
    }
  }
}

/**
 * Populate the backend filter dropdown from model rows.
 * @param {ModelRow[]} modelRows
 */
export function populateBackends(modelRows) {
  const sel = /** @type {HTMLSelectElement} */ ($('backend'));
  const cur = sel.value;
  const set = new Set(modelRows.map((r) => r.backend).filter((b) => b !== undefined));
  if (cur !== 'all') set.add(cur); // keep the current selection selectable
  const backends = [...set].sort();
  sel.innerHTML = `<option value="all">all backends</option>${backends
    .map((b) => `<option value="${b}"${b === cur ? ' selected' : ''}>${b}</option>`)
    .join('')}`;
  sel.value = cur;
}

/**
 * Render the summary cards section.
 * @param {Summary} s
 * @param {string} backend
 * @param {ModelRow[]} modelRows
 */
export function renderSummary(s, backend, modelRows) {
  // Lead with components; break a component out into its projects only when it
  // owns more than one, so a single-project component isn't shown twice.
  const scopeCards = (s.components ?? []).flatMap((c) =>
    c.projects.length > 1
      ? [
          { label: c.component, value: fmt(c.cost), sub: `${c.trace_count} traces` },
          ...c.projects.map((p) => ({
            label: `↳ ${p.name}`,
            value: fmt(p.cost),
            sub: `${p.trace_count} traces`,
          })),
        ]
      : [{ label: c.component, value: fmt(c.cost), sub: `${c.trace_count} traces` }],
  );
  const cards =
    backend && backend !== 'all'
      ? [
          { label: `total · ${backend}`, value: fmt(s.total_cost), sub: `${s.window_hours}h window` },
          ...scopeCards,
        ]
      : [
          { label: 'total cost', value: fmt(s.total_cost), sub: `${s.window_hours}h window` },
          ...scopeCards,
        ];
  $('summary-cards').innerHTML = cards
    .map(
      (c) =>
        `<div class="card"><div class="label">${esc(c.label)}</div>` +
        `<div class="value">${esc(c.value)}</div><div class="sub">${esc(c.sub)}</div></div>`,
    )
    .join('');
}

/**
 * Render the cost trend chart (line + area on canvas).
 * @param {TrendPoint[]} points
 */
export function renderTrend(points) {
  const canvas = /** @type {HTMLCanvasElement} */ ($('trend'));
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  canvas.width = canvas.clientWidth;
  const W = canvas.width;
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
  ctx.fillStyle = 'rgba(91,140,255,.18)';
  ctx.fill();
  // line
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = (i / (n - 1 || 1)) * W;
    const y = H - (p.cost / max) * (H - 8) - 4;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = '#5b8cff';
  ctx.lineWidth = 2;
  ctx.stroke();
}

/**
 * Render the by-agent cost bar chart.
 * @param {AgentRow[]} rows
 */
export function renderByAgent(rows) {
  const max = Math.max(...rows.map((r) => r.cost), 1e-9);
  $('by-agent').innerHTML =
    rows
      .map(
        (r) =>
          `<div class="bar-row"><span class="name" title="${esc(r.name)}">${esc(r.name)}</span>` +
          `<span class="bar-track"><span class="bar-fill" style="width:${(r.cost / max) * 100}%"></span></span>` +
          `<span class="cost">${fmt(r.cost)}</span></div>`,
      )
      .join('') || '<div class="muted">no data</div>';
}

/**
 * Render the by-model cost bar chart.
 * @param {ModelRow[]} rows
 */
export function renderByModel(rows) {
  const max = Math.max(...rows.map((r) => r.cost), 1e-9);
  $('by-model').innerHTML =
    rows
      .slice(0, 15)
      .map((r) => {
        const tok = `${(r.total_tokens || 0).toLocaleString()} tokens · ${r.observations} obs`;
        return (
          `<div class="bar-row"><span class="name" title="${esc(r.model)}">${esc(r.model)}</span>` +
          `<span class="bar-track"><span class="bar-fill" style="width:${(r.cost / max) * 100}%"></span></span>` +
          `<span class="cost" title="${tok}">${fmt(r.cost)}</span></div>`
        );
      })
      .join('') || '<div class="muted">no data</div>';
}

/**
 * Render the highlights section (most expensive trace/session).
 * @param {Highlights} h
 */
export function renderHighlights(h) {
  const t = h.most_expensive_trace;
  const s = h.most_expensive_session;
  const rows = [];
  if (t)
    rows.push(
      `<div class="hl"><div class="k">most expensive trace</div><div class="v">${esc(t.name || '?')} — ${fmt(t.cost)}<br><span class="k">${esc(t.id || '')}</span></div></div>`,
    );
  if (s)
    rows.push(
      `<div class="hl"><div class="k">most expensive session</div><div class="v">${esc(s.session_id)} — ${fmt(s.cost)} (${s.count} traces)</div></div>`,
    );
  $('highlights').innerHTML = rows.join('') || '<div class="muted">no data</div>';
}

/**
 * Render the reconciliation results table.
 * @param {ReconcileRow[]} rows
 */
export function renderReconcile(rows) {
  $('reconcile').innerHTML = rows
    .map((r) => {
      if (!r.configured)
        return `<div class="recon-row"><span>${esc(r.project)}</span><span class="muted" style="grid-column: 2 / -1">no OpenRouter key configured</span></div>`;
      if (r.error)
        return `<div class="recon-row"><span>${esc(r.project)}</span><span class="drift" style="grid-column: 2 / -1">${esc(r.error)}</span></div>`;
      const bal = r.balance ? `bal ${fmt(r.balance.remaining)}` : '';
      if (r.detail)
        return `<div class="recon-row"><span>${esc(r.project)}</span><span class="muted">${esc(r.detail)}</span><span class="muted">${bal}</span><span></span><span></span></div>`;
      const pill = r.low_balance
        ? '<span class="pill bad">low bal</span>'
        : r.within_tolerance
          ? '<span class="pill ok">clean</span>'
          : '<span class="pill bad">drift</span>';
      return `<div class="recon-row"><span>${esc(r.project)}</span><span class="muted">provider ${fmt(r.provider_delta_usd)}</span><span class="muted">traced ${fmt(r.langfuse_cost_usd)}${r.langfuse_total_cost_usd !== undefined && r.langfuse_total_cost_usd !== null && Math.abs(r.langfuse_total_cost_usd - (r.langfuse_cost_usd ?? 0)) > 1e-9 ? ` (all ${fmt(r.langfuse_total_cost_usd)})` : ''}</span><span class="${r.within_tolerance ? 'ok' : 'drift'}">Δ ${fmt(r.drift_usd)}</span><span>${pill} <span class="muted">${bal}</span></span></div>`;
    })
    .join('');
}

// Warning banner for the last (scheduled or manual) reconcile — only shown when
// there's drift. Pure renderer over an /api/reconcile/last payload.
/**
 * Show/hide the reconciliation drift warning banner.
 * @param {ReconLast | null} last
 */
export function renderReconBanner(last) {
  const el = $('recon-banner');
  if (!el) return;
  if (!last || last.status !== 'warning') {
    el.hidden = true;
    return;
  }
  const bad = (last.results || []).filter(
    (r) => r.error || r.within_tolerance === false || r.low_balance,
  );
  const when = last.generated_at ? new Date(last.generated_at).toLocaleString() : '';
  const items = bad
    .map((r) => {
      if (r.error) return `${esc(r.project)}: ${esc(r.error)}`;
      if (r.low_balance)
        return r.balance
          ? `${esc(r.project)}: low balance — $${fmt(r.balance.remaining)} remaining`
          : `${esc(r.project)}: low balance`;
      return `${esc(r.project)}: Δ ${fmt(r.drift_usd)} (provider ${fmt(r.provider_delta_usd)} vs traced ${fmt(r.langfuse_cost_usd)})`;
    })
    .join(' · ');
  el.innerHTML = `<b>⚠ cost reconciliation warning</b> — ${items} <span class="banner-when">checked ${when}</span>`;
  el.hidden = false;
}

/**
 * Update the 'last checked' timestamp label.
 * @param {ReconLast | null} last
 */
export function renderReconWhen(last) {
  const el = $('recon-when');
  if (!el) return;
  el.textContent = last?.generated_at
    ? `last checked ${new Date(last.generated_at).toLocaleString()}`
    : '';
}

/**
 * Refresh the banner + 'last checked' label from the persisted last reconcile,
 * without touching the results table (used after a manual, possibly
 * project-scoped, run that already rendered its own rows).
 * @returns {Promise<void>}
 */
export async function refreshReconMeta() {
  try {
    const last = await getJSON(API.RECONCILE_LAST);
    renderReconBanner(last);
    renderReconWhen(last);
  } catch (_e) {
    /* best-effort */
  }
}

/**
 * On page load, render whatever the last (scheduled) reconcile left behind — the
 * banner, the 'last checked' time, AND the results table — so the last run is
 * visible after a reload/restart without having to click 'run'. The table and
 * last.json are volume-persisted, so this survives container restarts.
 * @returns {Promise<void>}
 */
export async function loadLastReconcile() {
  try {
    const last = await getJSON(API.RECONCILE_LAST);
    renderReconBanner(last);
    renderReconWhen(last);
    if (last && Array.isArray(last.results) && last.results.length) {
      renderReconcile(last.results);
    }
  } catch (_e) {
    /* no-op */
  }
}

/**
 * Refresh all dashboard panels (summary, trend, agents, models, highlights).
 * @returns {Promise<void>}
 */
export async function refresh() {
  setStatus('loading…');
  try {
    const backend = /** @type {HTMLSelectElement} */ ($('backend')).value;
    // The fine-grained (trace-based) trend can't be split by backend; when a
    // backend is selected, use the day-granular per-backend trend instead.
    const trendPath =
      backend === 'all'
        ? `${API.TREND}${qs()}`
        : `${API.BACKEND_TREND}${qs()}&${QS.BACKEND}=${encodeURIComponent(backend)}`;
    const [s, trend, agents, models, hi] = await Promise.all([
      getJSON(`${API.SUMMARY}${qs()}&${QS.BACKEND}=${encodeURIComponent(backend)}`),
      getJSON(trendPath),
      getJSON(`${API.BY_AGENT}${qs()}&${QS.BACKEND}=${encodeURIComponent(backend)}`),
      getJSON(`${API.BY_MODEL}${qs()}`),
      getJSON(`${API.HIGHLIGHTS}${qs()}&${QS.BACKEND}=${encodeURIComponent(backend)}`),
    ]);
    populateBackends(models);
    const modelRows =
      backend === 'all'
        ? models
        : models.filter((/** @type {ModelRow} */ m) => m.backend === backend);
    renderSummary(s, backend, modelRows);
    renderTrend(trend);
    renderByAgent(agents);
    renderByModel(modelRows);
    renderHighlights(hi);
    setStatus(`updated ${new Date().toLocaleTimeString()}`);
  } catch (e) {
    const err = /** @type {Error} */ (e);
    setStatus(`error: ${err.message}`);
  }
}

/**
 * Run reconciliation for the selected project and render the results.
 * @returns {Promise<void>}
 */
export async function runReconcile() {
  setStatus('reconciling…');
  try {
    const rows = await getJSON(
      `${API.RECONCILE}?${QS.PROJECT}=${/** @type {HTMLSelectElement} */ ($('project')).value}`,
    );
    renderReconcile(rows);
    await refreshReconMeta();
    setStatus(`reconciled ${new Date().toLocaleTimeString()}`);
  } catch (e) {
    const err = /** @type {Error} */ (e);
    setStatus(`reconcile error: ${err.message}`);
  }
}

// --- bootstrap (guarded: skipped under Node/Vitest import) ---
if (typeof document !== 'undefined' && document.getElementById('refresh')) {
  $('refresh').onclick = refresh;
  $('project').onchange = refresh;
  $('backend').onchange = refresh;
  $('window').onchange = refresh;
  $('reconcile-btn').onclick = runReconcile;

  (async () => {
    await loadProjects();
    await refresh();
    await loadLastReconcile();
  })();
}
