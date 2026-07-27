import logging

import pandas as pd


def _concat_distinct(series: pd.Series) -> object:
    values = sorted({str(v).strip() for v in series.dropna() if str(v).strip()})
    if not values:
        return pd.NA
    return "; ".join(values)


def agregar_programa_por_proposta(
    proposta_df: pd.DataFrame,
    programa_proposta_df: pd.DataFrame,
    programa_df: pd.DataFrame,
    log: logging.Logger,
) -> pd.DataFrame:
    """
    Anexa COD_PROGRAMA e NOME_PROGRAMA à proposta, 1 linha por ID_PROPOSTA.

    Usa a mesma lógica de match (uf_especifica / brasil_todo) de antes; quando
    uma proposta casa com vários programas, concatena valores distintos com '; '.
    Propostas sem match preservam-se (left join): COD/NOME ficam nulos.
    """
    base = proposta_df.merge(programa_proposta_df, on="ID_PROPOSTA", how="left")
    base = base.reset_index(drop=True)
    base["_row_id"] = base.index

    match_uf = base.merge(
        programa_df,
        left_on=["ID_PROGRAMA", "UF_PROPONENTE", "NATUREZA_JURIDICA", "MODALIDADE"],
        right_on=[
            "ID_PROGRAMA",
            "UF_PROGRAMA",
            "NATUREZA_JURIDICA_PROGRAMA",
            "MODALIDADE_PROGRAMA",
        ],
        how="inner",
    )
    match_uf["programa_match_status"] = "uf_especifica"

    programa_brasil = programa_df[programa_df["UF_PROGRAMA"].isna()]
    match_brasil = base.merge(
        programa_brasil,
        left_on=["ID_PROGRAMA", "NATUREZA_JURIDICA", "MODALIDADE"],
        right_on=["ID_PROGRAMA", "NATUREZA_JURIDICA_PROGRAMA", "MODALIDADE_PROGRAMA"],
        how="inner",
    )
    match_brasil["programa_match_status"] = "brasil_todo"

    dup_match = set(match_uf["_row_id"]) & set(match_brasil["_row_id"])
    if dup_match:
        raise ValueError(
            f"{len(dup_match)} linhas casaram em ambos os critérios de programa "
            "(uf_especifica e brasil_todo) — pressuposto de exclusividade mútua "
            "violado, revisar a lógica de match antes de prosseguir."
        )

    matched = pd.concat([match_uf, match_brasil], ignore_index=True)

    n_uf = int((matched["programa_match_status"] == "uf_especifica").sum()) if len(matched) else 0
    n_brasil = int((matched["programa_match_status"] == "brasil_todo").sum()) if len(matched) else 0

    matched_ids = set(match_uf["_row_id"]) | set(match_brasil["_row_id"])
    unmatched = base[~base["_row_id"].isin(matched_ids)]
    n_sem_programa = int(unmatched["ID_PROGRAMA"].isna().sum())
    n_sem_match = int(unmatched["ID_PROGRAMA"].notna().sum())

    if matched.empty:
        aggregated = pd.DataFrame(
            columns=["ID_PROPOSTA", "COD_PROGRAMA", "NOME_PROGRAMA"],
        )
        n_collapsed = 0
    else:
        n_codes = matched.groupby("ID_PROPOSTA")["COD_PROGRAMA"].nunique(dropna=True)
        n_collapsed = int((n_codes > 1).sum())
        aggregated = (
            matched.groupby("ID_PROPOSTA", as_index=False)
            .agg(
                COD_PROGRAMA=("COD_PROGRAMA", _concat_distinct),
                NOME_PROGRAMA=("NOME_PROGRAMA", _concat_distinct),
            )
        )

    proposta_enriquecida = proposta_df.merge(
        aggregated,
        on="ID_PROPOSTA",
        how="left",
    )

    if len(proposta_enriquecida) != len(proposta_df):
        raise ValueError(
            f"Agregação alterou cardinalidade de proposta: "
            f"entrada={len(proposta_df)}, saída={len(proposta_enriquecida)}",
        )
    if proposta_enriquecida["ID_PROPOSTA"].duplicated().any():
        raise ValueError(
            "Agregação não é 1:1 por ID_PROPOSTA — há IDs duplicados na saída.",
        )

    n_com_programa = int(proposta_enriquecida["COD_PROGRAMA"].notna().sum())
    log.info(
        f"  Agregação programa por proposta: {len(proposta_enriquecida)} linhas (1:1) "
        f"({n_com_programa} com programa, {n_collapsed} com múltiplos programas concatenados; "
        f"pré-agregação: {n_uf} uf_especifica, {n_brasil} brasil_todo, "
        f"{n_sem_match} sem_match, {n_sem_programa} sem_programa)",
    )
    return proposta_enriquecida
