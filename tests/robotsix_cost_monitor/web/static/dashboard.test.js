import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  loadLastReconcile,
  loadProjects,
  populateBackends,
  refresh,
  refreshReconMeta,
  renderByAgent,
  renderByAgentSegmented,
  renderByModel,
  renderHighlights,
  renderReconBanner,
  renderReconWhen,
  renderReconcile,
  renderSummary,
  renderTrend,
  runReconcile,
} from '../../../../src/robotsix_cost_monitor/web/static/dashboard.js';

function fixture(html) {
  document.body.innerHTML = html;
}

describe('renderSummary', () => {
  it('renders all-backend summary with project cards', () => {
    fixture('<section id="summary-cards"></section>');
    const s = {
      total_cost: 123.45,
      window_hours: 24,
      projects: [
        { name: 'proj-a', cost: 80, trace_count: 10 },
        { name: 'proj-b', cost: 43.45, trace_count: 3 },
      ],
    };
    renderSummary(s, 'all', []);

    const el = document.getElementById('summary-cards');
    expect(el.children.length).toBe(3); // total + 2 projects
    expect(el.innerHTML).toContain('total cost');
    expect(el.innerHTML).toContain('$123');
    expect(el.innerHTML).toContain('proj-a');
    expect(el.innerHTML).toContain('$80');
    expect(el.innerHTML).toContain('proj-b');
    expect(el.innerHTML).toContain('$43.45');
  });

  it('renders selected-backend summary with single card', () => {
    fixture('<section id="summary-cards"></section>');
    const s = { total_cost: 999, window_hours: 6 };
    // Caller is responsible for filtering by backend; simulate pre-filtered rows.
    const modelRows = [
      { cost: 10, model: 'gpt-4', backend: 'openai' },
      { cost: 20, model: 'claude', backend: 'openai' },
    ];
    renderSummary(s, 'openai', modelRows);

    const el = document.getElementById('summary-cards');
    expect(el.children.length).toBe(1);
    expect(el.innerHTML).toContain('total');
    expect(el.innerHTML).toContain('openai');
    expect(el.innerHTML).toContain('$30.00');
  });

  it('renders all-backend with no projects', () => {
    fixture('<section id="summary-cards"></section>');
    const s = { total_cost: 0, window_hours: 1, projects: [] };
    renderSummary(s, 'all', []);
    const el = document.getElementById('summary-cards');
    expect(el.children.length).toBe(1); // only total
    expect(el.innerHTML).toContain('$0.00');
  });
});

describe('renderTrend', () => {
  let mockCtx;

  beforeEach(() => {
    mockCtx = {
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      stroke: vi.fn(),
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
    };

    // Stub getContext to return our mock
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mockCtx);
  });

  afterAll(() => {
    vi.restoreAllMocks();
  });

  it('renders trend without throwing and calls canvas methods', () => {
    fixture('<canvas id="trend" height="120"></canvas>');
    const canvas = document.getElementById('trend');
    // jsdom doesn't compute clientWidth; set it manually
    Object.defineProperty(canvas, 'clientWidth', { value: 800, writable: true });

    const points = [{ cost: 1 }, { cost: 2 }, { cost: 3 }];

    expect(() => renderTrend(points)).not.toThrow();

    expect(mockCtx.clearRect).toHaveBeenCalled();
    expect(mockCtx.beginPath).toHaveBeenCalled();
    expect(mockCtx.moveTo).toHaveBeenCalled();
    expect(mockCtx.lineTo).toHaveBeenCalled();
    expect(mockCtx.closePath).toHaveBeenCalled();
    expect(mockCtx.fill).toHaveBeenCalled();
    expect(mockCtx.stroke).toHaveBeenCalled();
    // fillStyle and strokeStyle should have been set
    expect(mockCtx.fillStyle).toBe('rgba(91,140,255,.18)');
    expect(mockCtx.strokeStyle).toBe('#5b8cff');
    expect(mockCtx.lineWidth).toBe(2);
  });

  it('handles single-point trend', () => {
    fixture('<canvas id="trend" height="120"></canvas>');
    const canvas = document.getElementById('trend');
    Object.defineProperty(canvas, 'clientWidth', { value: 800, writable: true });

    expect(() => renderTrend([{ cost: 5 }])).not.toThrow();
    expect(mockCtx.clearRect).toHaveBeenCalled();
    expect(mockCtx.stroke).toHaveBeenCalled();
  });
});

