"""Configuração do pipeline de atividades das Cozinhas Solidárias (Fundacentro).

Independente de etl/config.py (SICONV/TransfereGov). Credenciais Google
vêm só de variável de ambiente — nunca hardcoded.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SPREADSHEET_ID = "1sS6T-EbMOtlIXRbY5OAgZtzb9nde9MnNAkWmfP4ruYc"
SHEET_ATIVIDADES = "atividades_cozinhas"

CHECKPOINT_FILE = BASE_DIR / ".ultima_data_extraida"

DATE_FMT = "%Y-%m-%d"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_ENV_VAR = "ETL_ATIVIDADES_GOOGLE_CREDENTIALS_FILE"


def google_credentials_path() -> Path:
    """Caminho do JSON da service account (obrigatório via env)."""
    raw = os.environ.get(CREDENTIALS_ENV_VAR)
    if not raw:
        raise SystemExit(
            f"Defina a variável de ambiente {CREDENTIALS_ENV_VAR} "
            "com o caminho do arquivo JSON da service account "
            "(ex.: scraper-whatsappweb-….json)."
        )
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"Arquivo de credenciais não encontrado: {path}")
    return path
