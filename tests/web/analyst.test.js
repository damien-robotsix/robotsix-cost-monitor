import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
	card,
	filingHTML,
	managerReply,
	proposalsHTML,
	render,
	renderTargeted,
} from '../../src/robotsix_cost_monitor/web/static/analyst.js';

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

describe('managerReply', () => {
	it('returns empty string for falsy input', () => {
		expect(managerReply(null)).toBe('');
		expect(managerReply(undefined)).toBe('');
	});

	it('returns reply.reply when present', () => {
		expect(managerReply({ reply: { reply: 'hello' } })).toBe('hello');
	});

	it('returns error when present and no reply', () => {
		expect(managerReply({ error: 'timeout' })).toBe('timeout');
	});

	it('returns empty string when neither reply nor error', () => {
		expect(managerReply({})).toBe('');
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

	it('renders full run with traces, proposals, and filed ticket', () => {
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
			filing_result: {
				filed: true,
				reply: { reply: 'thanks, will review' },
			},
		};
		render(run);

		// Meta cards
		const meta = document.getElementById('run-meta');
		expect(meta.innerHTML).toContain('last run');
		expect(meta.innerHTML).toContain('traces analyzed');
		expect(meta.innerHTML).toContain('1'); // trace count
		expect(meta.innerHTML).toContain('proposals');
		expect(meta.innerHTML).toContain('filed');

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

		// Ticket — filed
		const ticket = document.getElementById('ticket');
		expect(ticket.innerHTML).toContain('✓ filed');
		expect(ticket.innerHTML).toContain('thanks, will review');
	});

	it('renders filing failed branch', () => {
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
			filing_result: { error: 'API key missing' },
		});
		const ticket = document.getElementById('ticket');
		expect(ticket.innerHTML).toContain('filing failed');
		expect(ticket.innerHTML).toContain('✗');
		expect(ticket.innerHTML).toContain('API key missing');
	});

	it('renders not-filed branch when filing_result is null', () => {
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
			filing_result: null,
		});
		const ticket = document.getElementById('ticket');
		expect(ticket.innerHTML).toContain('not filed');
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
			filing_result: null,
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
			filing_result: null,
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
			filing_result: null,
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
		renderTargeted('target', { generated_at: 'x', detail: 'analysis timed out' }, () => '<h>header</h>');
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
			filing_result: { filed: true },
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

describe('filingHTML', () => {
	it('returns empty string for falsy input', () => {
		expect(filingHTML(null)).toBe('');
	});

	it('renders board manager reply', () => {
		const html = filingHTML({ reply: { reply: 'done' } });
		expect(html).toContain('board manager');
		expect(html).toContain('done');
	});

	it('renders error when present', () => {
		const html = filingHTML({ error: 'fail' });
		expect(html).toContain('fail');
	});
});
