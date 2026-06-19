"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (n) => "$" + (Number(n) || 0).toFixed(n >= 100 ? 0 : 2);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
  );
const setStatus = (m) => {
  $("status").textContent = m;
};

async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

function card(label, value, sub) {
  return `<div class="card"><div class="label">${esc(label)}</div><div class="value">${esc(
    value,
  )}</div><div class="sub">${esc(sub)}</div></div>`;
}

function managerReply(rr) {
  if (!rr) return "";
  if (rr.reply && rr.reply.reply) return rr.reply.reply; // manager NL reply
  if (rr.error) return rr.error;
  return "";
}

function render(run) {
  if (!run || run.enabled === false || !run.generated_at) {
    $("run-meta").innerHTML = card(
      "last run",
      "—",
      (run && run.detail) || "no run yet — press “run analysis”",
    );
    for (const id of ["summary", "analyzed", "proposals", "ticket"])
      $(id).innerHTML = "<p class='muted'>—</p>";
    return;
  }

  const traces = run.analyzed_traces || [];
  const props = run.proposals || [];
  const fr = run.filing_result || null;

  $("run-meta").innerHTML = [
    card("last run", new Date(run.generated_at).toLocaleString(), `window ${run.window_hours}h`),
    card("traces analyzed", traces.length, ""),
    card("proposals", props.length, ""),
    card("tickets", fr && fr.filed ? "filed" : "—", fr && fr.filed ? "via board manager" : ""),
  ].join("");

  $("summary").innerHTML = run.summary
    ? `<p>${esc(run.summary)}</p>`
    : "<p class='muted'>—</p>";

  $("analyzed").innerHTML = traces.length
    ? traces
        .map(
          (t) => `
      <div class="item">
        <div class="item-head">
          <span class="mono">${esc(t.trace_id)}</span>
          <span class="muted">${esc(t.project || "")}${t.name ? " · " + esc(t.name) : ""} · <b>${fmt(t.cost)}</b></span>
        </div>
        <div class="item-body"><b>selected:</b> ${esc(
          t.selection_reason ||
            (t.rank ? `#${t.rank} by cost` : "top-cost trace"),
        )}</div>
        <div class="item-body"><b>analysis:</b> ${esc(t.finding || "(no finding)")}</div>
      </div>`,
        )
        .join("")
    : "<p class='muted'>no traces were analyzed</p>";

  $("proposals").innerHTML = props.length
    ? props
        .map(
          (p) => `
      <div class="item">
        <div class="item-head">
          <span>${esc(p.title)}</span>
          ${p.estimated_saving ? `<span class="save">${esc(p.estimated_saving)}</span>` : ""}
        </div>
        <div class="item-body">${esc(p.rationale || "")}</div>
      </div>`,
        )
        .join("")
    : "<p class='muted'>no proposals</p>";

  if (!fr) {
    $("ticket").innerHTML =
      "<p class='muted'>proposals not filed (no broker configured, or no proposals)</p>";
  } else if (fr.error) {
    $("ticket").innerHTML = `
      <div class="item">
        <div class="item-head"><span>filing failed</span><span class="bad">✗</span></div>
        <div class="item-body">${esc(fr.error)}</div>
      </div>`;
  } else {
    const reply = managerReply(fr);
    $("ticket").innerHTML = `
      <div class="item">
        <div class="item-head">
          <span>board manager</span>
          <span class="ok">✓ filed</span>
        </div>
        <div class="item-body">${esc(reply || "(no reply)")}</div>
        <div class="muted">tickets created/refined by the board manager from the ${props.length} proposal(s) above.</div>
      </div>`;
  }
}

async function load() {
  try {
    render(await getJSON("/api/analyst/proposals"));
    setStatus("showing last run");
  } catch (e) {
    setStatus("load failed: " + e.message);
  }
}

async function run() {
  const btn = $("run-btn");
  btn.disabled = true;
  setStatus("running analysis… this can take a couple of minutes");
  try {
    const r = await fetch("/api/analyst/run", { method: "POST" });
    if (!r.ok) throw new Error(`run → ${r.status}`);
    render(await r.json());
    setStatus("run complete");
  } catch (e) {
    setStatus("run failed: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

$("run-btn").addEventListener("click", run);
load();
