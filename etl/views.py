import logging

import pandas as pd


def _parse_join(join: str) -> tuple[str, str, str, str]:
    left, right = join.split(" = ", 1)
    left_table, left_column = left.strip().rsplit(".", 1)
    right_table, right_column = right.strip().rsplit(".", 1)
    return left_table, left_column, right_table, right_column


def _resolve_new_table(
    join: str,
    incorporated: set[str],
) -> tuple[str, str, str, str, str]:
    left_table, left_column, right_table, right_column = _parse_join(join)

    if left_table in incorporated and right_table not in incorporated:
        return left_table, left_column, right_table, right_column, right_table
    if right_table in incorporated and left_table not in incorporated:
        return right_table, right_column, left_table, left_column, left_table
    raise ValueError(
        f"Cannot resolve join '{join}': incorporated={sorted(incorporated)}",
    )


def _final_column_order(
    result: pd.DataFrame,
    table_columns: dict[str, list[str]],
    table_order: list[str],
    schema_column_order: list[str] | None,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    if schema_column_order is not None:
        for table in schema_column_order:
            for column in table_columns.get(table, []):
                if column in result.columns and column not in seen:
                    ordered.append(column)
                    seen.add(column)

    for table in table_order:
        if schema_column_order is not None and table in schema_column_order:
            continue
        for column in table_columns.get(table, []):
            if column in result.columns and column not in seen:
                ordered.append(column)
                seen.add(column)

    return ordered


def build_view(
    definition: dict,
    dataframes: dict[str, pd.DataFrame],
    log: logging.Logger,
) -> pd.DataFrame:
    base_table = definition["base_table"]
    joins = definition["joins"]
    output_table = definition["output_table"]

    if base_table not in dataframes:
        raise KeyError(f"Base table '{base_table}' not found in dataframes")

    result = dataframes[base_table].copy()
    expected_rows = len(result)
    incorporated = {base_table}
    table_order = [base_table]
    table_columns: dict[str, list[str]] = {
        base_table: list(dataframes[base_table].columns),
    }

    for join_index, join in enumerate(joins, start=1):
        (
            result_table,
            result_column,
            new_table,
            new_column,
            joined_table,
        ) = _resolve_new_table(join, incorporated)

        if joined_table not in dataframes:
            raise KeyError(f"Join table '{joined_table}' not found in dataframes")

        right = dataframes[joined_table].copy()

        left_key = result_column
        join_key_on_right = new_column if joined_table == new_table else result_column
        right_key = join_key_on_right

        missing_left = [key for key in (left_key,) if key not in result.columns]
        missing_right = [key for key in (right_key,) if key not in right.columns]
        if missing_left or missing_right:
            raise KeyError(
                f"Join keys missing for '{join}': "
                f"left={missing_left}, right={missing_right}",
            )

        overlapping = set(result.columns) & set(right.columns) - {right_key}
        rename_map: dict[str, str] = {}
        if overlapping:
            log.warning(
                f"Column collision in view '{output_table}' at join {join_index} ({join}): "
                f"{sorted(overlapping)}; prefixing with '{joined_table}_'",
            )
            for column in overlapping:
                rename_map[column] = f"{joined_table}_{column}"
            right = right.rename(columns=rename_map)

        result = result.merge(
            right,
            left_on=left_key,
            right_on=right_key,
            how="left",
        )
        result = result.drop(columns=[right_key])

        if len(result) != expected_rows:
            raise ValueError(
                f"Row count changed after join {join_index} ({join}): "
                f"expected {expected_rows}, got {len(result)}. "
                f"Possible fan-out from joining '{joined_table}'.",
            )

        incorporated.add(joined_table)
        table_order.append(joined_table)

        joined_columns: list[str] = []
        for column in dataframes[joined_table].columns:
            if column == right_key:
                continue
            actual_column = rename_map.get(column, column)
            joined_columns.append(actual_column)
        table_columns[joined_table] = joined_columns

    column_order = _final_column_order(
        result,
        table_columns,
        table_order,
        definition.get("column_order"),
    )

    missing_output = [column for column in column_order if column not in result.columns]
    if missing_output:
        raise KeyError(f"Output columns missing after joins: {missing_output}")

    return result[column_order]
