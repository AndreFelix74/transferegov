"""
Última situação (HISTORICO_SIT) de cada convênio, sem repetição.

A data reportada é a do início da situação atual: a primeira ocorrência
do bloco contínuo final de HISTORICO_SIT (ignora repetições anteriores
do mesmo status, ex.: sub-rogação / regravações).
"""
from __future__ import annotations

import pandas as pd

from etl.links import link_proposta

GROUP_COLS = ["ID_PROPOSTA", "NR_CONVENIO"]
DATE_COL = "DIA_HISTORICO_SIT"
SIT_COL = "HISTORICO_SIT"


def com_nr_convenio(df: pd.DataFrame) -> pd.DataFrame:
    nr = df["NR_CONVENIO"].fillna("").astype(str).str.strip()
    return df.loc[nr.ne("") & nr.str.lower().ne("nan")].copy()


def inicio_situacao_atual(group: pd.DataFrame) -> pd.Series:
    ordered = group.sort_values(DATE_COL, kind="mergesort").reset_index(drop=True)
    last_sit = ordered.iloc[-1][SIT_COL]

    i = len(ordered) - 1
    while i > 0 and ordered.iloc[i - 1][SIT_COL] == last_sit:
        i -= 1

    inicio = ordered.iloc[i]
    return pd.Series(
        {
            DATE_COL: inicio[DATE_COL],
            SIT_COL: last_sit,
            "COD_HISTORICO_SIT": inicio.get("COD_HISTORICO_SIT"),
        }
    )


def ultima_situacao_por_convenio(df: pd.DataFrame) -> pd.DataFrame:
    with_convenio = com_nr_convenio(df)
    with_convenio[DATE_COL] = pd.to_datetime(with_convenio[DATE_COL], errors="raise")

    ordered = with_convenio.sort_values(GROUP_COLS + [DATE_COL], kind="mergesort")
    rows: list[dict] = []

    for keys, group in ordered.groupby(GROUP_COLS, dropna=False, sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        id_proposta, nr_convenio = keys[0], keys[1]
        inicio = inicio_situacao_atual(group)
        rows.append(
            {
                "ID_PROPOSTA": id_proposta,
                "NR_CONVENIO": nr_convenio,
                DATE_COL: inicio[DATE_COL],
                SIT_COL: inicio[SIT_COL],
                "COD_HISTORICO_SIT": inicio["COD_HISTORICO_SIT"],
            }
        )

    result = pd.DataFrame(rows)
    result["LINK_PROPOSTA"] = result["ID_PROPOSTA"].map(link_proposta)
    cols = [
        "ID_PROPOSTA",
        "NR_CONVENIO",
        DATE_COL,
        SIT_COL,
        "COD_HISTORICO_SIT",
        "LINK_PROPOSTA",
    ]
    return result[cols]
