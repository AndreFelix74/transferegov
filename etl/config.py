import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "raw"
STAGING_DIR = BASE_DIR / "staging"
DB_DIR = BASE_DIR / "db"
LOG_DIR = BASE_DIR / "logs"
CONFIG_FILE = BASE_DIR / "programas_alvo.txt"
DB_FILE = DB_DIR / "siconv.db"

GOOGLE_SPREADSHEET_ID = "1sS6T-EbMOtlIXRbY5OAgZtzb9nde9MnNAkWmfP4ruYc"
GOOGLE_CREDENTIALS_FILE = BASE_DIR / "scraper-whatsappweb-1e84668a304b.json"
META_SHEET_NAME = "meta_carga"

REPOSITORY_URL = "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/"

CSV_ENCODING = "utf-8-sig"
CHUNK_SIZE = 1_000_000

DATE_COLUMN_PREFIXES = ("DATA_", "DT_")
NON_DATE_DAY_FIELDS = ("DIA", "MES", "ANO")
DECIMAL_COLUMN_PREFIXES = ("VL_", "VALOR_", "QTD_", "PRECO_", "QUANTIDADE")
DATE_RE = r"^(\d{2})/(\d{2})/(\d{4})$"


# Instrumentos que passam no filtro de Código de Programa (COD_PROGRAMA), mas
# pertencem a outra área da Secretaria — excluídos manualmente do recorte da
# Cozinha Solidária.
EXCLUDED_AGREEMENT_NUMBERS = {"970193", "980185", "998038"}


def is_date_column(column: str) -> bool:
    if column in NON_DATE_DAY_FIELDS:
        return False
    return column.startswith(DATE_COLUMN_PREFIXES) or column.startswith("DIA_")


def is_decimal_column(column: str) -> bool:
    return column.startswith(DECIMAL_COLUMN_PREFIXES)


# Ordem define a cadeia de filtros. extract_column/extract_set populam IDs para as próximas tabelas.
TABLES = [
    {
        "file": "siconv_programa.csv",
        "filter_column": "COD_PROGRAMA",
        "filter_set": "program_codes",
        "extract_column": "ID_PROGRAMA",
        "extract_set": "program_ids",
    },
    {
        "file": "siconv_programa_proposta.csv",
        "filter_column": "ID_PROGRAMA",
        "filter_set": "program_ids",
        "extract_column": "ID_PROPOSTA",
        "extract_set": "proposal_ids",
    },
    {
        "file": "siconv_convenio.csv",
        "filter_column": "ID_PROPOSTA",
        "filter_set": "proposal_ids",
        "extract_column": "NR_CONVENIO",
        "extract_set": "agreement_numbers",
    },
    {
        "file": "siconv_licitacao.csv",
        "filter_column": "NR_CONVENIO",
        "filter_set": "agreement_numbers",
        "extract_column": "ID_LICITACAO",
        "extract_set": "bidding_ids",
    },
    {"file": "siconv_proposta.csv", "filter_column": "ID_PROPOSTA", "filter_set": "proposal_ids"},
    {"file": "siconv_desembolso.csv", "filter_column": "NR_CONVENIO", "filter_set": "agreement_numbers"},
    {"file": "siconv_itens_licitacao.csv", "filter_column": "ID_LICITACAO", "filter_set": "bidding_ids"},
    {"file": "siconv_contrato.csv", "filter_column": "ID_LICITACAO", "filter_set": "bidding_ids"},
    {
        "file": "siconv_dl.csv",
        "filter_column": "ID_PROPOSTA",
        "filter_set": "proposal_ids",
        "extract_column": "ID_DL",
        "extract_set": "dl_ids",
    },
    {
        "file": "siconv_itens_dl.csv",
        "filter_column": "ID_DL",
        "filter_set": "dl_ids",
    },
    {"file": "siconv_pagamento.csv", "filter_column": "NR_CONVENIO", "filter_set": "agreement_numbers", "extract_column": "NR_MOV_FIN", "extract_set": "movement_numbers"},
    {"file": "siconv_pagamento_tributo.csv", "filter_column": "NR_CONVENIO", "filter_set": "agreement_numbers"},
    {"file": "siconv_obtv_convenente.csv", "filter_column": "NR_MOV_FIN", "filter_set": "movement_numbers"},
    {"file": "siconv_plano_aplicacao_detalhado.csv", "filter_column": "ID_PROPOSTA", "filter_set": "proposal_ids"},
    {"file": "siconv_historico_situacao.csv", "filter_column": "ID_PROPOSTA", "filter_set": "proposal_ids"},
    {"file": "siconv_cronograma_desembolso.csv", "filter_column": "ID_PROPOSTA", "filter_set": "proposal_ids"},
    {
        "file": "siconv_meta_crono_fisico.csv",
        "filter_column": "ID_PROPOSTA",
        "filter_set": "proposal_ids",
        "extract_column": "ID_META",
        "extract_set": "goal_ids",
    },
    {"file": "siconv_etapa_crono_fisico.csv", "filter_column": "ID_META", "filter_set": "goal_ids"},
    {"file": "siconv_emenda.csv", "filter_column": "ID_PROPOSTA", "filter_set": "proposal_ids"},
    {"file": "siconv_termo_aditivo.csv", "filter_column": "NR_CONVENIO", "filter_set": "agreement_numbers"},
    {"file": "siconv_solicitacao_rendimento_aplicacao.csv", "filter_column": "NR_CONVENIO", "filter_set": "agreement_numbers"},
]

VIEWS_DIR = Path(__file__).parent / "views"

ENRICHMENT_CSV_FILES = ["proposta_enriquecida.csv"]


def required_csv_files() -> list[str]:
    return [table["file"] for table in TABLES]


def view_output_files() -> list[str]:
    return sorted(
        f"{json.load(schema_file.open(encoding='utf-8'))['output_table']}.csv"
        for schema_file in VIEWS_DIR.glob("*.json")
    )


def staging_csv_files() -> list[str]:
    return required_csv_files() + ENRICHMENT_CSV_FILES + view_output_files()


def short_table_name_from_file(csv_filename: str) -> str:
    return Path(csv_filename).stem.removeprefix("siconv_")


def sheet_name_from_csv(csv_filename: str) -> str:
    return Path(csv_filename).stem.removeprefix("siconv_")


def table_name_from_csv(csv_filename: str) -> str:
    return sheet_name_from_csv(csv_filename)


def archive_name_for(table: dict) -> str:
    return table.get("remote_file", f"{Path(table['file']).stem}.zip")


def archive_url_for(table: dict) -> str:
    return REPOSITORY_URL + archive_name_for(table)
