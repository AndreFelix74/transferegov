import json
import logging
import time

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

from etl.config import (
    CSV_ENCODING,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_SPREADSHEET_ID,
    STAGING_DIR,
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
    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SPREADSHEET_ID,
        range=_sheet_range(sheet_name, cell),
        valueInputOption="USER_ENTERED",
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
        time.sleep(5)

    log.info(f"Load concluído. Planilha: https://docs.google.com/spreadsheets/d/{GOOGLE_SPREADSHEET_ID}")
