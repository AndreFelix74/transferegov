/* =====================================================================
   Cozinha Solidária — shared data layer (view_convenio)
   ===================================================================== */

const SHEET_ID = "1sS6T-EbMOtlIXRbY5OAgZtzb9nde9MnNAkWmfP4ruYc";
const GID = "307493429"; // aba view_convenio
const CSV_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${GID}`;

/* Paleta de marca — objeto semântico + derivados para gráficos */
const BRAND_COLORS = {
  laranja: "#e45946",
  roxo: "#69438c",
  amarelo: "#ff9c00",
  verde: "#317c5d",
};

const BRAND_PALETTE = [
  BRAND_COLORS.laranja,
  BRAND_COLORS.roxo,
  BRAND_COLORS.amarelo,
  BRAND_COLORS.verde,
  "#355e7a",
  "#a42627",
  "#0c6642",
];

const CHART_CYCLE_COLORS = [
  BRAND_COLORS.roxo,
  BRAND_COLORS.verde,
  BRAND_COLORS.amarelo,
  BRAND_COLORS.laranja,
  "#8a7a9b",
  "#5f9c82",
];

/* Formato americano na planilha: ponto decimal, sem separador de milhar */
function parseNum(value) {
  const n = parseFloat(value);
  return Number.isNaN(n) ? 0 : n;
}

function parseDate(value) {
  if (!value) return null;
  const text = String(value).trim();
  if (!text) return null;
  const iso = /^\d{4}-\d{2}-\d{2}$/.test(text) ? `${text}T00:00:00` : text;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatBRL(value) {
  return (value || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  });
}

function formatBRLCompact(value) {
  const n = (value || 0) / 1_000_000;
  return `${n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`;
}

function setStatusBanner(selector, message, kind) {
  const el = document.querySelector(selector);
  el.textContent = message;
  el.className = "status-banner" + (kind ? ` ${kind}` : "");
}

function setStatusDot(selector, message, hasError) {
  const el = document.querySelector(selector);
  el.innerHTML = `<span class="ponto${hasError ? " erro" : ""}"></span><span>${message}</span>`;
}
