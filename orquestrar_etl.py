"""
Orquestração do ETL SICONV - Cozinha Solidária / MDS
=====================================================
Extract  → Baixa os zips individuais de https://repositorio.dados.gov.br/seges/detru/ e extrai para ./raw
Transform → Normaliza dados de ./raw em ./staging e gera tabelas largas declarativas
Load      → Carrega os CSVs de ./staging na planilha Google Sheets

Uso:
    python orquestrar_etl.py             # Executa as 3 fases
    python orquestrar_etl.py --extract   # Só baixa e extrai
    python orquestrar_etl.py --transform # Normaliza + gera views (assume raw já populado)
    python orquestrar_etl.py --normalize # Só normaliza raw → staging
    python orquestrar_etl.py --build-views # Só gera tabelas largas (assume staging normalizado)
    python orquestrar_etl.py --load      # Só carrega na planilha (assume staging já populado)
"""

import argparse
import logging
from datetime import datetime

from etl import extract, load, transform
from etl.config import LOG_DIR


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"etl_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("etl_siconv")


def main():
    parser = argparse.ArgumentParser(description="ETL SICONV - Cozinha Solidária")
    parser.add_argument("--extract", action="store_true", help="Só fase Extract")
    parser.add_argument("--transform", action="store_true", help="Normaliza + gera views")
    parser.add_argument("--normalize", action="store_true", help="Só normaliza raw → staging")
    parser.add_argument("--build-views", action="store_true", help="Só gera tabelas largas")
    parser.add_argument("--load", action="store_true", help="Só fase Load")
    args = parser.parse_args()

    log = setup_logging()
    log.info("ETL SICONV iniciado.")

    transform_steps = args.transform or args.normalize or args.build_views
    run_all = not (args.extract or transform_steps or args.load)

    if run_all or args.extract:
        extract(log)

    if run_all or args.transform or args.normalize or args.build_views:
        transform(log)

    if run_all or args.load:
        load(log)

    log.info("ETL finalizado.")


if __name__ == "__main__":
    main()
