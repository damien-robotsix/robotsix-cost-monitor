import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  card,
  load,
  makeTargeted,
  proposalsHTML,
  render,
  renderTargeted,
  run,
  stageHeader,
  ticketHeader,
} from '../../../../src/robotsix_cost_monitor/web/static/analyst.js';

function fixture(html) {
  document.body.innerHTML = html;
}

describe('card', () => {
  it('renders a card div with label, value, sub', () => {
    const html = card('my label', 'my value', 'my sub');
    expect(html).toContain('<div class="card">');
    expect(html).toContain('my label');
    expect(html).toContain('my value');
    expect(html).toContain('my sub');
  });

  it('escapes HTML in label, value, sub', () => {
    const html = card('<b>', '&', '"');
    expect(html).toContain('&lt;b&gt;');
    expect(html).toContain('&amp;');
    expect(html).toContain('&quot;');
  });
});

describe('render', () => {
  it('renders placeholder for falsy run', () => {
    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
    `);
    render(null);
    expect(document.getElementById('run-meta').innerHTML).toContain('no run yet');
    for (const id of ['summary', 'analyzed', 'proposals', 'ticket']) {
      expect(document.getElementById(id).innerHTML).toContain('—');
    }
  });

  it('renders placeholder when enabled is false', () => {
    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
    `);
    render({ enabled: false, generated_at: '2024-01-01T00:00:00Z' });
    expect(document.getElementById('run-meta').innerHTML).toContain('no run yet');
    for (const id of ['summary', 'analyzed', 'proposals', 'ticket']) {
      expect(document.getElementById(id).innerHTML).toContain('—');
    }
  });

  it('renders placeholder when generated_at is missing', () => {
    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
    `);
    render({ enabled: true });
    expect(document.getElementById('run-meta').innerHTML).toContain('no run yet');
  });

  it('renders placeholder with detail message when run has detail', () => {
    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
    `);
    render({ enabled: true, detail: 'no data for this window' });
    expect(document.getElementById('run-meta').innerHTML).toContain('no data for this window');
  });

  it('renders full run with traces and proposals', () => {
    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
    `);
    const run = {
      enabled: true,
      generated_at: '2025-06-01T12:00:00Z',
      window_hours: 24,
      summary: 'Overall fleet summary text.',
      analyzed_traces: [
        {
          trace_id: 't1',
          project: 'proj-a',
          name: 'expensive-op',
          cost: 5.5,
          selection_reason: '#1 by cost',
          finding: 'uses too many tokens',
        },
      ],
      proposals: [
        {
          title: 'reduce tokens',
          estimated_saving: '~$10/mo',
          rationale: 'switch to smaller model',
        },
      ],
    };
    render(run);

    // Meta cards
    const meta = document.getElementById('run-meta');
    expect(meta.innerHTML).toContain('last run');
    expect(meta.innerHTML).toContain('traces analyzed');
    expect(meta.innerHTML).toContain('1'); // trace count
    expect(meta.innerHTML).toContain('proposals');
    expect(meta.innerHTML).not.toContain('tickets');

    // Summary
    expect(document.getElementById('summary').innerHTML).toContain('Overall fleet summary text.');

    // Analyzed traces
    const analyzed = document.getElementById('analyzed');
    expect(analyzed.innerHTML).toContain('t1');
    expect(analyzed.innerHTML).toContain('proj-a');
    expect(analyzed.innerHTML).toContain('expensive-op');
    expect(analyzed.innerHTML).toContain('$5.50');
    expect(analyzed.innerHTML).toContain('#1 by cost');
    expect(analyzed.innerHTML).toContain('uses too many tokens');

    // Proposals
    const proposals = document.getElementById('proposals');
    expect(proposals.innerHTML).toContain('reduce tokens');
    expect(proposals.innerHTML).toContain('~$10/mo');
    expect(proposals.innerHTML).toContain('switch to smaller model');
  });

  it('renders empty traces placeholder', () => {
    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
    `);
    render({
      enabled: true,
      generated_at: '2025-06-01T12:00:00Z',
      window_hours: 24,
      analyzed_traces: [],
      proposals: [],
    });
    expect(document.getElementById('analyzed').innerHTML).toContain('no traces were analyzed');
  });

  it('renders empty proposals placeholder', () => {
    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
    `);
    render({
      enabled: true,
      generated_at: '2025-06-01T12:00:00Z',
      window_hours: 24,
      analyzed_traces: [],
      proposals: [],
    });
    expect(document.getElementById('proposals').innerHTML).toContain('no proposals');
  });

  it('renders empty summary placeholder', () => {
    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
    `);
    render({
      enabled: true,
      generated_at: '2025-06-01T12:00:00Z',
      window_hours: 24,
      analyzed_traces: [],
      proposals: [],
    });
    expect(document.getElementById('summary').innerHTML).toContain('—');
  });
});

