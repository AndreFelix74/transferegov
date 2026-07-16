/* =====================================================================
   Cozinha Solidária — shared data layer (view_convenio)
   ===================================================================== */

const SHEET_ID = "1sS6T-EbMOtlIXRbY5OAgZtzb9nde9MnNAkWmfP4ruYc";
const GID = "307493429"; // aba view_convenio
const CSV_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${GID}`;

const GID_SOLICITACAO_RENDIMENTO = "1677659110"; // aba solicitacao_rendimento_aplicacao
const CSV_URL_SOLICITACAO_RENDIMENTO =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${GID_SOLICITACAO_RENDIMENTO}`;

const GID_SIG_PCS = "1768843796"; // aba SIG_PCS (atribuição técnico ↔ convênio)
const CSV_URL_SIG_PCS =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${GID_SIG_PCS}&headers=1`;

// Abas brutas do staging (load.py → sheet_name_from_csv)
const CSV_URL_PAGAMENTO =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent("pagamento")}`;
const CSV_URL_PAGAMENTO_TRIBUTO =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent("pagamento_tributo")}`;
const CSV_URL_VIEW_PAGAMENTO =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent("view_pagamento")}`;
const CSV_URL_VIEW_PLANO_APLICACAO =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent("view_plano_aplicacao_detalhado")}`;
const CSV_URL_COZINHA =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent("COZINHA")}`;

function csvUrlForGid(gid) {
  return `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${gid}`;
}

/** Tipo de instrumento: Fomento ou Edital {ANO_PROP}, como no painel gerencial. */
function getCategoriaTipo(row) {
  if ((row.MODALIDADE || "").trim().toUpperCase() === "TERMO DE FOMENTO") return "Fomento";
  const ano = (row.ANO_PROP || "").trim();
  return ano ? `Edital ${ano}` : "Sem ano informado";
}

function ordenarCategoriasTipo(categorias) {
  return [...categorias].sort((a, b) => {
    if (a === "Fomento") return 1;
    if (b === "Fomento") return -1;
    return a.localeCompare(b, "pt-BR");
  });
}

function parseCsv(url, { header = true } = {}) {
  return new Promise((resolve, reject) => {
    Papa.parse(url, {
      download: true,
      header,
      skipEmptyLines: true,
      complete: (resultado) => resolve(resultado.data || []),
      error: reject,
    });
  });
}

/** Soma uma coluna numérica agrupando por NR_CONVENIO. */
function sumByConvenio(rows, valueColumn) {
  const map = Object.create(null);
  for (const row of rows) {
    const nr = String(row.NR_CONVENIO || "").trim();
    if (!nr) continue;
    map[nr] = (map[nr] || 0) + parseNum(row[valueColumn]);
  }
  return map;
}

/**
 * Valor Executado por NR_CONVENIO (cálculo na interface):
 *   SUM(pagamento.VL_PAGO) + SUM(pagamento_tributo.VL_PAG_TRIBUTOS)
 * Ausência de um dos lados conta como zero.
 */
function buildValorExecutadoMap(pagamentos, tributos) {
  const pagamentosPorConvenio = sumByConvenio(pagamentos, "VL_PAGO");
  const tributosPorConvenio = sumByConvenio(tributos, "VL_PAG_TRIBUTOS");
  const map = Object.create(null);
  const keys = new Set([
    ...Object.keys(pagamentosPorConvenio),
    ...Object.keys(tributosPorConvenio),
  ]);
  for (const nr of keys) {
    map[nr] = (pagamentosPorConvenio[nr] || 0) + (tributosPorConvenio[nr] || 0);
  }
  return map;
}

function loadValorExecutadoMap() {
  return Promise.all([
    parseCsv(CSV_URL_PAGAMENTO),
    parseCsv(CSV_URL_PAGAMENTO_TRIBUTO),
  ]).then(([pagamentos, tributos]) => buildValorExecutadoMap(pagamentos, tributos));
}

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
