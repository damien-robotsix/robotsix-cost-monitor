import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  renderByAgent,
  renderByAgentSegmented,
  renderByModel,
  renderHighlights,
  renderReconcile,
  renderSummary,
  renderTrend,
} from '../../src/robotsix_cost_monitor/web/static/dashboard.js';

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