describe('renderTargeted', () => {
  it('renders not-run-yet message for falsy run', () => {
    fixture('<div id="target"></div>');
    renderTargeted('target', null, () => '<h>header</h>');
    expect(document.getElementById('target').innerHTML).toContain('not run yet');
  });

  it('renders not-run-yet for run without generated_at', () => {
    fixture('<div id="target"></div>');
    renderTargeted('target', {}, () => '<h>header</h>');
    expect(document.getElementById('target').innerHTML).toContain('not run yet');
  });

  it('renders detail when run has detail', () => {
    fixture('<div id="target"></div>');
    renderTargeted(
      'target',
      { generated_at: 'x', detail: 'analysis timed out' },
      () => '<h>header</h>',
    );
    const el = document.getElementById('target');
    expect(el.innerHTML).toContain('analysis timed out');
    expect(el.innerHTML).not.toContain('<h>header</h>'); // header not rendered on detail
  });

  it('renders full targeted run with header, summary, proposals, filing', () => {
    fixture('<div id="target"></div>');
    const headerFn = (run) => `<b>header for ${run.ticket_id}</b>`;
    const run = {
      generated_at: '2025-06-01T12:00:00Z',
      ticket_id: 'T-123',
      total_cost: 50,
      trace_count: 7,
      history_available: true,
      summary: 'costly due to loops',
      proposals: [{ title: 'fix loop', estimated_saving: '$30', rationale: 'remove retry' }],
    };
    renderTargeted('target', run, headerFn);
    const el = document.getElementById('target');
    expect(el.innerHTML).toContain('header for T-123');
    expect(el.innerHTML).toContain('costly due to loops');
    expect(el.innerHTML).toContain('fix loop');
    expect(el.innerHTML).toContain('$30');
    expect(el.innerHTML).toContain('remove retry');
  });
});

describe('proposalsHTML', () => {
  it('renders no proposals placeholder for empty', () => {
    expect(proposalsHTML([])).toContain('no proposals');
    expect(proposalsHTML(null)).toContain('no proposals');
  });

  it('renders proposal items', () => {
    const html = proposalsHTML([{ title: 'p1', estimated_saving: '$10', rationale: 'r1' }]);
    expect(html).toContain('p1');
    expect(html).toContain('$10');
    expect(html).toContain('r1');
  });
});