describe('renderByAgent', () => {
  it('renders bar rows for given agents', () => {
    fixture('<div id="by-agent"></div>');
    const rows = [
      { name: 'Agent A', cost: 50 },
      { name: 'Agent & B', cost: 25 },
    ];
    renderByAgent(rows);
    const el = document.getElementById('by-agent');
    expect(el.children.length).toBe(2);
    expect(el.innerHTML).toContain('Agent A');
    expect(el.innerHTML).toContain('Agent &amp; B'); // escaped
    expect(el.innerHTML).toContain('$50.00');
    expect(el.innerHTML).toContain('$25.00');
  });

  it('renders no data placeholder for empty rows', () => {
    fixture('<div id="by-agent"></div>');
    renderByAgent([]);
    const el = document.getElementById('by-agent');
    expect(el.innerHTML).toContain('no data');
    expect(el.querySelector('.muted')).not.toBeNull();
  });
});

describe('renderByAgentSegmented', () => {
  function data(overrides = {}) {
    return {
      rows: [],
      subscription_cap: 0,
      subscription_cap_pct: null,
      subscription_count_total: 0,
      window_hours: 24,
      openrouter_marginal_total: 0,
      subscription_estimate_total: 0,
      ...overrides,
    };
  }

  it('renders openrouter and subscription costs as distinct columns with call counts', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(
      data({
        rows: [
          {
            name: 'plan',
            openrouter_cost: 2.5,
            subscription_cost: 0,
            openrouter_count: 10,
            subscription_count: 0,
            total_cost: 2.5,
            marginal_reducible: true,
          },
          {
            name: 'refine',
            openrouter_cost: 0.0003,
            subscription_cost: 51.15,
            openrouter_count: 183,
            subscription_count: 183,
            total_cost: 51.1503,
            marginal_reducible: true,
          },
        ],
        subscription_cap: 1000,
        subscription_cap_pct: 0.183,
        subscription_count_total: 183,
      }),
    );
    const el = document.getElementById('by-agent-segmented');

    // volume-vs-cap signal present
    expect(el.innerHTML).toContain('Subscription call volume: 183 / 1000');
    expect(el.innerHTML).toContain('(18.3%)');

    // header labels
    expect(el.innerHTML).toContain('OpenRouter (marginal $)');
    expect(el.innerHTML).toContain('Subscription (estimate)');

    // first row: plan (higher openrouter_cost)
    const rows = el.querySelectorAll('.bar-row:not(.seg-header)');
    expect(rows.length).toBe(2);
    expect(rows[0].innerHTML).toContain('plan');
    expect(rows[0].innerHTML).toContain('$2.50');
    expect(rows[0].innerHTML).toContain('$0.00');

    // second row: refine
    expect(rows[1].innerHTML).toContain('refine');
    expect(rows[1].innerHTML).toContain('$51.15');
    // call counts rendered
    expect(rows[0].innerHTML).toContain('10 calls');
    expect(rows[1].innerHTML).toContain('183 calls');
  });

  it('preserves input ordering (rows rendered as supplied)', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(
      data({
        rows: [
          {
            name: 'c',
            openrouter_cost: 1,
            subscription_cost: 0,
            openrouter_count: 1,
            subscription_count: 0,
            total_cost: 1,
            marginal_reducible: true,
          },
          {
            name: 'a',
            openrouter_cost: 3,
            subscription_cost: 0,
            openrouter_count: 1,
            subscription_count: 0,
            total_cost: 3,
            marginal_reducible: true,
          },
          {
            name: 'b',
            openrouter_cost: 2,
            subscription_cost: 0,
            openrouter_count: 1,
            subscription_count: 0,
            total_cost: 2,
            marginal_reducible: true,
          },
        ],
      }),
    );
    const el = document.getElementById('by-agent-segmented');
    const rows = el.querySelectorAll('.bar-row:not(.seg-header)');
    const names = [...rows].map((c) => c.querySelector('.name').textContent);
    expect(names).toEqual(['c', 'a', 'b']);
  });

  it('escapes agent names', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(
      data({
        rows: [
          {
            name: '<script>alert(1)</script>',
            openrouter_cost: 0,
            subscription_cost: 1,
            openrouter_count: 0,
            subscription_count: 1,
            total_cost: 1,
            marginal_reducible: false,
          },
        ],
      }),
    );
    const el = document.getElementById('by-agent-segmented');
    const nameEl = el.querySelector('.name');
    // Text content must be HTML-escaped (no raw <script> element rendered)
    expect(nameEl.innerHTML).toContain('&lt;script&gt;');
    expect(nameEl.textContent).toBe('<script>alert(1)</script>');
    // title attribute may serialize literal angle brackets (harmless);
    // quotes are escaped so attribute breakout is impossible
  });

  it('renders no data placeholder for empty rows', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(data({ rows: [] }));
    const el = document.getElementById('by-agent-segmented');
    expect(el.innerHTML).toContain('no data');
    expect(el.querySelector('.muted')).not.toBeNull();
  });

  it('badges subscription-only stages with "subscription — no model-switch"', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(
      data({
        rows: [
          {
            name: 'marginal-stage',
            openrouter_cost: 5,
            subscription_cost: 0,
            openrouter_count: 2,
            subscription_count: 0,
            total_cost: 5,
            marginal_reducible: true,
          },
          {
            name: 'claude_sdk agent',
            openrouter_cost: 0,
            subscription_cost: 1.17,
            openrouter_count: 0,
            subscription_count: 3,
            total_cost: 1.17,
            marginal_reducible: false,
          },
        ],
      }),
    );
    const el = document.getElementById('by-agent-segmented');
    // subscription-only row carries the badge
    const rows = el.querySelectorAll('.bar-row:not(.seg-header)');
    expect(rows[1].innerHTML).toContain('subscription — no model-switch');
    // marginal row does NOT
    expect(rows[0].innerHTML).not.toContain('subscription — no model-switch');
    // subscription-only row is de-emphasised
    expect(rows[1].classList.contains('subscription-only')).toBe(true);
    expect(rows[0].classList.contains('subscription-only')).toBe(false);
  });

  it('shows warning state when subscription_cap_pct >= 0.8', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(
      data({
        rows: [
          {
            name: 's',
            openrouter_cost: 0,
            subscription_cost: 1,
            openrouter_count: 0,
            subscription_count: 850,
            total_cost: 1,
            marginal_reducible: false,
          },
        ],
        subscription_cap: 1000,
        subscription_cap_pct: 0.85,
        subscription_count_total: 850,
      }),
    );
    const el = document.getElementById('by-agent-segmented');
    expect(el.innerHTML).toContain('850 / 1000');
    expect(el.innerHTML).toContain('(85.0%)');
    expect(el.innerHTML).toContain('near cap');
    expect(el.querySelector('.cap-info.cap-warn')).not.toBeNull();
  });

  it('shows "cap not configured" when subscription_cap is 0', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(
      data({
        rows: [
          {
            name: 's',
            openrouter_cost: 0,
            subscription_cost: 1,
            openrouter_count: 0,
            subscription_count: 10,
            total_cost: 1,
            marginal_reducible: false,
          },
        ],
        subscription_cap: 0,
        subscription_cap_pct: null,
        subscription_count_total: 10,
      }),
    );
    const el = document.getElementById('by-agent-segmented');
    expect(el.innerHTML).toContain('cap not configured');
    expect(el.querySelector('.cap-info.muted')).not.toBeNull();
  });

  it('shows "cap not configured" when subscription_cap is null/undefined', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(
      data({
        rows: [
          {
            name: 's',
            openrouter_cost: 0,
            subscription_cost: 1,
            openrouter_count: 0,
            subscription_count: 5,
            total_cost: 1,
            marginal_reducible: false,
          },
        ],
        subscription_cap: null,
        subscription_cap_pct: null,
        subscription_count_total: 5,
      }),
    );
    const el = document.getElementById('by-agent-segmented');
    expect(el.innerHTML).toContain('cap not configured');
  });

  it('renders marginal (openrouter) cost as primary signal, not subscription', () => {
    fixture('<div id="by-agent-segmented"></div>');
    renderByAgentSegmented(
      data({
        rows: [
          {
            name: 'mixed',
            openrouter_cost: 4.2,
            subscription_cost: 80.0,
            openrouter_count: 5,
            subscription_count: 100,
            total_cost: 84.2,
            marginal_reducible: true,
          },
        ],
      }),
    );
    const el = document.getElementById('by-agent-segmented');
    // The bar-fill width is based on openrouter_cost
    const barFill = el.querySelector('.bar-fill');
    expect(barFill).not.toBeNull();
    // openrouter cost value is present
    expect(el.innerHTML).toContain('$4.20');
    // subscription cost is there but as secondary
    expect(el.innerHTML).toContain('$80');
  });
});

