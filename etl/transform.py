import json
import logging
from pathlib import Path

import pandas as pd

from etl.config import (
    CHUNK_SIZE,
    CONFIG_FILE,
    CSV_ENCODING,
    DATE_RE,
    EXCLUDED_AGREEMENT_NUMBERS,
    RAW_DIR,
    STAGING_DIR,
    TABLES,
    is_date_column,
    is_decimal_column,
    short_table_name_from_file,
)
from etl.cs_codigo import extrair_cs
from etl.enrichment import agregar_programa_por_proposta
from etl.links import link_proposta
from etl.plano_aplicacao import natureza_despesa_de_codigo
from etl.proposta import padronizar_nr_proposta
from etl.views import build_view

VIEW_SOURCE_TABLES = {
    "proposta",
    "programa",
    "programa_proposta",
    "convenio",
    "plano_aplicacao_detalhado",
    "cronograma_desembolso",
    "licitacao",
    "itens_licitacao",
    "pagamento",
}

SCHEMA_DIR = Path(__file__).parent / "views"


def load_view_definitions() -> list[dict]:
    definitions = []
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as schema_file:
            definitions.append(json.load(schema_file))
    return definitions


def load_target_programs(config_file: Path) -> list[str]:
    with open(config_file, encoding="utf-8") as config_file_handle:
        return [
            stripped
            for line in config_file_handle
            if (stripped := line.strip()) and not stripped.startswith("#")
        ]


def filter_raw_csv(
    path: Path,
    column: str,
    ids: set[str],
    *,
    chunk_size: int = CHUNK_SIZE,
) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        path,
        sep=";",
        encoding=CSV_ENCODING,
        dtype=str,
        chunksize=chunk_size,
    ):
        chunk.columns = chunk.columns.str.strip()
        filtered = chunk[chunk[column].isin(ids)]
        if not filtered.empty:
            chunks.append(filtered)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


def normalize(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()
    for col in normalized.columns:
        if is_date_column(col):
            normalized[col] = normalized[col].str.replace(
                DATE_RE, r"\3-\2-\1", regex=True,
            )
        elif is_decimal_column(col):
            normalized[col] = _normalize_financial_series(normalized[col])
    return normalized


def _normalize_financial_series(series: pd.Series) -> pd.Series:
    stripped = series.str.strip()
    has_comma = stripped.str.contains(",", na=False)
    transformed = stripped.str.replace(".", "", regex=False).str.replace(
        ",", ".", regex=False,
    )
    return stripped.where(~has_comma, transformed)


def write_staging_csv(dataframe: pd.DataFrame, staging_dir: Path, filename: str):
    dataframe.to_csv(
        staging_dir / filename,
        sep=";",
        index=False,
        encoding=CSV_ENCODING,
    )


def transform(log: logging.Logger):
    log.info("=== TRANSFORM ===")
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    id_sets: dict[str, set[str]] = {
        "program_codes": set(load_target_programs(CONFIG_FILE)),
    }
    log.info(
        f"Programas-alvo ({len(id_sets['program_codes'])}): "
        f"{sorted(id_sets['program_codes'])}",
    )

    log.info("=== TRANSFORM: NORMALIZE ===")
    dataframes_by_table: dict[str, pd.DataFrame] = {}

    for table in TABLES:
        filename = table["file"]
        filter_column = table["filter_column"]
        filter_ids = id_sets[table["filter_set"]]

        log.info(f"  Filtrando {filename} por {filter_column} ...")
        table_df = filter_raw_csv(
            RAW_DIR / filename,
            filter_column,
            filter_ids,
        )
        if filename == "siconv_convenio.csv" and "NR_CONVENIO" in table_df.columns:
            table_df = table_df[~table_df["NR_CONVENIO"].isin(EXCLUDED_AGREEMENT_NUMBERS)]

        log.info(f"    → {len(table_df)} registros")

        normalized_df = normalize(table_df)
        table_name = short_table_name_from_file(filename)
        if table_name == "proposta":
            if "NR_PROPOSTA" in normalized_df.columns:
                normalized_df["NR_PROPOSTA"] = normalized_df["NR_PROPOSTA"].map(
                    padronizar_nr_proposta,
                )
            if "ID_PROPOSTA" in normalized_df.columns:
                normalized_df["LINK_PROPOSTA"] = normalized_df["ID_PROPOSTA"].map(link_proposta)
        if table_name == "plano_aplicacao_detalhado":
            if "DESCRICAO_ITEM" in normalized_df.columns:
                normalized_df["CS_CODIGO"] = normalized_df["DESCRICAO_ITEM"].map(extrair_cs)
            if "COD_NATUREZA_DESPESA" in normalized_df.columns:
                normalized_df["NATUREZA_DESPESA"] = normalized_df["COD_NATUREZA_DESPESA"].map(
                    natureza_despesa_de_codigo,
                )
        write_staging_csv(normalized_df, STAGING_DIR, filename)

        if table_name in VIEW_SOURCE_TABLES:
            dataframes_by_table[table_name] = normalized_df

        if "extract_column" in table:
            extract_set = table["extract_set"]
            id_sets[extract_set] = set(table_df[table["extract_column"]].dropna().unique())
            log.info(f"  {len(id_sets[extract_set])} IDs em {extract_set}")

    log.info("Normalização concluída.")

    log.info("=== TRANSFORM: BUILD VIEWS ===")

    for table_name in sorted(VIEW_SOURCE_TABLES):
        log.info(f"  {table_name}: {len(dataframes_by_table[table_name])} registros")

    log.info("  Agregando programa por proposta (1:1) ...")
    proposta_enriquecida = agregar_programa_por_proposta(
        dataframes_by_table["proposta"],
        dataframes_by_table["programa_proposta"],
        dataframes_by_table["programa"],
        log,
    )
    write_staging_csv(proposta_enriquecida, STAGING_DIR, "proposta_enriquecida.csv")
    log.info(
        f"    → {len(proposta_enriquecida)} registros gravados em proposta_enriquecida.csv",
    )
    dataframes_by_table["proposta_enriquecida"] = proposta_enriquecida

    for definition in load_view_definitions():
        output_table = definition["output_table"]
        log.info(f"  Gerando view {output_table} ({definition['title']}) ...")

        view_df = build_view(definition, dataframes_by_table, log)
        output_file = f"{output_table}.csv"
        write_staging_csv(view_df, STAGING_DIR, output_file)

        log.info(
            f"    → {len(view_df)} registros gravados em {output_file} "
            f"(cardinalidade ok)",
        )

    log.info("Views concluídas.")

    log.info("Transform concluído.")