describe('load', () => {
  it('fetches latest analyst run and renders it', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        enabled: true,
        generated_at: '2025-06-01T12:00:00Z',
        window_hours: 24,
        analyzed_traces: [],
        proposals: [],
      }),
    });

    fixture(`
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
      <div id="status">idle</div>
    `);

    try {
      await load();
      const meta = document.getElementById('run-meta');
      expect(meta.innerHTML).toContain('last run');
      const status = document.getElementById('status');
      expect(status.textContent).toBe('showing last run');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('handles fetch error and sets error status', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network'));

    fixture('<div id="status">idle</div>');

    try {
      await load();
      const status = document.getElementById('status');
      expect(status.textContent).toContain('load failed');
      expect(status.textContent).toContain('network');
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});

describe('run', () => {
  it('triggers POST analysis run and renders result', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        enabled: true,
        generated_at: '2025-06-01T12:00:00Z',
        window_hours: 24,
        analyzed_traces: [],
        proposals: [],
      }),
    });

    fixture(`
      <button id="run-btn">run</button>
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
      <div id="status">idle</div>
    `);

    try {
      await run();

      // Verify POST was made
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/analyst/run', { method: 'POST' });

      // Verify button is re-enabled
      const btn = /** @type {HTMLButtonElement} */ (document.getElementById('run-btn'));
      expect(btn.disabled).toBe(false);

      // Verify status updated
      const status = document.getElementById('status');
      expect(status.textContent).toBe('run complete');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('handles non-ok response and sets error status', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    fixture(`
      <button id="run-btn">run</button>
      <div id="status">idle</div>
    `);

    try {
      await run();
      const status = document.getElementById('status');
      expect(status.textContent).toContain('run failed');
      const btn = /** @type {HTMLButtonElement} */ (document.getElementById('run-btn'));
      expect(btn.disabled).toBe(false);
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('handles fetch rejection and sets error status', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('timeout'));

    fixture(`
      <button id="run-btn">run</button>
      <div id="status">idle</div>
    `);

    try {
      await run();
      const status = document.getElementById('status');
      expect(status.textContent).toContain('run failed');
      expect(status.textContent).toContain('timeout');
      const btn = /** @type {HTMLButtonElement} */ (document.getElementById('run-btn'));
      expect(btn.disabled).toBe(false);
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('disables button during run', async () => {
    // We verify the button starts enabled and is disabled during run
    // using a deferred promise to inspect mid-flight state
    let resolve;
    const deferred = new Promise((r) => {
      resolve = r;
    });
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockReturnValue(
      deferred.then(() => ({
        ok: true,
        json: async () => ({
          enabled: true,
          generated_at: '2025-06-01T12:00:00Z',
          window_hours: 24,
          analyzed_traces: [],
          proposals: [],
        }),
      })),
    );

    fixture(`
      <button id="run-btn">run</button>
      <section id="run-meta"></section>
      <div id="summary"></div>
      <div id="analyzed"></div>
      <div id="proposals"></div>
      <div id="ticket"></div>
      <div id="status">idle</div>
    `);

    try {
      const runPromise = run();
      // Button should be disabled while running
      const btn = /** @type {HTMLButtonElement} */ (document.getElementById('run-btn'));
      expect(btn.disabled).toBe(true);

      resolve(); // let fetch complete
      await runPromise;

      expect(btn.disabled).toBe(false);
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});

describe('ticketHeader', () => {
  it('renders ticket header with trace count and cost', () => {
    const html = ticketHeader({
      ticket_id: 'T-123',
      board_id: 'board-1',
      total_cost: 50,
      trace_count: 7,
      history_available: true,
      by_stage: [
        { name: 'plan', cost: 30 },
        { name: 'refine', cost: 20 },
      ],
    });
    expect(html).toContain('T-123');
    expect(html).toContain('board-1');
    expect(html).toContain('$50');
    expect(html).toContain('7 traces');
    expect(html).toContain('history');
    expect(html).toContain('plan');
    expect(html).toContain('$30');
    expect(html).toContain('refine');
    expect(html).toContain('$20');
  });

  it('uses session_id when ticket_id is missing', () => {
    const html = ticketHeader({
      session_id: 'sess-1',
      board_id: '',
      total_cost: 0,
      trace_count: 1,
      history_available: false,
    });
    expect(html).toContain('sess-1');
  });

  it('omits stage breakdown when by_stage is empty', () => {
    const html = ticketHeader({
      ticket_id: 'T-1',
      board_id: '',
      total_cost: 10,
      trace_count: 2,
      history_available: false,
      by_stage: [],
    });
    expect(html).not.toContain('by stage');
  });

  it('escapes HTML in ids and names', () => {
    const html = ticketHeader({
      ticket_id: '<script>',
      board_id: '">',
      total_cost: 1,
      trace_count: 1,
      history_available: false,
      by_stage: [{ name: '<b>bold</b>', cost: 1 }],
    });
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('&quot;&gt;');
    expect(html).toContain('&lt;b&gt;bold&lt;/b&gt;');
  });
});

describe('stageHeader', () => {
  it('renders stage header with cost and pct', () => {
    const html = stageHeader({
      stage: 'plan',
      total_cost: 30,
      pct_of_traced: 45,
      trace_count: 10,
      sample_size: 5,
    });
    expect(html).toContain('plan');
    expect(html).toContain('$30');
    expect(html).toContain('45%');
    expect(html).toContain('10 traces');
    expect(html).toContain('sampled 5');
  });

  it('escapes HTML in stage name', () => {
    const html = stageHeader({
      stage: '<b>x</b>',
      total_cost: 0,
      pct_of_traced: 0,
      trace_count: 0,
      sample_size: 0,
    });
    expect(html).toContain('&lt;b&gt;x&lt;/b&gt;');
  });
});

describe('makeTargeted', () => {
  it('returns a load function that fetches and renders targeted analysis', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        generated_at: '2025-06-01T12:00:00Z',
        ticket_id: 'T-1',
        total_cost: 100,
        trace_count: 5,
        history_available: false,
        proposals: [{ title: 'fix something', rationale: 'reason' }],
      }),
    });

    fixture(`
      <button id="ticket-btn">analyze</button>
      <div id="ticket-analysis"></div>
      <div id="status">idle</div>
    `);

    try {
      const loadFn = makeTargeted('ticket', 'ticket-btn', 'ticket-analysis', ticketHeader);
      expect(typeof loadFn).toBe('function');

      await loadFn();
      const el = document.getElementById('ticket-analysis');
      expect(el.innerHTML).toContain('T-1');
      expect(el.innerHTML).toContain('fix something');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('wires click handler to run targeted analysis via POST', async () => {
    const origFetch = globalThis.fetch;

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        generated_at: '2025-06-01T13:00:00Z',
        ticket_id: 'T-2',
        total_cost: 200,
        trace_count: 3,
        history_available: false,
      }),
    });

    fixture(`
      <button id="ticket-btn">analyze</button>
      <div id="ticket-analysis"></div>
      <div id="status">idle</div>
    `);

    try {
      makeTargeted('ticket', 'ticket-btn', 'ticket-analysis', ticketHeader);

      // Click the button
      const btn = /** @type {HTMLButtonElement} */ (document.getElementById('ticket-btn'));
      await btn.click();
      // Wait for the async click handler
      await vi.waitFor(() => {
        const el = document.getElementById('ticket-analysis');
        return el.innerHTML.includes('T-2');
      });

      const el = document.getElementById('ticket-analysis');
      expect(el.innerHTML).toContain('T-2');
      expect(el.innerHTML).toContain('$200');
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/analyst/ticket-run', { method: 'POST' });
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('handles load error gracefully', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('load error'));

    fixture(`
      <button id="ticket-btn">analyze</button>
      <div id="ticket-analysis"></div>
      <div id="status">idle</div>
    `);

    try {
      const loadFn = makeTargeted('ticket', 'ticket-btn', 'ticket-analysis', ticketHeader);
      await loadFn();
      const status = document.getElementById('status');
      expect(status.textContent).toContain('load failed');
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});