describe('renderByModel', () => {
  it('renders bar rows for given models', () => {
    fixture('<div id="by-model"></div>');
    const rows = [
      { model: 'gpt-4', cost: 100, total_tokens: 5000, observations: 3 },
      { model: 'claude', cost: 60, total_tokens: 2000, observations: 1 },
    ];
    renderByModel(rows);
    const el = document.getElementById('by-model');
    expect(el.children.length).toBe(2);
    expect(el.innerHTML).toContain('gpt-4');
    expect(el.innerHTML).toContain('$100');
    expect(el.innerHTML).toContain('5,000 tokens');
  });

  it('caps at 15 rows via .slice(0, 15)', () => {
    fixture('<div id="by-model"></div>');
    const rows = Array.from({ length: 20 }, (_, i) => ({
      model: `model-${i}`,
      cost: 1,
      total_tokens: 0,
      observations: 0,
    }));
    renderByModel(rows);
    const el = document.getElementById('by-model');
    expect(el.children.length).toBe(15);
  });

  it('renders no data placeholder for empty rows', () => {
    fixture('<div id="by-model"></div>');
    renderByModel([]);
    const el = document.getElementById('by-model');
    expect(el.innerHTML).toContain('no data');
  });
});

describe('renderReconcile', () => {
  it('renders not-configured message', () => {
    fixture('<div id="reconcile"></div>');
    renderReconcile([{ project: 'myproj', configured: false }]);
    const el = document.getElementById('reconcile');
    expect(el.innerHTML).toContain('myproj');
    expect(el.innerHTML).toContain('no OpenRouter key configured');
  });

  it('renders error message', () => {
    fixture('<div id="reconcile"></div>');
    renderReconcile([{ project: 'errproj', configured: true, error: 'timeout' }]);
    const el = document.getElementById('reconcile');
    expect(el.innerHTML).toContain('errproj');
    expect(el.innerHTML).toContain('timeout');
  });

  it('renders clean pill when within_tolerance is true', () => {
    fixture('<div id="reconcile"></div>');
    renderReconcile([
      {
        project: 'cleanproj',
        configured: true,
        provider_delta_usd: 10,
        langfuse_cost_usd: 10,
        drift_usd: 0,
        within_tolerance: true,
      },
    ]);
    const el = document.getElementById('reconcile');
    expect(el.innerHTML).toContain('cleanproj');
    expect(el.innerHTML).toContain('clean');
    expect(el.querySelector('.pill.ok')).not.toBeNull();
  });

  it('renders drift pill when within_tolerance is false', () => {
    fixture('<div id="reconcile"></div>');
    renderReconcile([
      {
        project: 'driftproj',
        configured: true,
        provider_delta_usd: 12,
        langfuse_cost_usd: 10,
        drift_usd: 2,
        within_tolerance: false,
      },
    ]);
    const el = document.getElementById('reconcile');
    expect(el.innerHTML).toContain('driftproj');
    expect(el.innerHTML).toContain('drift');
    expect(el.querySelector('.pill.bad')).not.toBeNull();
  });

  it('renders detail-only row', () => {
    fixture('<div id="reconcile"></div>');
    renderReconcile([
      {
        project: 'detailproj',
        configured: true,
        detail: 'no data for window',
      },
    ]);
    const el = document.getElementById('reconcile');
    expect(el.innerHTML).toContain('detailproj');
    expect(el.innerHTML).toContain('no data for window');
  });

  it('renders balance info when present', () => {
    fixture('<div id="reconcile"></div>');
    renderReconcile([
      {
        project: 'balproj',
        configured: true,
        provider_delta_usd: 5,
        langfuse_cost_usd: 5,
        drift_usd: 0,
        within_tolerance: true,
        balance: { remaining: 42.5 },
      },
    ]);
    const el = document.getElementById('reconcile');
    expect(el.innerHTML).toContain('$42.50');
  });
});

