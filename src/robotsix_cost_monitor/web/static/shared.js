"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (n) => "$" + (Number(n) || 0).toFixed(n >= 100 ? 0 : 2);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
  );

async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}
