"""
Extractor for the Cozinha Solidária admin panel (fundacentro.gov.br).

Authenticates against the panel's login form, downloads the
"RelatorioGeral" activity report via its CSV export endpoint, saves the
raw download and an enriched CSV (codigo_cozinha / acao / refeicao), and
appends the enriched rows to the Google Sheet aba "atividades_cozinhas".

This is a separate operational data source from the SICONV pipeline
(etl/). It must not import etl.config / etl.load.

Credentials:
    COZINHA_SOLIDARIA_SENHA  (o painel só pede senha; não há login)
    Google Sheets: mesmo JSON da service account do ETL SICONV
    (scraper-whatsappweb-….json na raiz do repo).

Checkpoint (etl_atividades/.ultima_data_extraida):
    Normal cron run (no --data-inicio): requires a valid checkpoint;
    data_inicio = checkpoint + 1 day, data_fim = yesterday by default
    (or --data-fim if passed explicitly). The default stops short of
    "today" so an in-progress day is never captured; the next run picks
    it up complete.
    Bootstrap / correction: pass --data-inicio (and optional --data-fim).
    Checkpoint is written only after a successful Sheets append.

Usage (cron, after bootstrap):
    export COZINHA_SOLIDARIA_SENHA="..."
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
import urllib3
from google.oauth2 import service_account
from googleapiclient.discovery import build
from urllib3.exceptions import InsecureRequestWarning

from etl_atividades.config import (
    CHECKPOINT_FILE,
    DATE_FMT,
    GOOGLE_CREDENTIALS_FILE,
    SHEET_ATIVIDADES,
    SHEETS_SCOPES,
    SPREADSHEET_ID,
    google_credentials_path,
)
from etl_atividades.transform_atividades_cozinha_solidaria import enrich_rows

# Cadeia de certificados incompleta no host Fundacentro — verify desligado
# só nesta sessão do painel (não afeta o client Google Sheets).
urllib3.disable_warnings(InsecureRequestWarning)
BASE_URL = "https://cozinhasolidaria.fundacentro.gov.br/tjd3s_cozinhas_solidarias"
LOGIN_URL = f"{BASE_URL}/cadastro_pessoas.php"
EXPORT_URL = f"{BASE_URL}/cozinha_solidaria/index_adm.php"

# tipo_filtro=5 => "todos" (all record types), per domain convention
TIPO_FILTRO_TODOS = "5"

FILENAME_PREFIX = "atividades_cozinha_solidaria"


@dataclass
class PanelCredentials:
    senha: str

    @classmethod
    def from_env(cls) -> "PanelCredentials":
        senha = os.environ.get("COZINHA_SOLIDARIA_SENHA")
        if not senha:
            raise SystemExit(
                "Defina a variável de ambiente COZINHA_SOLIDARIA_SENHA "
                "antes de rodar o script."
            )
        return cls(senha=senha)


def build_session(creds: PanelCredentials) -> requests.Session:
    """Authenticate and return a session carrying the resulting cookie."""
    session = requests.Session()
    # Host apresenta cadeia SSL incompleta (issuer local ausente).
    session.verify = False
    # Estabelece PHPSESSID como o browser faria ao abrir a página.
    session.get(LOGIN_URL, timeout=30)
    # O botão submit tem name="login" (não é campo de usuário); o PHP
    # só processa o POST quando esse campo vem junto com "senha".
    response = session.post(
        LOGIN_URL,
        data={"senha": creds.senha, "login": "Entrar"},
        allow_redirects=False,
        timeout=30,
    )
    # A successful login redirects (302). A failed one typically re-renders
    # the login page with 200. Session cookie presence is the real signal.
    if response.status_code not in (302, 303) or not session.cookies:
        raise RuntimeError(
            f"Falha no login (status {response.status_code}). "
            "Verifique a senha ou se o formulário mudou."
        )
    return session


def download_csv(
    session: requests.Session,
    data_inicio: str,
    data_fim: str,
    tipo_filtro: str = TIPO_FILTRO_TODOS,
) -> bytes:
    """Download the export and return the raw bytes (does not write to disk)."""
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

    return response.content


def write_csv(path: str, headers: list[str], data_rows: list[list[str]]) -> None:
    """Persist headers + rows as UTF-8 CSV (comma-separated)."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(headers)
        writer.writerows(data_rows)


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
    """Parse export CSV (delimitador real do painel: '|')."""
    text = content.decode("utf-8-sig")
    if not text.strip():
        raise RuntimeError("CSV da exportação veio vazio.")

    # Ignora linhas em branco no início — senão rows[0] vira [] e o enrich
    # descarta todas as colunas originais, ficando só as derivadas vazias.
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        raise RuntimeError("CSV da exportação veio sem linhas úteis.")

    first = lines[0]
    # Painel Fundacentro exporta com '|'; também aceita ';', tab e ','.
    counts = {
        "|": first.count("|"),
        ";": first.count(";"),
        "\t": first.count("\t"),
        ",": first.count(","),
    }
    delimiter = max(counts, key=counts.get)
    if counts[delimiter] == 0:
        delimiter = ","

    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise RuntimeError("CSV da exportação não tem linhas após limpeza.")

    headers = [h.strip() for h in rows[0]]
    if not headers or not any(headers):
        raise RuntimeError(f"CSV sem cabeçalho válido (delimitador={delimiter!r}).")

    return headers, rows[1:]