describe('renderHighlights', () => {
  it('renders most expensive trace and session', () => {
    fixture('<div id="highlights"></div>');
    renderHighlights({
      most_expensive_trace: {
        id: 'trace-1',
        name: 'big call',
        cost: 99.9,
      },
      most_expensive_session: {
        session_id: 'sess-1',
        cost: 500,
        count: 12,
      },
    });
    const el = document.getElementById('highlights');
    expect(el.innerHTML).toContain('most expensive trace');
    expect(el.innerHTML).toContain('big call');
    expect(el.innerHTML).toContain('$99.90');
    expect(el.innerHTML).toContain('most expensive ticket');
    expect(el.innerHTML).toContain('sess-1');
    expect(el.innerHTML).toContain('$500');
    expect(el.innerHTML).toContain('12 traces');
  });

  it('renders no data placeholder for empty highlights', () => {
    fixture('<div id="highlights"></div>');
    renderHighlights({});
    const el = document.getElementById('highlights');
    expect(el.innerHTML).toContain('no data');
  });
});

describe('loadProjects', () => {
  it('fetches projects and populates the dropdown', async () => {
    fixture('<select id="project"></select>');
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { slug: 'proj-a', name: 'Project A' },
        { slug: 'proj-b', name: 'Project B' },
      ],
    });

    try {
      await loadProjects();
      const sel = /** @type {HTMLSelectElement} */ (document.getElementById('project'));
      expect(sel.children.length).toBe(2);
      expect(sel.children[0].value).toBe('proj-a');
      expect(sel.children[0].textContent).toBe('Project A');
      expect(sel.children[1].value).toBe('proj-b');
      expect(sel.children[1].textContent).toBe('Project B');
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});

