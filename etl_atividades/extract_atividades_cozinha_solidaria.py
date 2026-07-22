"""
Extractor for the Cozinha Solidária admin panel (fundacentro.gov.br).

Authenticates against the panel's login form, downloads the
"RelatorioGeral" activity report via its CSV export endpoint, saves the
CSV locally, and appends the rows to the Google Sheet aba
"atividades_cozinhas".

This is a separate operational data source from the SICONV pipeline
(etl/). It must not import etl.config / etl.load.

Credentials:
    COZINHA_SOLIDARIA_LOGIN
    COZINHA_SOLIDARIA_SENHA
    ETL_ATIVIDADES_GOOGLE_CREDENTIALS_FILE  (path to service-account JSON)

Checkpoint (etl_atividades/.ultima_data_extraida):
    Normal cron run (no --data-inicio): requires a valid checkpoint;
    data_inicio = checkpoint + 1 day, data_fim = yesterday by default
    (or --data-fim if passed explicitly). The default stops short of
    "today" so an in-progress day is never captured; the next run picks
    it up complete.
    Bootstrap / correction: pass --data-inicio (and optional --data-fim).
    Checkpoint is written only after a successful Sheets append.

Usage (cron, after bootstrap):
    export COZINHA_SOLIDARIA_LOGIN="..."
    export COZINHA_SOLIDARIA_SENHA="..."
    export ETL_ATIVIDADES_GOOGLE_CREDENTIALS_FILE="/path/to/sa.json"
    python -m etl_atividades.extract_atividades_cozinha_solidaria \\
        --output-dir ./data

Usage (bootstrap / manual window):
    python -m etl_atividades.extract_atividades_cozinha_solidaria \\
        --output-dir ./data --data-inicio 2026-04-01 --data-fim 2026-07-14
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import requests
from google.oauth2.service_account import Credentials
from gspread import Worksheet, authorize
from gspread.exceptions import WorksheetNotFound

from etl_atividades.config import (
    CHECKPOINT_FILE,
    CREDENTIALS_ENV_VAR,
    DATE_FMT,
    SHEET_ATIVIDADES,
    SHEETS_SCOPES,
    SPREADSHEET_ID,
    google_credentials_path,
)

BASE_URL = "https://cozinhasolidaria.fundacentro.gov.br/tjd3s_cozinhas_solidarias"
LOGIN_URL = f"{BASE_URL}/cadastro_pessoas.php"
EXPORT_URL = f"{BASE_URL}/cozinha_solidaria/index_adm.php"

# tipo_filtro=5 => "todos" (all record types), per domain convention
TIPO_FILTRO_TODOS = "5"

FILENAME_PREFIX = "atividades_cozinha_solidaria"


@dataclass
class PanelCredentials:
    login: str
    senha: str

    @classmethod
    def from_env(cls) -> "PanelCredentials":
        login = os.environ.get("COZINHA_SOLIDARIA_LOGIN")
        senha = os.environ.get("COZINHA_SOLIDARIA_SENHA")
        if not login or not senha:
            raise SystemExit(
                "Defina as variáveis de ambiente COZINHA_SOLIDARIA_LOGIN e "
                "COZINHA_SOLIDARIA_SENHA antes de rodar o script."
            )
        return cls(login=login, senha=senha)


def build_session(creds: PanelCredentials) -> requests.Session:
    """Authenticate and return a session carrying the resulting cookie."""
    session = requests.Session()
    response = session.post(
        LOGIN_URL,
        data={"login": creds.login, "senha": creds.senha},
        allow_redirects=False,
        timeout=30,
    )
    # A successful login redirects (302). A failed one typically re-renders
    # the login page with 200. Session cookie presence is the real signal.
    if response.status_code not in (302, 303) or not session.cookies:
        raise RuntimeError(
            f"Falha no login (status {response.status_code}). "
            "Verifique as credenciais ou se o formulário mudou."
        )
    return session


def download_csv(
    session: requests.Session,
    data_inicio: str,
    data_fim: str,
    output_path: str,
    tipo_filtro: str = TIPO_FILTRO_TODOS,
) -> bytes:
    """Download the export, write it to disk, and return the raw bytes."""
    params = {
        "exportar_csv": "1",
        "tipo_filtro": tipo_filtro,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
    }
    response = session.get(EXPORT_URL, params=params, timeout=60)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "csv" not in content_type and "text/plain" not in content_type:
        raise RuntimeError(
            f"Resposta não parece ser CSV (Content-Type: {content_type!r}). "
            "Sessão pode ter expirado ou a URL de exportação mudou."
        )

    with open(output_path, "wb") as f:
        f.write(response.content)

    return response.content


def parse_iso_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, DATE_FMT).date()
    except ValueError:
        return None


def read_checkpoint() -> date | None:
    """Return the checkpoint date, or None if missing/invalid."""
    if not CHECKPOINT_FILE.is_file():
        return None
    try:
        raw = CHECKPOINT_FILE.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    if not raw:
        return None
    return parse_iso_date(raw[0])


def write_checkpoint(data_fim: date) -> None:
    CHECKPOINT_FILE.write_text(data_fim.strftime(DATE_FMT) + "\n", encoding="utf-8")


def parse_csv_bytes(content: bytes) -> tuple[list[str], list[list[str]]]:
    """Preserve Portuguese API headers (data_upload, cozinha, tipo_resultado, …)."""
    text = content.decode("utf-8-sig")
    if not text.strip():
        return [], []

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1:]


def open_atividades_worksheet() -> Worksheet:
    """Open (or create) the atividades_cozinhas worksheet."""
    creds = Credentials.from_service_account_file(
        str(google_credentials_path()),
        scopes=SHEETS_SCOPES,
    )
    client = authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        return spreadsheet.worksheet(SHEET_ATIVIDADES)
    except WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=SHEET_ATIVIDADES,
            rows=1000,
            cols=26,
        )


def append_rows_to_sheet(
    worksheet: Worksheet,
    headers: list[str],
    data_rows: list[list[str]],
) -> int:
    """Append rows with RAW input; fail loudly if header diverges."""
    existing = worksheet.get_all_values()
    if not existing:
        if headers:
            worksheet.append_row(headers, value_input_option="RAW")
    elif existing[0] != headers:
        raise RuntimeError(
            f"Cabeçalho da aba '{SHEET_ATIVIDADES}' diverge do CSV recebido. "
            "Alinhar manualmente antes de continuar.\n"
            f"  aba: {existing[0]!r}\n"
            f"  csv: {headers!r}"
        )

    if not data_rows:
        return 0

    worksheet.append_rows(data_rows, value_input_option="RAW")
    return len(data_rows)


def resolve_date_range(args: argparse.Namespace) -> tuple[date, date] | None:
    """Resolve (data_inicio, data_fim) from CLI and/or checkpoint.

    Default data_fim (when --data-fim is omitted) is yesterday, so the
    current day is never partially captured.

    Returns None when there is nothing new to fetch (already caught up).
    Exits the process if the normal flow has no valid checkpoint.
    """
    data_fim = (
        parse_iso_date(args.data_fim)
        if args.data_fim
        else date.today() - timedelta(days=1)
    )
    if args.data_fim and data_fim is None:
        raise SystemExit(f"--data-fim inválido (use {DATE_FMT}): {args.data_fim!r}")

    if args.data_inicio:
        data_inicio = parse_iso_date(args.data_inicio)
        if data_inicio is None:
            raise SystemExit(
                f"--data-inicio inválido (use {DATE_FMT}): {args.data_inicio!r}"
            )
    else:
        checkpoint = read_checkpoint()
        if checkpoint is None:
            print(
                "Não há checkpoint válido em "
                f"{CHECKPOINT_FILE}.\n"
                "Para inicializar (bootstrap) ou corrigir, rode com "
                "--data-inicio YYYY-MM-DD (e opcionalmente --data-fim). "
                "Exemplo:\n"
                "  python -m etl_atividades.extract_atividades_cozinha_solidaria "
                "--data-inicio 2026-04-01\n"
                "Ou corrija manualmente o arquivo de checkpoint "
                "(uma linha YYYY-MM-DD).",
                file=sys.stderr,
            )
            raise SystemExit(1)
        data_inicio = checkpoint + timedelta(days=1)

    assert data_fim is not None
    if data_inicio > data_fim:
        return None
    return data_inicio, data_fim


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        default="./data",
        help="Diretório onde o CSV baixado será salvo",
    )
    parser.add_argument(
        "--data-inicio",
        help=(
            f"YYYY-MM-DD — bootstrap/correção; ignora o checkpoint como "
            f"origem de data_inicio. Sem este flag, exige checkpoint válido."
        ),
    )
    parser.add_argument(
        "--data-fim",
        help=(
            "YYYY-MM-DD (opcional; default: ontem). "
            "Sem este flag, a rotina nunca inclui o dia corrente "
            "(ainda em andamento). Com o flag, usa a data informada "
            "(bootstrap/correção)."
        ),
    )
    parser.add_argument(
        "--tipo-filtro",
        default=TIPO_FILTRO_TODOS,
        help="Código do filtro (default: 5 = todos)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    date_range = resolve_date_range(args)
    if date_range is None:
        print("Nada novo para baixar — já está em dia.", file=sys.stderr)
        return

    data_inicio_d, data_fim_d = date_range
    data_inicio = data_inicio_d.strftime(DATE_FMT)
    data_fim = data_fim_d.strftime(DATE_FMT)

    # Fail fast on missing Google credentials before hitting the panel.
    _ = google_credentials_path()

    os.makedirs(args.output_dir, exist_ok=True)
    panel_creds = PanelCredentials.from_env()

    print("Autenticando no painel Fundacentro...", file=sys.stderr)
    session = build_session(panel_creds)

    print(f"Baixando exportação de {data_inicio} a {data_fim}...", file=sys.stderr)
    output_path = os.path.join(
        args.output_dir,
        f"{FILENAME_PREFIX}_{data_inicio}_{data_fim}.csv",
    )
    content = download_csv(
        session,
        data_inicio=data_inicio,
        data_fim=data_fim,
        output_path=output_path,
        tipo_filtro=args.tipo_filtro,
    )
    print(f"OK: {len(content)} bytes salvos em {output_path}", file=sys.stderr)

    headers, data_rows = parse_csv_bytes(content)
    print(
        f"Gravando {len(data_rows)} linhas em '{SHEET_ATIVIDADES}' "
        f"(credenciais via {CREDENTIALS_ENV_VAR})...",
        file=sys.stderr,
    )
    worksheet = open_atividades_worksheet()
    n_appended = append_rows_to_sheet(worksheet, headers, data_rows)
    print(f"OK: {n_appended} linhas anexadas na planilha.", file=sys.stderr)

    # Checkpoint only after a confirmed successful append.
    write_checkpoint(data_fim_d)
    print(
        f"Checkpoint atualizado: {CHECKPOINT_FILE} → {data_fim}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
