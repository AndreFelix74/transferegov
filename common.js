/* =====================================================================
   Cozinha Solidária — camada compartilhada de dados SICONV
   Código em inglês; nomes de colunas/abas e valores de domínio em PT.
   ===================================================================== */

/* --- 1. Constants & URLs --- */

const SHEET_ID = "1sS6T-EbMOtlIXRbY5OAgZtzb9nde9MnNAkWmfP4ruYc";
const GID = "307493429"; // aba view_convenio
const CSV_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${GID}`;

const GID_SOLICITACAO_RENDIMENTO = "1677659110"; // aba solicitacao_rendimento_aplicacao
const CSV_URL_SOLICITACAO_RENDIMENTO =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${GID_SOLICITACAO_RENDIMENTO}`;

const GID_SIG_PCS = "1768843796"; // aba SIG_PCS (atribuição técnico ↔ convênio)
const CSV_URL_SIG_PCS =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${GID_SIG_PCS}&headers=1`;

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
const CSV_URL_ATIVIDADES_COZINHAS =
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent("atividades_cozinhas")}`;

const PROPOSTA_DETAIL_URL =
  "https://discricionarias.transferegov.sistema.gov.br/voluntarias/ConsultarProposta/ResultadoDaConsultaDePropostaDetalharProposta.do?idProposta=";
const ITEM_PAD_DETAIL_URL =
  "https://discricionarias.transferegov.sistema.gov.br/voluntarias/DetalharBensProposta/ListarBensDetalhar.do?id=";

const APPROVED_YIELD_STATUS = "PT Ajustado e Aprovado";
const VALID_UF = /^[A-Z]{2}$/;

/** Mapeamento lógico → cabeçalho SICONV na view_convenio. */
const CONVENIO_COLUMNS = {
  proposalId: "ID_PROPOSTA",
  proponent: "NM_PROPONENTE",
  modality: "MODALIDADE",
  convenioNumber: "NR_CONVENIO",
  status: "SIT_CONVENIO",
  vigencyStart: "DIA_INIC_VIGENC_CONV",
  vigencyEnd: "DIA_FIM_VIGENC_CONV",
  committedValue: "VL_EMPENHADO_CONV",
  proposalGlobalValue: "VL_GLOBAL_PROP",
  yieldBalance: "VL_RENDIMENTO_APLICACAO",
  accountBalance: "VL_SALDO_CONTA",
  convenioGlobalValue: "VL_GLOBAL_CONV",
  disbursedValue: "VL_DESEMBOLSADO_CONV",
};

/** Índices 0-based da aba SIG_PCS: A = convênio, F = técnico. */
const SIG_PCS_COLUMNS = {
  convenio: 0,
  technician: 5,
};

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

/* --- 2. CSV loading --- */

function csvUrlForGid(gid) {
  return `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${gid}`;
}

function csvUrlForSheet(sheetName) {
  return `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent(sheetName)}`;
}

function parseCsv(url, { header = true } = {}) {
  return new Promise((resolve, reject) => {
    Papa.parse(url, {
      download: true,
      header,
      skipEmptyLines: true,
      complete: (result) => resolve(result.data || []),
      error: reject,
    });
  });
}

async function loadSheets(sheetConfig, onProgress) {
  const data = {};
  let done = 0;
  await Promise.all(sheetConfig.map(async ({ key, sheet }) => {
    let rows = await parseCsv(csvUrlForSheet(sheet));
    if (sheet === "meta_carga") {
      const expected = ["executado_em", "data_carga_siconv", "total_convenios"];
      if (!rows.length || !expected.every((col) => col in rows[0])) rows = [];
    }
    data[key] = rows;
    done += 1;
    if (onProgress) onProgress(sheet, done, sheetConfig.length);
  }));
  return data;
}

function sumByConvenio(rows, valueColumn) {
  const map = Object.create(null);
  for (const row of rows) {
    const nr = String(row.NR_CONVENIO || "").trim();
    if (!nr) continue;
    map[nr] = (map[nr] || 0) + parseNum(row[valueColumn]);
  }
  return map;
}

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

function loadConveniosWithExecutedValue({ filterFormalized = false } = {}) {
  return Promise.all([
    parseCsv(CSV_URL),
    loadValorExecutadoMap(),
  ]).then(([convenios, executedValueByConvenio]) => {
    let rows = convenios || [];
    if (filterFormalized) {
      rows = rows.filter((r) =>
        String(r.NR_CONVENIO || "").trim() !== ""
        && String(r.SIT_CONVENIO || "").trim() !== "Proposta/Plano de Trabalho Aprovado",
      );
    }
    return { convenios: rows, executedValueByConvenio };
  });
}