describe('populateBackends', () => {
  it('populates backend dropdown from model rows', () => {
    fixture('<select id="backend"><option value="all">all backends</option></select>');
    const modelRows = [
      { model: 'gpt-4', backend: 'openai', cost: 10, total_tokens: 100, observations: 2 },
      { model: 'claude', backend: 'anthropic', cost: 5, total_tokens: 50, observations: 1 },
    ];
    populateBackends(modelRows);

    const sel = /** @type {HTMLSelectElement} */ (document.getElementById('backend'));
    const options = [...sel.children].map((o) => o.value);
    expect(options).toContain('all');
    expect(options).toContain('anthropic');
    expect(options).toContain('openai');
  });

  it('deduplicates backends', () => {
    fixture('<select id="backend"><option value="all">all backends</option></select>');
    const modelRows = [
      { model: 'gpt-4', backend: 'openai', cost: 10, total_tokens: 100, observations: 2 },
      { model: 'gpt-3.5', backend: 'openai', cost: 5, total_tokens: 50, observations: 1 },
      { model: 'claude', backend: 'anthropic', cost: 3, total_tokens: 30, observations: 1 },
    ];
    populateBackends(modelRows);

    const sel = /** @type {HTMLSelectElement} */ (document.getElementById('backend'));
    const options = [...sel.children].map((o) => o.value);
    expect(options.filter((v) => v === 'openai').length).toBe(1);
    expect(options.filter((v) => v === 'anthropic').length).toBe(1);
  });

  it('preserves current selection', () => {
    fixture(
      '<select id="backend"><option value="all">all backends</option><option value="anthropic">anthropic</option></select>',
    );
    const sel = /** @type {HTMLSelectElement} */ (document.getElementById('backend'));
    sel.value = 'anthropic';

    const modelRows = [
      { model: 'gpt-4', backend: 'openai', cost: 10, total_tokens: 100, observations: 2 },
      { model: 'claude', backend: 'anthropic', cost: 5, total_tokens: 50, observations: 1 },
    ];
    populateBackends(modelRows);

    expect(sel.value).toBe('anthropic');
  });

  it('handles rows without backend field', () => {
    fixture('<select id="backend"><option value="all">all backends</option></select>');
    const modelRows = [{ model: 'unknown-model', cost: 10, total_tokens: 100, observations: 2 }];
    populateBackends(modelRows);

    const sel = /** @type {HTMLSelectElement} */ (document.getElementById('backend'));
    const options = [...sel.children].map((o) => o.value);
    // Only 'all' since rows without backend are filtered out
    expect(options).toEqual(['all']);
  });
});

