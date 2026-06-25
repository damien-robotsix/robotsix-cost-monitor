import { $, esc, fmt, getJSON } from './shared.js';

/**
 * @typedef {object} AnalystRun
 * @property {boolean} [enabled]
 * @property {string} [generated_at]
 * @property {string} [detail]
 * @property {number} [window_hours]
 * @property {string} [summary]
 * @property {TraceAnalysis[]} [analyzed_traces]
 * @property {Proposal[]} [proposals]
 * @property {FilingResult} [filing_result]
 * @property {number} [total_cost]
 * @property {number} [trace_count]
 * @property {boolean} [history_available]
 * @property {string} [ticket_id]
 * @property {string} [session_id]
 * @property {string} [board_id]
 * @property {StageBreakdown[]} [by_stage]
 * @property {string} [stage]
 * @property {number} [pct_of_traced]
 * @property {number} [sample_size]
 */

/**
 * @typedef {object} TraceAnalysis
 * @property {string} trace_id
 * @property {string} [project]
 * @property {string} [name]
 * @property {number} cost
 * @property {string} [selection_reason]
 * @property {number} [rank]
 * @property {string} [finding]
 */

/**
 * @typedef {object} Proposal
 * @property {string} title
 * @property {string} [estimated_saving]
 * @property {string} [rationale]
 */

/**
 * @typedef {object} FilingResult
 * @property {boolean} [filed]
 * @property {string} [error]
 * @property {string | {reply: {reply: string}}} [reply]
 */

/**
 * @typedef {object} StageBreakdown
 * @property {string} name
 * @property {number} cost
 */

/**
 * Update the status text element.
 * @param {string} m
 */
export const setStatus = (m) => {
  $('status').textContent = m;
};

/**
 * Render a metric card as HTML.
 * @param {string} label
 * @param {string} value
 * @param {string} sub
 * @returns {string}
 */
export function card(label, value, sub) {
  return `<div class="card"><div class="label">${esc(label)}</div><div class="value">${esc(
    value,
  )}</div><div class="sub">${esc(sub)}</div></div>`;
}

/**
 * Extract the human-readable reply from a manager FilingResult.
 * @param {FilingResult | null | undefined} rr
 * @returns {string}
 */
export function managerReply(rr) {
  if (!rr) return '';
  if (rr.reply?.reply) return rr.reply.reply; // manager NL reply (legacy dict body)
  if (typeof rr.reply === 'string') return rr.reply; // BrokeredRequester returns string
  if (rr.error) return rr.error;
  return '';
}

/**
 * Render the full analyst run (summary + traces + proposals + filing status).
 * @param {AnalystRun | null} run
 */
export function render(run) {
  if (!run || run.enabled === false || !run.generated_at) {
    $('run-meta').innerHTML = card(
      'last run',
      '—',
      (run?.detail) || 'no run yet — press “run analysis”',
    );
    for (const id of ['summary', 'analyzed', 'proposals', 'ticket'])
      $(id).innerHTML = "<p class='muted'>—</p>";
    return;
  }

  const traces = run.analyzed_traces || [];
  const props = run.proposals || [];
  const fr = run.filing_result || null;

  $('run-meta').innerHTML = [
    card('last run', new Date(run.generated_at).toLocaleString(), `window ${run.window_hours}h`),
    card('traces analyzed', traces.length, ''),
    card('proposals', props.length, ''),
    card('tickets', fr?.filed ? 'filed' : '—', fr && fr.filed ? 'via board manager' : ''),
  ].join('');

  $('summary').innerHTML = run.summary ? `<p>${esc(run.summary)}</p>` : "<p class='muted'>—</p>";

  $('analyzed').innerHTML = traces.length
    ? traces
        .map(
          (t) => `
      <div class="item">
        <div class="item-head">
          <span class="mono">${esc(t.trace_id)}</span>
          <span class="muted">${esc(t.project || '')}${t.name ? ` · ${esc(t.name)}` : ''} · <b>${fmt(t.cost)}</b></span>
        </div>
        <div class="item-body"><b>selected:</b> ${esc(
          t.selection_reason || (t.rank ? `#${t.rank} by cost` : 'top-cost trace'),
        )}</div>
        <div class="item-body"><b>analysis:</b> ${esc(t.finding || '(no finding)')}</div>
      </div>`,
        )
        .join('')
    : "<p class='muted'>no traces were analyzed</p>";

  $('proposals').innerHTML = props.length
    ? props
        .map(
          (p) => `
      <div class="item">
        <div class="item-head">
          <span>${esc(p.title)}</span>
          ${p.estimated_saving ? `<span class="save">${esc(p.estimated_saving)}</span>` : ''}
        </div>
        <div class="item-body">${esc(p.rationale || '')}</div>
      </div>`,
        )
        .join('')
    : "<p class='muted'>no proposals</p>";

  if (!fr) {
    $('ticket').innerHTML =
      "<p class='muted'>proposals not filed (no broker configured, or no proposals)</p>";
  } else if (fr.error) {
    $('ticket').innerHTML = `
      <div class="item">
        <div class="item-head"><span>filing failed</span><span class="bad">✗</span></div>
        <div class="item-body">${esc(fr.error)}</div>
      </div>`;
  } else {
    const reply = managerReply(fr);
    $('ticket').innerHTML = `
      <div class="item">
        <div class="item-head">
          <span>board manager</span>
          <span class="ok">✓ filed</span>
        </div>
        <div class="item-body">${esc(reply || '(no reply)')}</div>
        <div class="muted">tickets created/refined by the board manager from the ${props.length} proposal(s) above.</div>
      </div>`;
  }
}

/**
 * Fetch and render the latest analyst run.
 * @returns {Promise<void>}
 */
export async function load() {
  try {
    render(await getJSON('/api/analyst/proposals'));
    setStatus('showing last run');
  } catch (e) {
    setStatus(`load failed: ${e.message}`);
  }
}

/**
 * Trigger a new analyst run and render the result.
 * @returns {Promise<void>}
 */
export async function run() {
  const btn = $('run-btn');
  btn.disabled = true;
  setStatus('running analysis… this can take a couple of minutes');
  try {
    const r = await fetch('/api/analyst/run', { method: 'POST' });
    if (!r.ok) throw new Error(`run → ${r.status}`);
    render(await r.json());
    setStatus('run complete');
  } catch (e) {
    setStatus(`run failed: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
}

