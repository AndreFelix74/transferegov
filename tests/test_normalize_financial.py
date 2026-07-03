"""Equivalence tests for vectorized financial value normalization."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from etl.transform import _normalize_financial_series


def _normalize_financial_value_legacy(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    text = str(value).strip()
    if not text or "," not in text:
        return text
    return text.replace(".", "").replace(",", ".")


SAMPLE_VALUES = ["1.234,56", "1234,56", "1234.56", "", None, np.nan, "0,00"]


def test_sample_values_match_legacy():
    series = pd.Series(SAMPLE_VALUES, dtype=object)
    legacy = series.map(_normalize_financial_value_legacy)
    vectorized = _normalize_financial_series(series.astype("string"))

    for original, old, new in zip(SAMPLE_VALUES, legacy, vectorized, strict=True):
        if pd.isna(old):
            assert pd.isna(new), f"{original!r}: expected NaN, got {new!r}"
        else:
            assert old == new, f"{original!r}: legacy={old!r}, vectorized={new!r}"


def test_real_csv_financial_columns_match_legacy():
    from etl.config import RAW_DIR, is_decimal_column

    mismatches = []

    for path in sorted(RAW_DIR.glob("siconv_*.csv")):
        table_df = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, nrows=50_000)
        table_df.columns = table_df.columns.str.strip()

        for col in table_df.columns:
            if not is_decimal_column(col):
                continue

            legacy = table_df[col].map(_normalize_financial_value_legacy)
            vectorized = _normalize_financial_series(table_df[col])
            diff_mask = ~(
                (legacy.isna() & vectorized.isna())
                | (legacy == vectorized)
            )
            if diff_mask.any():
                sample = table_df.loc[diff_mask, col].head(3).tolist()
                mismatches.append(
                    f"{path.name}:{col} ({diff_mask.sum()} rows) e.g. {sample}",
                )

    assert not mismatches, "Mismatches found:\n" + "\n".join(mismatches)


if __name__ == "__main__":
    test_sample_values_match_legacy()
    print("OK: sample values match legacy")
    test_real_csv_financial_columns_match_legacy()
    print("OK: real CSV financial columns match legacy")
