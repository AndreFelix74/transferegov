import json
import logging
import time
from datetime import datetime
from email.utils import parsedate_to_datetime

import pandas as pd
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

from etl.config import (
    CSV_ENCODING,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_SPREADSHEET_ID,
    META_SHEET_NAME,
    STAGING_DIR,
    TABLES,
    archive_url_for,
    sheet_name_from_csv,
    staging_csv_files,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BATCH_ROWS = 5000


def _create_sheets_service():
    with open(GOOGLE_CREDENTIALS_FILE, encoding="utf-8") as credentials_file:
        keys = json.load(credentials_file)

    credentials = service_account.Credentials.from_service_account_info(keys, scopes=SCOPES)
    return build("sheets", "v4", credentials=credentials)


def _sheet_range(sheet_name: str, cell: str) -> str:
    return f"'{sheet_name}'!{cell}"


def _list_sheets(service) -> dict[str, int]:
    spreadsheet = service.spreadsheets().get(spreadsheetId=GOOGLE_SPREADSHEET_ID).execute()
    return {
        sheet["properties"]["title"]: sheet["properties"]["sheetId"]
        for sheet in spreadsheet["sheets"]
    }


def _resize_sheet(service, sheet_id: int, row_count: int, col_count: int):
    service.spreadsheets().batchUpdate(
        spreadsheetId=GOOGLE_SPREADSHEET_ID,
        body={
            "requests": [{
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "rowCount": row_count,
                            "columnCount": col_count,
                        },
                    },
                    "fields": "gridProperties.rowCount,gridProperties.columnCount",
                },
            }],
        },
    ).execute()


def _ensure_sheet(service, sheets: dict[str, int], sheet_name: str) -> dict[str, int]:
    if sheet_name in sheets:
        return sheets

    response = service.spreadsheets().batchUpdate(
        spreadsheetId=GOOGLE_SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
    ).execute()
    sheet_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]
    sheets[sheet_name] = sheet_id
    return sheets


def _clear_sheet(service, sheet_name: str):
    service.spreadsheets().values().clear(
        spreadsheetId=GOOGLE_SPREADSHEET_ID,
        range=_sheet_range(sheet_name, "A:ZZ"),
    ).execute()


def _upload_values(service, sheet_name: str, cell: str, values: list[list]):
    # RAW: evita que o Sheets interprete IDs longos (ex.: NR_PROCESSO) como
    # número e os corrompa em notação científica / perda de precisão.
    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SPREADSHEET_ID,
        range=_sheet_range(sheet_name, cell),
        valueInputOption="RAW",
        body={"values": values},
    ).execute()


def _sheet_rows(dataframe: pd.DataFrame) -> list[list]:
    return dataframe.fillna("").astype(str).values.tolist()


def _upload_dataframe(service, sheet_name: str, dataframe: pd.DataFrame):
    _clear_sheet(service, sheet_name)
    rows = _sheet_rows(dataframe)
    _upload_values(service, sheet_name, "A1", [dataframe.columns.tolist()])

    for start in range(0, len(rows), BATCH_ROWS):
        batch = rows[start:start + BATCH_ROWS]
        row_number = start + 2
        _upload_values(service, sheet_name, f"A{row_number}", batch)


def _remote_carga_date() -> str:
    latest = 0.0
    for table in TABLES:
        try:
            response = requests.head(
                archive_url_for(table), timeout=30, allow_redirects=True,
            )
            response.raise_for_status()
            mtime = parsedate_to_datetime(response.headers["Last-Modified"]).timestamp()
            latest = max(latest, mtime)
        except requests.RequestException:
            continue
    if not latest:
        return "—"
    return datetime.fromtimestamp(latest).strftime("%d/%m/%Y")


def _upload_meta_carga(service, sheets: dict[str, int], log: logging.Logger):
    convenio_path = STAGING_DIR / "siconv_convenio.csv"
    total_convenios = 0
    if convenio_path.exists():
        convenio_df = pd.read_csv(convenio_path, sep=";", encoding=CSV_ENCODING, dtype=str)
        total_convenios = len(convenio_df)

    meta_df = pd.DataFrame([{
        "executado_em": datetime.now().isoformat(timespec="seconds"),
        "data_carga_siconv": _remote_carga_date(),
        "total_convenios": str(total_convenios),
    }])
    log.info(f"  Aba '{META_SHEET_NAME}': {total_convenios} convênios ...")
    sheets = _ensure_sheet(service, sheets, META_SHEET_NAME)
    _resize_sheet(service, sheets[META_SHEET_NAME], 2, len(meta_df.columns))
    _upload_dataframe(service, META_SHEET_NAME, meta_df)
    return sheets


def load(log: logging.Logger):
    """Carrega os CSVs de ./staging em abas da planilha Google Sheets."""
    log.info("=== LOAD ===")
    service = _create_sheets_service()
    sheets = _list_sheets(service)

    for filename in staging_csv_files():
        csv_path = STAGING_DIR / filename
        if not csv_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado em staging: {csv_path}")

        table_df = pd.read_csv(csv_path, sep=";", encoding=CSV_ENCODING, dtype=str)
        sheet_name = sheet_name_from_csv(filename)
        log.info(f"  Aba '{sheet_name}': {len(table_df)} linhas ...")

        sheets = _ensure_sheet(service, sheets, sheet_name)
        _resize_sheet(
            service,
            sheets[sheet_name],
            len(table_df) + 1,
            len(table_df.columns),
        )
        _upload_dataframe(service, sheet_name, table_df)
        time.sleep(3)

    sheets = _upload_meta_carga(service, sheets, log)

    log.info(f"Load concluído. Planilha: https://docs.google.com/spreadsheets/d/{GOOGLE_SPREADSHEET_ID}")