def _sheet_range(sheet_name: str, cell: str) -> str:
    return f"'{sheet_name}'!{cell}"


def create_sheets_service():
    """Google Sheets API client (mesmo padrão de etl/load.py; sem gspread)."""
    credentials = service_account.Credentials.from_service_account_file(
        str(google_credentials_path()),
        scopes=SHEETS_SCOPES,
    )
    return build("sheets", "v4", credentials=credentials)


def _list_sheet_titles(service) -> set[str]:
    spreadsheet = (
        service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    )
    return {
        sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])
    }


def _ensure_sheet(service, sheet_name: str) -> None:
    if sheet_name in _list_sheet_titles(service):
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
    ).execute()


def append_rows_to_sheet(
    service,
    headers: list[str],
    data_rows: list[list[str]],
) -> int:
    """Append rows with RAW input; fail loudly if header diverges."""
    _ensure_sheet(service, SHEET_ATIVIDADES)

    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=_sheet_range(SHEET_ATIVIDADES, "1:1"),
        )
        .execute()
    )
    existing_header = (result.get("values") or [None])[0]

    if not existing_header:
        if headers:
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=_sheet_range(SHEET_ATIVIDADES, "A1"),
                valueInputOption="RAW",
                body={"values": [headers]},
            ).execute()
    elif existing_header != headers:
        raise RuntimeError(
            f"Cabeçalho da aba '{SHEET_ATIVIDADES}' diverge do CSV recebido. "
            "Alinhar manualmente antes de continuar.\n"
            f"  aba: {existing_header!r}\n"
            f"  csv: {headers!r}"
        )

    if not data_rows:
        return 0

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=_sheet_range(SHEET_ATIVIDADES, "A1"),
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": data_rows},
    ).execute()
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
    stem = f"{FILENAME_PREFIX}_{data_inicio}_{data_fim}"
    raw_path = os.path.join(args.output_dir, f"{stem}_raw.csv")
    output_path = os.path.join(args.output_dir, f"{stem}.csv")
    content = download_csv(
        session,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo_filtro=args.tipo_filtro,
    )
    with open(raw_path, "wb") as f:
        f.write(content)
    print(f"OK: {len(content)} bytes brutos salvos em {raw_path}", file=sys.stderr)

    headers, data_rows = parse_csv_bytes(content)
    headers, data_rows = enrich_rows(headers, data_rows)

    write_csv(output_path, headers, data_rows)
    print(f"OK: CSV enriquecido salvo em {output_path}", file=sys.stderr)

    print(
        f"Gravando {len(data_rows)} linhas em '{SHEET_ATIVIDADES}' "
        f"(credenciais: {GOOGLE_CREDENTIALS_FILE.name})...",
        file=sys.stderr,
    )
    service = create_sheets_service()
    n_appended = append_rows_to_sheet(service, headers, data_rows)
    print(f"OK: {n_appended} linhas anexadas na planilha.", file=sys.stderr)

    # Checkpoint only after a confirmed successful append.
    write_checkpoint(data_fim_d)
    print(
        f"Checkpoint atualizado: {CHECKPOINT_FILE} → {data_fim}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
