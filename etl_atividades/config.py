"""Configuração do pipeline de atividades das Cozinhas Solidárias (Fundacentro).

Independente de etl/config.py (SICONV/TransfereGov). Usa o mesmo arquivo
JSON de service account na raiz do repo que o load do SICONV.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

SPREADSHEET_ID = "1sS6T-EbMOtlIXRbY5OAgZtzb9nde9MnNAkWmfP4ruYc"
SHEET_ATIVIDADES = "atividades_cozinhas"

CHECKPOINT_FILE = BASE_DIR / ".ultima_data_extraida"

DATE_FMT = "%Y-%m-%d"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

# Mesmo arquivo que etl/config.GOOGLE_CREDENTIALS_FILE (raiz do repo).
GOOGLE_CREDENTIALS_FILE = REPO_ROOT / "scraper-whatsappweb-1e84668a304b.json"


def google_credentials_path() -> Path:
    """Caminho do JSON da service account (mesmo do ETL SICONV)."""
    path = GOOGLE_CREDENTIALS_FILE.resolve()
    if not path.is_file():
        raise SystemExit(f"Arquivo de credenciais não encontrado: {path}")
    return path
