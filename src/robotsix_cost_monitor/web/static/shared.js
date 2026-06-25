"use strict";

/**
 * Shorthand for `document.getElementById`.
 * @param {string} id
 * @returns {HTMLElement | null}
 */
export const $ = (id) => document.getElementById(id);

/**
 * Format a number as USD.
 * @param {number | string} n
 * @returns {string}
 */
export const fmt = (n) => "$" + (Number(n) || 0).toFixed(n >= 100 ? 0 : 2);

/**
 * Escape HTML special characters.
 * @param {string | null | undefined} s
 * @returns {string}
 */
export const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
  );

/**
 * Fetch JSON from a relative path.
 * @param {string} path
 * @returns {Promise<any>}
 */
export async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}
