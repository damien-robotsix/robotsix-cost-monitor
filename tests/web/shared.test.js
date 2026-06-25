import { describe, expect, it, vi } from 'vitest';
import { $, esc, fmt, getJSON } from '../../src/robotsix_cost_monitor/web/static/shared.js';

describe('fmt', () => {
  it('formats zero', () => {
    expect(fmt(0)).toBe('$0.00');
  });

  it('formats a single-digit integer', () => {
    expect(fmt(5)).toBe('$5.00');
  });

  it('formats a number with cents', () => {
    expect(fmt(99.5)).toBe('$99.50');
  });

  it('formats 100 without decimals (n >= 100 branch)', () => {
    expect(fmt(100)).toBe('$100');
  });

  it('formats 150 without decimals', () => {
    expect(fmt(150)).toBe('$150');
  });

  it('formats null as $0.00 (Number(null) = 0)', () => {
    expect(fmt(null)).toBe('$0.00');
  });

  it('formats undefined as $0.00', () => {
    expect(fmt(undefined)).toBe('$0.00');
  });

  it('formats a string number', () => {
    expect(fmt('42.5')).toBe('$42.50');
  });
});

describe('esc', () => {
  it('escapes HTML special characters', () => {
    expect(esc('<a href="x">&')).toBe('&lt;a href=&quot;x&quot;&gt;&amp;');
  });

  it('returns empty string for null', () => {
    expect(esc(null)).toBe('');
  });

  it('returns empty string for undefined', () => {
    expect(esc(undefined)).toBe('');
  });

  it('returns string as-is when no special chars', () => {
    expect(esc('hello world')).toBe('hello world');
  });

  it('converts numbers to strings', () => {
    expect(esc(42)).toBe('42');
  });
});

describe('$', () => {
  it('returns an element by id', () => {
    document.body.innerHTML = '<div id="x">hi</div>';
    const el = $('x');
    expect(el).not.toBeNull();
    expect(el.textContent).toBe('hi');
  });

  it('returns null for missing id', () => {
    document.body.innerHTML = '';
    expect($('missing')).toBeNull();
  });
});

describe('getJSON', () => {
  it('resolves parsed JSON on ok response', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ a: 1 }),
    });

    try {
      const result = await getJSON('/api/test');
      expect(result).toEqual({ a: 1 });
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/test');
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('rejects with status message on non-ok response', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
    });

    try {
      await expect(getJSON('/api/bad')).rejects.toThrow('→ 503');
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});