/* --- 3. Parsing & formatting --- */

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

function parseDateParts(str) {
  if (!str) return null;
  const s = String(str).trim();
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return { d: +m[3], mo: +m[2], y: +m[1], raw: str };
  m = s.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (!m) return null;
  return { d: +m[1], mo: +m[2], y: +m[3], raw: str };
}

function formatDate(value) {
  if (value instanceof Date) {
    return value.toLocaleDateString("pt-BR");
  }
  const p = parseDateParts(value);
  if (!p) return value || "—";
  return `${String(p.d).padStart(2, "0")}/${String(p.mo).padStart(2, "0")}/${p.y}`;
}

function dateSortKey(str) {
  const p = parseDateParts(str);
  if (!p) return 0;
  return p.y * 10000 + p.mo * 100 + p.d;
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

function formatDecimal(value, { decimals = 0 } = {}) {
  return (value || 0).toLocaleString(navigator.language || "pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatPercentBar(value, color) {
  if (value === null || Number.isNaN(value)) {
    return `<span style="color:var(--tinta-suave)">—</span>`;
  }
  const clamped = Math.min(100, Math.max(0, value));
  return `
    <div class="barra-percentual">
      <div class="trilho"><div class="preenchimento" style="width:${clamped.toFixed(0)}%; background:${color}"></div></div>
      <span class="texto mono">${clamped.toFixed(0)}%</span>
    </div>`;
}

function formatDeadlineStamp(row) {
  const { band, daysRemaining } = row;
  if (daysRemaining === null) return `<span class="badge-situacao">sem data de vigência</span>`;
  return `<span class="carimbo ${band.key}"><span class="dias">${daysRemaining}d</span></span>`;
}

/* --- 4. view_convenio domain --- */

function getInstrumentCategory(row) {
  if ((row.MODALIDADE || "").trim().toUpperCase() === "TERMO DE FOMENTO") return "Fomento";
  const ano = (row.ANO_PROP || "").trim();
  return ano ? `Edital ${ano}` : "Sem ano informado";
}

function sortInstrumentCategories(categories) {
  return [...categories].sort((a, b) => {
    if (a === "Fomento") return 1;
    if (b === "Fomento") return -1;
    return a.localeCompare(b, "pt-BR");
  });
}

function daysBetween(dateA, dateB) {
  const MS_PER_DAY = 1000 * 60 * 60 * 24;
  return Math.round((dateA.getTime() - dateB.getTime()) / MS_PER_DAY);
}

function executionUrgencyBand(daysRemaining) {
  if (daysRemaining === null) return { key: "indefinido", label: "sem prazo", color: "var(--tinta-suave)" };
  if (daysRemaining < 30) return { key: "urgente", label: "< 30 dias", color: BRAND_COLORS.laranja };
  if (daysRemaining < 90) return { key: "alerta", label: "30–90 dias", color: BRAND_COLORS.amarelo };
  return { key: "normal", label: "> 90 dias", color: BRAND_COLORS.verde };
}

function accountabilityUrgencyBand(days) {
  if (days === null) return { key: "indefinido", label: "", color: "var(--tinta-suave)" };
  if (days > 180) return { key: "urgente", label: "", color: BRAND_COLORS.laranja };
  if (days >= 91) return { key: "alerta", label: "", color: BRAND_COLORS.amarelo };
  return { key: "normal", label: "", color: BRAND_COLORS.verde };
}

function isInExecution(status) {
  return (status || "").trim() === "Em execução";
}

function isInAccountability(status) {
  const s = status || "";
  return s.includes("Prestação de Contas") && !s.includes("Aprovada");
}

function hasConvenio(row) {
  const nr = (row.convenioNumber || "").trim();
  return nr && nr !== "—";
}

function transformConvenioRow(rawRow, executedValueByConvenio, { technicianByConvenio } = {}) {
  const cols = CONVENIO_COLUMNS;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const nr = (rawRow[cols.convenioNumber] || "").trim();

  const startDate = parseDate(rawRow[cols.vigencyStart]);
  const endDate = parseDate(rawRow[cols.vigencyEnd]);
  const executedValue = nr ? (executedValueByConvenio[nr] || 0) : 0;
  const globalValue = parseNum(rawRow[cols.convenioGlobalValue]);
  const disbursedValue = parseNum(rawRow[cols.disbursedValue]);
  const status = rawRow[cols.status] || "Não informada";
  const inExecution = isInExecution(status);

  const rawDaysRemaining = endDate
    ? (inExecution ? daysBetween(endDate, today) : daysBetween(today, endDate))
    : null;
  const daysRemaining = rawDaysRemaining === null
    ? null
    : (inExecution ? rawDaysRemaining : Math.abs(rawDaysRemaining));
  const band = inExecution
    ? executionUrgencyBand(rawDaysRemaining)
    : accountabilityUrgencyBand(daysRemaining);

  let vigencyPercent = null;
  if (startDate && endDate && endDate > startDate) {
    const totalDays = daysBetween(endDate, startDate);
    const elapsedDays = daysBetween(today, startDate);
    vigencyPercent = Math.min(100, Math.max(0, (elapsedDays / totalDays) * 100));
  }

  let executionPercent = null;
  if (globalValue > 0) {
    executionPercent = Math.min(100, Math.max(0, (executedValue / globalValue) * 100));
  }

  let disbursementPercent = null;
  if (globalValue > 0) {
    disbursementPercent = Math.min(100, Math.max(0, (disbursedValue / globalValue) * 100));
  }

  const row = {
    proposalId: rawRow[cols.proposalId] || "",
    proponent: rawRow[cols.proponent] || "(sem nome cadastrado)",
    modality: rawRow[cols.modality] || "—",
    convenioNumber: nr || "—",
    status,
    vigencyPercent,
    executionPercent,
    disbursementPercent,
    daysRemaining,
    band,
  };

  if (technicianByConvenio) {
    row.vigencyEndDate = endDate;
    row.technician = technicianByConvenio[nr] || null;
  }

  return row;
}

/* --- 5. Aggregations --- */

function buildUsedYieldMap(requests) {
  const map = Object.create(null);
  for (const row of requests) {
    const status = (row.STATUS_SOLICITACAO_REND_APLICACAO || "").trim();
    if (status !== APPROVED_YIELD_STATUS) continue;
    const nr = String(row.NR_CONVENIO || "").trim();
    if (!nr) continue;
    map[nr] = (map[nr] || 0) + parseNum(row.VALOR_APROVADO_SOLICITACAO_REND_APLICACAO);
  }
  return map;
}

function buildTechnicianAssignment(rows, sigColumns = SIG_PCS_COLUMNS) {
  const byTechnician = {};
  const byConvenio = {};
  for (const row of rows.slice(1)) {
    const nr = String(row[sigColumns.convenio] || "").trim();
    const technician = String(row[sigColumns.technician] || "").trim();
    if (!nr || !technician) continue;
    byConvenio[nr] = technician;
    if (!byTechnician[technician]) byTechnician[technician] = [];
    byTechnician[technician].push(nr);
  }
  return { byTechnician, byConvenio };
}

function normalizeKitchenCode(value) {
  return String(value || "").trim().toUpperCase();
}

function isValidState(value) {
  const uf = String(value || "").trim().toUpperCase();
  return VALID_UF.test(uf) ? uf : "";
}

function buildStateByKitchenMap(kitchens) {
  const map = Object.create(null);
  for (const row of kitchens) {
    const code = normalizeKitchenCode(row["Código da Cozinha"]);
    const state = isValidState(row.UF);
    if (!code || !state) continue;
    map[code] = state;
  }
  return map;
}

function getStatesFromKitchenSheet(kitchens) {
  return [...new Set(
    kitchens.map((r) => isValidState(r.UF)).filter(Boolean),
  )].sort((a, b) => a.localeCompare(b, "pt-BR"));
}

function getProposalIdsWithConvenio(convenios) {
  const ids = new Set();
  for (const row of convenios) {
    if (String(row.NR_CONVENIO || "").trim() === "") continue;
    const id = String(row.ID_PROPOSTA || "").trim();
    if (id) ids.add(id);
  }
  return ids;
}

function transformPartnershipInstrumentRow(rawRow, usedYieldByConvenio, executedValueByConvenio, today) {
  const nrConvenio = String(rawRow.NR_CONVENIO || "").trim();
  const startDate = parseDate(rawRow.DIA_INIC_VIGENC_CONV);
  const endDate = parseDate(rawRow.DIA_FIM_VIGENC_CONV);
  const accountabilityDeadline = parseDate(rawRow.DIA_LIMITE_PREST_CONTAS);

  const globalProposalValue = parseNum(rawRow.VL_GLOBAL_PROP);
  const availableYield = parseNum(rawRow.VL_RENDIMENTO_APLICACAO);
  const usedYield = nrConvenio ? (usedYieldByConvenio[nrConvenio] || 0) : 0;
  const totalYield = usedYield + availableYield;
  const accountBalance = parseNum(rawRow.VL_SALDO_CONTA);
  const executedValue = nrConvenio ? (executedValueByConvenio[nrConvenio] || 0) : 0;
  const executedValuePercent = globalProposalValue > 0
    ? (executedValue / globalProposalValue) * 100
    : null;

  let totalVigencyDays = null;
  let elapsedDays = null;
  let daysRemaining = null;
  let elapsedTimePercent = null;

  if (startDate && endDate) {
    totalVigencyDays = daysBetween(endDate, startDate);
    if (totalVigencyDays >= 0) {
      const rawElapsed = daysBetween(today, startDate);
      elapsedDays = Math.min(totalVigencyDays, Math.max(0, rawElapsed));
      daysRemaining = totalVigencyDays - elapsedDays;
      elapsedTimePercent = totalVigencyDays > 0
        ? (elapsedDays / totalVigencyDays) * 100
        : null;
    }
  }

  return {
    proposalId: rawRow.ID_PROPOSTA || "",
    modality: rawRow.MODALIDADE || "—",
    proposalNumber: rawRow.NR_PROPOSTA || "—",
    convenioNumber: nrConvenio || "—",
    proponent: rawRow.NM_PROPONENTE || "(sem nome cadastrado)",
    cnpj: rawRow.IDENTIF_PROPONENTE || "—",
    processNumber: rawRow.NR_PROCESSO || "—",
    state: rawRow.UF_PROPONENTE || "—",
    programCode: rawRow.COD_PROGRAMA || "—",
    globalProposalValue,
    repasseValue: parseNum(rawRow.VL_REPASSE_PROP),
    counterpartValue: parseNum(rawRow.VL_CONTRAPARTIDA_PROP),
    availableYield,
    usedYield,
    totalYield,
    accountBalance,
    disbursedValue: parseNum(rawRow.VL_DESEMBOLSADO_CONV),
    executedValue,
    executedValuePercent,
    vigencyStart: startDate,
    vigencyEnd: endDate,
    accountabilityDeadline,
    totalVigencyDays,
    elapsedDays,
    daysRemaining,
    elapsedTimePercent,
    currentDate: today,
    status: rawRow.SIT_CONVENIO || "—",
    band: executionUrgencyBand(daysRemaining),
  };
}

function transformApplicationPlanRow(rawRow, stateByKitchen) {
  const kitchenCode = normalizeKitchenCode(rawRow.CS_CODIGO);
  const proposalId = String(rawRow.ID_PROPOSTA || "").trim();
  const proposalLink = proposalId
    ? (String(rawRow.LINK_PROPOSTA || "").trim() || `${PROPOSTA_DETAIL_URL}${proposalId}`)
    : "";
  return {
    type: getInstrumentCategory(rawRow),
    state: (kitchenCode && stateByKitchen[kitchenCode]) || "—",
    kitchenCode: kitchenCode || "—",
    proposalId,
    proposalLink,
    proposalNumber: rawRow.NR_PROPOSTA || "—",
    acronym: rawRow.SIGLA || "—",
    municipality: rawRow.MUNICIPIO || "—",
    acquisitionNature: rawRow.NATUREZA_AQUISICAO || "—",
    itemDescription: rawRow.DESCRICAO_ITEM || "—",
    itemZip: rawRow.CEP_ITEM || "—",
    itemAddress: rawRow.ENDERECO_ITEM || "—",
    expenseType: rawRow.TIPO_DESPESA_ITEM || "—",
    expenseNature: rawRow.NATUREZA_DESPESA || "—",
    itemStatus: rawRow.SIT_ITEM || "—",
    expenseNatureCode: rawRow.COD_NATUREZA_DESPESA || "—",
    itemQuantity: parseNum(rawRow.QTD_ITEM),
    unitValue: parseNum(rawRow.VALOR_UNITARIO_ITEM),
    totalValue: parseNum(rawRow.VALOR_TOTAL_ITEM),
    itemPadId: String(rawRow.ID_ITEM_PAD || "").trim() || "—",
    itemPadLink: String(rawRow.ID_ITEM_PAD || "").trim()
      ? `${ITEM_PAD_DETAIL_URL}${String(rawRow.ID_ITEM_PAD).trim()}`
      : "",
  };
}

function loadPartnershipInstruments() {
  return Promise.all([
    parseCsv(CSV_URL),
    parseCsv(CSV_URL_SOLICITACAO_RENDIMENTO),
    loadValorExecutadoMap(),
  ]).then(([convenios, requests, executedValueByConvenio]) => {
    const loadDate = new Date();
    loadDate.setHours(0, 0, 0, 0);
    const usedYieldByConvenio = buildUsedYieldMap(requests);
    const rows = convenios
      .filter((r) => String(r.NR_CONVENIO || "").trim() !== "")
      .map((r) => transformPartnershipInstrumentRow(
        r, usedYieldByConvenio, executedValueByConvenio, loadDate,
      ));
    return { rows, loadDate, executedValueByConvenio };
  });
}

function loadAgreedValueData() {
  return Promise.all([
    parseCsv(CSV_URL_VIEW_PLANO_APLICACAO),
    parseCsv(CSV_URL_COZINHA),
    parseCsv(CSV_URL),
  ]).then(([planRows, kitchens, convenios]) => {
    const proposalIds = getProposalIdsWithConvenio(convenios);
    const stateByKitchen = buildStateByKitchenMap(kitchens);
    const kitchenStates = getStatesFromKitchenSheet(kitchens);
    const rows = planRows
      .filter((r) => proposalIds.has(String(r.ID_PROPOSTA || "").trim()))
      .map((r) => transformApplicationPlanRow(r, stateByKitchen));
    return { rows, kitchenStates, planRows, kitchens, convenios };
  });
}

/* --- 6. Query helpers (operacional) --- */

function tableExists(data, name) {
  return Array.isArray(data[name]) && data[name].length > 0;
}

function tableColumns(data, name) {
  const rows = data[name];
  if (!rows?.length) return [];
  return Object.keys(rows[0]);
}

function hasColumn(data, table, col) {
  return tableColumns(data, table).includes(col);
}

function findBy(data, table, col, val) {
  return data[table]?.find((row) => row[col] === val) || null;
}

function filterBy(data, table, col, val) {
  return (data[table] || []).filter((row) => row[col] === val);
}

function filterIn(data, table, col, values) {
  if (!values.length) return [];
  const allowed = new Set(values);
  return (data[table] || []).filter((row) => allowed.has(row[col]));
}

function uniqueBiddings(rows) {
  const byId = new Map();
  for (const row of rows) {
    if (row.ID_LICITACAO && !byId.has(row.ID_LICITACAO)) {
      byId.set(row.ID_LICITACAO, row);
    }
  }
  return [...byId.values()];
}

function buildConvenioListFromData(data) {
  return data.convenio
    .filter((c) => String(c.NR_CONVENIO ?? "").trim())
    .map((c) => ({
      NR_CONVENIO: c.NR_CONVENIO,
      ID_PROPOSTA: c.ID_PROPOSTA,
      SIT_CONVENIO: c.SIT_CONVENIO,
      VL_REPASSE_CONV: c.VL_REPASSE_CONV,
      NM_PROPONENTE: c.NM_PROPONENTE,
      UF_PROPONENTE: c.UF_PROPONENTE,
      MUNIC_PROPONENTE: c.MUNIC_PROPONENTE,
      OBJETO_PROPOSTA: c.OBJETO_PROPOSTA,
      NOME_PROGRAMA: c.NOME_PROGRAMA ?? "",
    }))
    .sort((a, b) => (+a.NR_CONVENIO) - (+b.NR_CONVENIO));
}

/* --- 7. Status UI --- */

function setStatusBanner(selector, message, kind) {
  const el = document.querySelector(selector);
  el.textContent = message;
  el.className = "status-banner" + (kind ? ` ${kind}` : "");
}

function setStatusDot(selector, message, hasError) {
  const el = document.querySelector(selector);
  el.innerHTML = `<span class="ponto${hasError ? " erro" : ""}"></span><span>${message}</span>`;
}
