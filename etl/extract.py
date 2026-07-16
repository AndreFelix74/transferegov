import logging
import zipfile
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from etl.config import RAW_DIR, TABLES, archive_name_for, archive_url_for

MAX_RETRIES = 3


def _remote_mtime(table: dict) -> float:
    response = requests.head(
        archive_url_for(table), timeout=30, allow_redirects=True,
    )
    response.raise_for_status()
    return parsedate_to_datetime(response.headers["Last-Modified"]).timestamp()


def _local_mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def _archive_path_for(table: dict) -> Path:
    return RAW_DIR / archive_name_for(table)


def _extract_marker_for(archive_path: Path) -> Path:
    return Path(f"{archive_path}.done")


def _download_archive(table: dict, archive_path: Path, timeout: int):
    archive_name = archive_name_for(table)
    with requests.get(archive_url_for(table), stream=True, timeout=timeout) as response:
        response.raise_for_status()
        total_bytes = int(response.headers.get("content-length", 0))
        with open(archive_path, "wb") as output_file, tqdm(
            total=total_bytes, unit="B", unit_scale=True, desc=archive_name,
        ) as progress_bar:
            for chunk in response.iter_content(chunk_size=65536):
                output_file.write(chunk)
                progress_bar.update(len(chunk))


def _extract_archive(archive_path: Path):
    archive_name = archive_path.name
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.infolist():
                target_path = RAW_DIR / member.filename
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(target_path, "wb") as target, tqdm(
                    total=member.file_size, unit="B", unit_scale=True, desc=archive_name,
                ) as progress_bar:
                    while chunk := source.read(65536):
                        target.write(chunk)
                        progress_bar.update(len(chunk))
    except zipfile.BadZipFile as error:
        return error
    return None


def _process_table(table: dict, timeout: int, log: logging.Logger):
    archive_path = _archive_path_for(table)
    marker = _extract_marker_for(archive_path)

    for attempt in range(1, MAX_RETRIES + 1):
        needs_download = (
            not archive_path.exists()
            or _remote_mtime(table) > _local_mtime(archive_path)
        )
        if needs_download:
            marker.unlink(missing_ok=True)
            _download_archive(table, archive_path, timeout)

        if marker.exists():
            return

        error = _extract_archive(archive_path)
        if error is None:
            marker.touch()
            return

        log.warning(
            "Arquivo corrompido (tentativa %d/%d), removendo: %s (%s)",
            attempt, MAX_RETRIES, archive_path.name, error,
        )
        archive_path.unlink(missing_ok=True)

    raise RuntimeError(
        f"Falha ao extrair {archive_path.name} após {MAX_RETRIES} tentativas"
    )


def extract(log: logging.Logger):
    log.info("=== EXTRACT ===")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    timeout = 60
    max_workers = 3

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_table, table, timeout, log): table
            for table in TABLES
        }
        for future in as_completed(futures):
            future.result()

    log.info("Extract concluído.")