describe('renderReconBanner', () => {
  it('hides banner when last is null', () => {
    fixture('<div id="recon-banner"></div>');
    renderReconBanner(null);
    const el = document.getElementById('recon-banner');
    expect(el.hidden).toBe(true);
  });

  it('hides banner when status is not warning', () => {
    fixture('<div id="recon-banner"></div>');
    renderReconBanner({ status: 'ok', results: [], generated_at: '2025-01-01T00:00:00Z' });
    const el = document.getElementById('recon-banner');
    expect(el.hidden).toBe(true);
  });

  it('shows banner with drift details when status is warning', () => {
    fixture('<div id="recon-banner"></div>');
    const last = {
      status: 'warning',
      generated_at: '2025-06-15T12:00:00Z',
      results: [
        {
          project: 'myproj',
          provider_delta_usd: 12,
          langfuse_cost_usd: 10,
          drift_usd: 2,
          within_tolerance: false,
        },
      ],
    };
    renderReconBanner(last);
    const el = document.getElementById('recon-banner');
    expect(el.hidden).toBe(false);
    expect(el.innerHTML).toContain('cost reconciliation drift');
    expect(el.innerHTML).toContain('myproj');
    expect(el.innerHTML).toContain('$2.00');
  });

  it('shows banner with error details', () => {
    fixture('<div id="recon-banner"></div>');
    const last = {
      status: 'warning',
      generated_at: '2025-06-15T12:00:00Z',
      results: [{ project: 'badproj', error: 'timeout' }],
    };
    renderReconBanner(last);
    const el = document.getElementById('recon-banner');
    expect(el.hidden).toBe(false);
    expect(el.innerHTML).toContain('badproj');
    expect(el.innerHTML).toContain('timeout');
  });

  it('does nothing when recon-banner element is missing', () => {
    fixture('');
    expect(() => renderReconBanner(null)).not.toThrow();
  });
});

describe('renderReconWhen', () => {
  it('renders last checked timestamp', () => {
    fixture('<div id="recon-when"></div>');
    renderReconWhen({ generated_at: '2025-06-15T12:00:00Z' });
    const el = document.getElementById('recon-when');
    expect(el.textContent).toContain('last checked');
  });

  it('renders empty string for null last', () => {
    fixture('<div id="recon-when">old</div>');
    renderReconWhen(null);
    const el = document.getElementById('recon-when');
    expect(el.textContent).toBe('');
  });

  it('renders empty string when generated_at is missing', () => {
    fixture('<div id="recon-when">old</div>');
    renderReconWhen({});
    const el = document.getElementById('recon-when');
    expect(el.textContent).toBe('');
  });

  it('does nothing when recon-when element is missing', () => {
    fixture('');
    expect(() => renderReconWhen(null)).not.toThrow();
  });
});

