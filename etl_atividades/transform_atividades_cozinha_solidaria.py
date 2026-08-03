"""Normalização de colunas derivadas das atividades da Cozinha Solidária.

Extrai ``codigo_cozinha`` de ``Cozinha`` e ``acao``/``refeicao`` de
``Contribuicao`` (ou ``frase_acao`` se existir), sem alterar as colunas
originais do CSV.
"""

from __future__ import annotations

import re
import sys

# Mais longo primeiro para "Café da Manhã" não cair em "Café".
REFEICOES = [
    "Café da Manhã",
    "Café",
    "Almoço",
    "Lanche",
    "Jantar",
    "Ceia",
]

_REFEICAO_PATTERN = "|".join(re.escape(r) for r in REFEICOES)
_ACAO_REFEICAO_RE = re.compile(
    rf"^(?P<acao>.*?)\s+(?P<refeicao>{_REFEICAO_PATTERN})(?:\s|$)",
)

_CODIGO_COZINHA_RE = re.compile(r"\((CS\d+)\)")

DERIVED_COLUMNS = ("codigo_cozinha", "acao", "refeicao")

_COZINHA_ALIASES = ("cozinha",)
# Fonte da frase "<Ação> <Refeição> <resto>" no export do painel.
_FRASE_ALIASES = ("contribuicao", "frase_acao")


def extract_codigo_cozinha(cozinha: str) -> str:
    """Extrai o código CS###### da coluna ``Cozinha``, se presente."""
    if not cozinha or not str(cozinha).strip():
        return ""
    match = _CODIGO_COZINHA_RE.search(str(cozinha))
    return match.group(1) if match else ""


def extract_acao_refeicao(frase_acao: str) -> tuple[str, str]:
    """Extrai (acao, refeicao) de ``frase_acao`` contra vocabulário fixo.

    Formato esperado: ``<Ação> <Refeição> <resto>``.
    Vazio → ambos vazios, sem warning.
    Preenchido fora do vocabulário → ambos vazios + warning em stderr.
    """
    text = "" if frase_acao is None else str(frase_acao).strip()
    if not text:
        return "", ""

    match = _ACAO_REFEICAO_RE.match(text)
    if not match:
        print(
            f"aviso: frase_acao fora do vocabulário conhecido: {text!r}",
            file=sys.stderr,
        )
        return "", ""

    return match.group("acao").strip(), match.group("refeicao")


def _header_index_ci(headers: list[str]) -> dict[str, int]:
    """Mapa nome_normalizado → índice (primeira ocorrência)."""
    index: dict[str, int] = {}
    for i, name in enumerate(headers):
        key = name.strip().lower()
        if key and key not in index:
            index[key] = i
    return index


def _cell(row: list[str], index_ci: dict[str, int], name: str) -> str:
    idx = index_ci.get(name.lower())
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx]).strip()


def resolve_frase_acao(row: list[str], index_ci: dict[str, int]) -> str:
    """Texto usado em extract_acao_refeicao: prioriza ``Contribuicao``."""
    for alias in _FRASE_ALIASES:
        if alias in index_ci:
            return _cell(row, index_ci, alias)
    return ""


def enrich_rows(
    headers: list[str],
    data_rows: list[list[str]],
) -> tuple[list[str], list[list[str]]]:
    """Acrescenta codigo_cozinha, acao e refeicao ao cabeçalho e às linhas."""
    if not headers:
        raise RuntimeError(
            "enrich_rows: cabeçalho vazio — abortando para não perder colunas."
        )

    index_ci = _header_index_ci(headers)
    idx_cozinha = next(
        (index_ci[a] for a in _COZINHA_ALIASES if a in index_ci),
        None,
    )
    if idx_cozinha is None:
        raise RuntimeError(
            "Coluna 'Cozinha' ausente no CSV. Cabeçalho recebido: "
            f"{headers!r}"
        )

    if not any(a in index_ci for a in _FRASE_ALIASES):
        raise RuntimeError(
            "Coluna 'Contribuicao' (ou frase_acao) ausente no CSV. "
            f"Cabeçalho recebido: {headers!r}"
        )

    new_headers = list(headers) + list(DERIVED_COLUMNS)
    enriched: list[list[str]] = []
    for row in data_rows:
        cozinha = row[idx_cozinha] if idx_cozinha < len(row) else ""
        frase = resolve_frase_acao(row, index_ci)
        codigo = extract_codigo_cozinha(cozinha)
        acao, refeicao = extract_acao_refeicao(frase)
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        enriched.append(padded[: len(headers)] + [codigo, acao, refeicao])
    return new_headers, enriched
