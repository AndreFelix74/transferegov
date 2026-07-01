import logging
import zipfile
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from etl.config import RAW_DIR, TABLES, archive_name_for, archive_url_for


def _remote_mtime(table: dict) -> float:
    response = requests.head(
        archive_url_for(table), timeout=30, allow_redirects=True,
    )
    response.raise_for_status()
    return parsedate_to_datetime(response.headers["Last-Modified"]).timestamp()


def _local_mtime(csv_path: Path) -> float:
    return csv_path.stat().st_mtime if csv_path.exists() else 0.0


def _download_archive(table: dict, archive_path: Path):
    archive_name = archive_name_for(table)
    with requests.get(archive_url_for(table), stream=True, timeout=600) as response:
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


def _zip_needs_update(zip_file: dict) -> bool:
    zip_path = RAW_DIR / archive_name_for(zip_file)
    return _remote_mtime(zip_file) > _local_mtime(zip_path)


def extract(log: logging.Logger):
    log.info("=== EXTRACT ===")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    zips_to_update = [zip_file for zip_file in TABLES if _zip_needs_update(zip_file)]

    log.info("=== EXTRACT DOWNLOAD ===")
    with ThreadPoolExecutor(max_workers=2) as executor:
        download_futures = {
            executor.submit(
                _download_archive, zip_file, RAW_DIR / archive_name_for(zip_file),
            ): zip_file
            for zip_file in zips_to_update
        }
        for future in as_completed(download_futures):
            future.result()

    log.info("=== EXTRACT UNZIP ===")

    for zip_path in sorted(RAW_DIR.glob("*.zip")):
        _extract_archive(zip_path)

    log.info("Extract concluído.")