describe('refreshReconMeta', () => {
  it('fetches last reconcile and updates banner and when', async () => {
    const last = {
      status: 'warning',
      generated_at: '2025-06-15T12:00:00Z',
      results: [
        {
          project: 'myproj',
          provider_delta_usd: 12,
          langfuse_cost_usd: 10,
          drift_usd: 2,
          within_tolerance: false,
        },
      ],
    };
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => last,
    });

    fixture('<div id="recon-banner"></div><div id="recon-when">old</div>');

    try {
      await refreshReconMeta();
      const banner = document.getElementById('recon-banner');
      const when = document.getElementById('recon-when');
      expect(banner.hidden).toBe(false);
      expect(banner.innerHTML).toContain('cost reconciliation drift');
      expect(when.textContent).toContain('last checked');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('handles fetch errors gracefully', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network'));

    fixture('<div id="recon-banner"></div><div id="recon-when">old</div>');

    try {
      await refreshReconMeta();
      // Should not throw; banner remains as-is
      const banner = document.getElementById('recon-banner');
      expect(banner).not.toBeNull();
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});

describe('loadLastReconcile', () => {
  it('renders last reconcile banner, when, and results table', async () => {
    const last = {
      status: 'ok',
      generated_at: '2025-06-15T12:00:00Z',
      results: [
        {
          project: 'cleanproj',
          configured: true,
          provider_delta_usd: 10,
          langfuse_cost_usd: 10,
          drift_usd: 0,
          within_tolerance: true,
        },
      ],
    };
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => last,
    });

    fixture(`
      <div id="recon-banner"></div>
      <div id="recon-when">old</div>
      <div id="reconcile"></div>
    `);

    try {
      await loadLastReconcile();
      const when = document.getElementById('recon-when');
      const reconcile = document.getElementById('reconcile');
      expect(when.textContent).toContain('last checked');
      expect(reconcile.innerHTML).toContain('cleanproj');
      expect(reconcile.innerHTML).toContain('clean');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('handles empty results gracefully', async () => {
    const last = {
      status: 'ok',
      generated_at: '2025-06-15T12:00:00Z',
      results: [],
    };
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => last,
    });

    fixture(`
      <div id="recon-banner"></div>
      <div id="recon-when">old</div>
      <div id="reconcile">old-table</div>
    `);

    try {
      await loadLastReconcile();
      // Results table should NOT be overwritten since results.length === 0
      const reconcile = document.getElementById('reconcile');
      expect(reconcile.innerHTML).toBe('old-table');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('handles fetch errors gracefully', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network'));

    fixture(`
      <div id="recon-banner"></div>
      <div id="recon-when">old</div>
      <div id="reconcile"></div>
    `);

    try {
      await loadLastReconcile();
      // Should not throw
      expect(true).toBe(true);
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});

describe('refresh', () => {
  let origFetch;

  beforeEach(() => {
    origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn((url) => {
      if (url.includes('/api/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ total_cost: 100, window_hours: 24, projects: [] }),
        });
      }
      if (url.includes('/api/trend')) {
        return Promise.resolve({
          ok: true,
          json: async () => [{ cost: 1 }, { cost: 2 }],
        });
      }
      if (url.includes('/api/by-agent-segmented')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            rows: [],
            subscription_cap: 0,
            subscription_cap_pct: null,
            subscription_count_total: 0,
          }),
        });
      }
      if (url.includes('/api/by-model')) {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }
      if (url.includes('/api/highlights')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({}),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
  });

  afterAll(() => {
    globalThis.fetch = origFetch;
  });

  it('refreshes all panels and sets status', async () => {
    fixture(`
      <select id="project"><option value="all">all</option></select>
      <select id="backend"><option value="all">all backends</option></select>
      <select id="window"><option value="24">24h</option></select>
      <div id="status">idle</div>
      <section id="summary-cards"></section>
      <canvas id="trend" height="120"></canvas>
      <div id="by-agent-segmented"></div>
      <div id="by-model"></div>
      <div id="highlights"></div>
    `);

    // Stub canvas getContext
    const mockCtx = {
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      stroke: vi.fn(),
    };
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mockCtx);
    // jsdom doesn't compute clientWidth
    const canvas = document.getElementById('trend');
    Object.defineProperty(canvas, 'clientWidth', { value: 800, writable: true });

    try {
      await refresh();
      const status = document.getElementById('status');
      expect(status.textContent).toContain('updated');
      // Summary cards should be rendered
      const summary = document.getElementById('summary-cards');
      expect(summary.innerHTML).toContain('total cost');
      // by-model should render (empty → no data)
      const byModel = document.getElementById('by-model');
      expect(byModel.innerHTML).toContain('no data');
    } finally {
      vi.restoreAllMocks();
    }
  });

  it('handles fetch error and sets error status', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('fetch failed'));

    fixture(`
      <select id="project"><option value="all">all</option></select>
      <select id="backend"><option value="all">all backends</option></select>
      <select id="window"><option value="24">24h</option></select>
      <div id="status">idle</div>
    `);

    try {
      await refresh();
      const status = document.getElementById('status');
      expect(status.textContent).toContain('error');
      expect(status.textContent).toContain('fetch failed');
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});

describe('runReconcile', () => {
  it('triggers reconciliation and renders results', async () => {
    const rows = [
      {
        project: 'cleanproj',
        configured: true,
        provider_delta_usd: 10,
        langfuse_cost_usd: 10,
        drift_usd: 0,
        within_tolerance: true,
      },
    ];
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => rows,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ok', generated_at: '2025-06-15T12:00:00Z', results: [] }),
      });

    fixture(`
      <select id="project"><option value="cleanproj">cleanproj</option></select>
      <div id="status">idle</div>
      <div id="reconcile"></div>
      <div id="recon-banner"></div>
      <div id="recon-when">old</div>
    `);

    try {
      await runReconcile();
      const reconcile = document.getElementById('reconcile');
      expect(reconcile.innerHTML).toContain('cleanproj');
      expect(reconcile.innerHTML).toContain('clean');
      const status = document.getElementById('status');
      expect(status.textContent).toContain('reconciled');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('handles error and sets error status', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('reconcile failed'));

    fixture(`
      <select id="project"><option value="proj">proj</option></select>
      <div id="status">idle</div>
      <div id="reconcile"></div>
    `);

    try {
      await runReconcile();
      const status = document.getElementById('status');
      expect(status.textContent).toContain('reconcile error');
      expect(status.textContent).toContain('reconcile failed');
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});
