import logging

import pandas as pd


def enrich_proposta_com_programa(
    proposta_df: pd.DataFrame,
    programa_proposta_df: pd.DataFrame,
    programa_df: pd.DataFrame,
    log: logging.Logger,
) -> pd.DataFrame:
    """
    Enriquece proposta com dados de programa via programa_proposta.
    Retorna proposta_enriquecida: 1 linha por proposta (ou mais, no raro caso de
    propostas associadas a múltiplos programas — confirmado empiricamente, ~0.1% da
    base). Garantia: nenhuma linha de proposta é descartada (zero-or-one match por
    grupo, preservando todas as linhas via concat de matched + unmatched).
    """
    base = proposta_df.merge(programa_proposta_df, on="ID_PROPOSTA", how="left")
    base = base.reset_index(drop=True)
    base["_row_id"] = base.index

    prog_cols = [c for c in programa_df.columns if c not in base.columns]

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

    matched_ids = set(match_uf["_row_id"]) | set(match_brasil["_row_id"])
    unmatched = base[~base["_row_id"].isin(matched_ids)].copy()
    for col in prog_cols:
        unmatched[col] = pd.NA
    unmatched["programa_match_status"] = unmatched["ID_PROGRAMA"].isna().map(
        {True: "sem_programa", False: "sem_match"},
    )

    proposta_enriquecida = pd.concat(
        [match_uf, match_brasil, unmatched],
        ignore_index=True,
    )
    proposta_enriquecida = proposta_enriquecida.drop(columns=["_row_id"])

    if len(proposta_enriquecida) != len(base):
        raise ValueError(
            f"Enriquecimento perdeu ou duplicou linhas: base={len(base)}, "
            f"resultado={len(proposta_enriquecida)}",
        )

    log.info(
        f"  Enriquecimento proposta x programa: {len(proposta_enriquecida)} linhas "
        f"({(proposta_enriquecida['programa_match_status'] == 'uf_especifica').sum()} uf_especifica, "
        f"{(proposta_enriquecida['programa_match_status'] == 'brasil_todo').sum()} brasil_todo, "
        f"{(proposta_enriquecida['programa_match_status'] == 'sem_match').sum()} sem_match, "
        f"{(proposta_enriquecida['programa_match_status'] == 'sem_programa').sum()} sem_programa)",
    )
    return proposta_enriquecida
