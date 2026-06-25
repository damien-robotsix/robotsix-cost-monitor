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
	it('renders openrouter and subscription costs as distinct columns', () => {
		fixture('<div id="by-agent"></div>');
		const rows = [
			{
				name: 'plan',
				openrouter_cost: 2.5,
				subscription_cost: 0,
				openrouter_count: 10,
				subscription_count: 0,
				total_cost: 2.5,
			},
			{
				name: 'refine',
				openrouter_cost: 0.0003,
				subscription_cost: 51.15,
				openrouter_count: 183,
				subscription_count: 183,
				total_cost: 51.1503,
			},
		];
		renderByAgentSegmented(rows);
		const el = document.getElementById('by-agent');
		expect(el.children.length).toBe(2);

		// First row should be plan (higher openrouter_cost, so ranked first)
		expect(el.children[0].innerHTML).toContain('plan');
		expect(el.children[0].innerHTML).toContain('$2.50');
		// plan has no subscription cost
		expect(el.children[0].innerHTML).toContain('est. (fixed subscription)');
		expect(el.children[0].innerHTML).toContain('$0.00');

		// Second row should be refine
		expect(el.children[1].innerHTML).toContain('refine');
		expect(el.children[1].innerHTML).toContain('$0.00'); // openrouter_cost ~0
		expect(el.children[1].innerHTML).toContain('est. (fixed subscription)');
		expect(el.children[1].innerHTML).toContain('$51.15');
	});

	it('preserves input ordering (openrouter_cost desc)', () => {
		fixture('<div id="by-agent"></div>');
		const rows = [
			{
				name: 'c',
				openrouter_cost: 1,
				subscription_cost: 0,
				openrouter_count: 1,
				subscription_count: 0,
				total_cost: 1,
			},
			{
				name: 'a',
				openrouter_cost: 3,
				subscription_cost: 0,
				openrouter_count: 1,
				subscription_count: 0,
				total_cost: 3,
			},
			{
				name: 'b',
				openrouter_cost: 2,
				subscription_cost: 0,
				openrouter_count: 1,
				subscription_count: 0,
				total_cost: 2,
			},
		];
		renderByAgentSegmented(rows);
		const el = document.getElementById('by-agent');
		const names = [...el.children].map((c) => c.querySelector('.name').textContent);
		// Input order is preserved (backend already sorts; renderer renders as-is)
		expect(names).toEqual(['c', 'a', 'b']);
	});

	it('escapes agent names', () => {
		fixture('<div id="by-agent"></div>');
		renderByAgentSegmented([
			{
				name: '<script>alert(1)</script>',
				openrouter_cost: 0,
				subscription_cost: 1,
				openrouter_count: 0,
				subscription_count: 1,
				total_cost: 1,
			},
		]);
		const el = document.getElementById('by-agent');
		expect(el.innerHTML).not.toContain('<script>');
		expect(el.innerHTML).toContain('&lt;script&gt;');
	});

	it('renders no data placeholder for empty rows', () => {
		fixture('<div id="by-agent"></div>');
		renderByAgentSegmented([]);
		const el = document.getElementById('by-agent');
		expect(el.innerHTML).toContain('no data');
		expect(el.querySelector('.muted')).not.toBeNull();
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