// --- targeted analyses (most costly ticket / stage) ---

/**
 * Render proposal list as HTML.
 * @param {Proposal[] | null} props
 * @returns {string}
 */
export function proposalsHTML(props) {
  if (!props || !props.length) return "<p class='muted'>no proposals</p>";
  return props
    .map(
      (p) => `
      <div class="item">
        <div class="item-head">
          <span>${esc(p.title)}</span>
          ${p.estimated_saving ? `<span class="save">${esc(p.estimated_saving)}</span>` : ''}
        </div>
        <div class="item-body">${esc(p.rationale || '')}</div>
      </div>`,
    )
    .join('');
}

/**
 * Render filing result as HTML (board manager reply).
 * @param {FilingResult | null} fr
 * @returns {string}
 */
export function filingHTML(fr) {
  if (!fr) return '';
  const reply = managerReply(fr);
  return `<div class="item-body muted"><b>board manager:</b> ${esc(reply || fr.error || '')}</div>`;
}

/**
 * Render a targeted analysis (ticket or stage) into a container.
 * @param {string} id - container element id
 * @param {AnalystRun | null} run
 * @param {(run: AnalystRun) => string} headerHTML
 */
export function renderTargeted(id, run, headerHTML) {
  const el = $(id);
  if (!run || !run.generated_at) {
    el.innerHTML = "<p class='muted'>not run yet — press “analyze”</p>";
    return;
  }
  if (run.detail) {
    el.innerHTML = `<p class='muted'>${esc(run.detail)}</p>`;
    return;
  }
  el.innerHTML = `
    <div class="item">${headerHTML(run)}</div>
    ${run.summary ? `<div class="item-body"><b>why it's costly:</b> ${esc(run.summary)}</div>` : ''}
    ${proposalsHTML(run.proposals)}
    ${filingHTML(run.filing_result)}`;
}

/**
 * Header HTML for a ticket-level targeted analysis.
 * @param {AnalystRun} run
 * @returns {string}
 */
export function ticketHeader(run) {
  const stages = (run.by_stage || []).map((s) => `${esc(s.name)} ${fmt(s.cost)}`).join(' · ');
  return `
    <div class="item-head">
      <span class="mono">${esc(run.ticket_id || run.session_id || '')}</span>
      <span class="muted">${esc(run.board_id || '')} · <b>${fmt(run.total_cost)}</b> · ${run.trace_count} traces${run.history_available ? ' · history ✓' : ''}</span>
    </div>
    ${stages ? `<div class="item-body muted">by stage: ${stages}</div>` : ''}`;
}

/**
 * Header HTML for a stage-level targeted analysis.
 * @param {AnalystRun} run
 * @returns {string}
 */
export function stageHeader(run) {
  return `
    <div class="item-head">
      <span>${esc(run.stage || '')}</span>
      <span class="muted"><b>${fmt(run.total_cost)}</b> · ${run.pct_of_traced}% of spend · ${run.trace_count} traces (sampled ${run.sample_size})</span>
    </div>`;
}

/**
 * Wire up a targeted analysis button (ticket or stage).
 * @param {'ticket' | 'stage'} kind
 * @param {string} btnId - button element id
 * @param {string} containerId - result container element id
 * @param {(run: AnalystRun) => string} headerFn
 * @returns {() => Promise<void>} initial load function
 */
export function makeTargeted(kind, btnId, containerId, headerFn) {
  const loadFn = async () => {
    try {
      renderTargeted(containerId, await getJSON(`/api/analyst/${kind}`), headerFn);
    } catch (e) {
      setStatus(`${kind} load failed: ${e.message}`);
    }
  };
  const btn = $(btnId);
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    setStatus(`analyzing most costly ${kind}… this can take a couple of minutes`);
    try {
      const r = await fetch(`/api/analyst/${kind}-run`, { method: 'POST' });
      if (!r.ok) throw new Error(`${kind}-run → ${r.status}`);
      renderTargeted(containerId, await r.json(), headerFn);
      setStatus(`${kind} analysis complete`);
    } catch (e) {
      setStatus(`${kind} run failed: ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  });
  return loadFn;
}

// --- bootstrap (guarded: skipped under Node/Vitest import) ---
if (typeof document !== 'undefined' && document.getElementById('run-btn')) {
  const loadTicket = makeTargeted('ticket', 'ticket-btn', 'ticket-analysis', ticketHeader);
  const loadStage = makeTargeted('stage', 'stage-btn', 'stage-analysis', stageHeader);

  $('run-btn').addEventListener('click', run);
  load();
  loadTicket();
  loadStage();
}
