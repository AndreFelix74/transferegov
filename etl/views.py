import logging

import pandas as pd

_ROW_ID_COLUMN = "__row_id__"


def _parse_join(join: str) -> tuple[str, str, str, str]:
    left, right = join.split(" = ", 1)
    left_table, left_column = left.strip().rsplit(".", 1)
    right_table, right_column = right.strip().rsplit(".", 1)
    return left_table, left_column, right_table, right_column


def build_view(
    definition: dict,
    dataframes: dict[str, pd.DataFrame],
    log: logging.Logger,
) -> pd.DataFrame:
    joins = definition["joins"]
    output_table = definition["output_table"]

    first_left_table, _, _, _ = _parse_join(joins[0])
    result = dataframes[first_left_table].copy()

    for join_index, join in enumerate(joins, start=1):
        _, left_column, right_table, right_column = _parse_join(join)

        right_df = dataframes[right_table].copy()
        right_df[_ROW_ID_COLUMN] = range(len(right_df))

        result = result.merge(
            right_df,
            left_on=left_column,
            right_on=right_column,
            how="left",
        )

        row_counts = result[_ROW_ID_COLUMN].value_counts(dropna=True)

        duplicated_ids = row_counts[row_counts > 1]
        if not duplicated_ids.empty:
            raise ValueError(
                f"{len(duplicated_ids)} rows from '{right_table}' matched more "
                f"than one row on the left side after join {join_index} ({join}) "
                f"in view '{output_table}'. Possible fan-out from '{right_table}'.",
            )

        missing_count = len(right_df) - len(row_counts)
        if missing_count > 0:
            raise ValueError(
                f"{missing_count} rows from '{right_table}' had no match "
                f"after join {join_index} ({join}) in view '{output_table}'.",
            )

        result = result.drop(columns=[_ROW_ID_COLUMN])

    return result
