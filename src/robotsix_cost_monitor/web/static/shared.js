/**
 * Shorthand for `document.getElementById`.
 *
 * TypeScript note: the return type is declared as `HTMLElement` (non-null)
 * because every call site in the app assumes the target element exists in the
 * current page; the two call-sites that previously checked for null perform
 * harmless dead-code checks.
 *
 * @param {string} id
 * @returns {HTMLElement}
 */
export const $ = (id) => /** @type {HTMLElement} */ (document.getElementById(id));

/**
 * Format a number as USD.
 * @param {number | string | null | undefined} n
 * @returns {string}
 */
export const fmt = (n) => `$${(Number(n) || 0).toFixed(Number(n) >= 100 ? 0 : 2)}`;

/**
 * Escape HTML special characters.
 * @param {string | null | undefined} s
 * @returns {string}
 */
export const esc = (s) =>
  String(s ?? '').replace(
    /[&<>"]/g,
    (c) => /** @type {string} */ ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]),
  );

/**
 * Fetch JSON from a relative path.
 * @param {string} path
 * @returns {Promise<any>}
 */
/**
 * Update the status text element.
 * @param {string} msg
 */
export const setStatus = (msg) => {
  $('status').textContent = msg;
};

export async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}
