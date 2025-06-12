import os
import re
import pandas as pd
import numpy as np
from collections import Counter

def optimize_data_types(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Downcast numeric columns where possible to save memory.
    """
    if verbose:
        before = df.memory_usage(deep=True).sum() / 1024**2
        print(f"[optimize] Memory before: {before:.2f} MB")

    df_opt = df.copy()
    for col in df_opt.columns:
        dt = df_opt[col].dtype

        # FLOATS → pandas nullable Int64 if no fractional part
        if pd.api.types.is_float_dtype(dt):
            non_null = df_opt[col].dropna()
            if (non_null == non_null.astype(int)).all():
                df_opt[col] = df_opt[col].astype("Int64")

        # INTEGERS → downcast to Int8/Int16/Int32 where it fits
        elif pd.api.types.is_integer_dtype(dt):
            non_null = df_opt[col].dropna()
            if not non_null.empty:
                mn, mx = non_null.min(), non_null.max()
                if -128 <= mn <= mx <= 127:
                    df_opt[col] = df_opt[col].astype("Int8")
                elif -32768 <= mn <= mx <= 32767:
                    df_opt[col] = df_opt[col].astype("Int16")
                elif -2**31 <= mn <= mx <= 2**31 - 1:
                    df_opt[col] = df_opt[col].astype("Int32")

    if verbose:
        after = df_opt.memory_usage(deep=True).sum() / 1024**2
        print(f"[optimize] Memory after:  {after:.2f} MB (saved {before-after:.2f} MB)")

    return df_opt
    """
    Downcast numeric columns where possible to save memory.
    """
    if verbose:
        before = df.memory_usage(deep=True).sum() / 1024**2
        print(f"[optimize] Memory before: {before:.2f} MB")

    df_opt = df.copy()
    for col in df_opt.columns:
        dt = df_opt[col].dtype
        if pd.api.types.is_float_dtype(dt):
            non_null = df_opt[col].dropna()
            if (non_null == non_null.astype(int)).all():
                df_opt[col] = df_opt[col].astype("Int64")
        elif pd.api.types.is_integer_dtype(dt) or pd.api.types.is_integer_dtype(dt, include_nullable=True):
            non_null = df_opt[col].dropna()
            if not non_null.empty:
                mn, mx = non_null.min(), non_null.max()
                if -128 <= mn <= mx <= 127:
                    df_opt[col] = df_opt[col].astype("Int8")
                elif -32768 <= mn <= mx <= 32767:
                    df_opt[col] = df_opt[col].astype("Int16")
                elif -2**31 <= mn <= mx <= 2**31 - 1:
                    df_opt[col] = df_opt[col].astype("Int32")

    if verbose:
        after = df_opt.memory_usage(deep=True).sum() / 1024**2
        print(f"[optimize] Memory after:  {after:.2f} MB (saved {before-after:.2f} MB)")

    return df_opt

def merge_team_data(folder: str) -> pd.DataFrame:
    """
    Read all CSVs in `folder` that contain 'TEAM NO' and outer-merge them,
    handling common columns vs. renaming conflicts automatically.
    """
    dfs = []
    for fn in sorted(os.listdir(folder)):
        path = os.path.join(folder, fn)
        if fn.lower().endswith(".csv"):
            df = pd.read_csv(path)
            if "TEAM NO" in df.columns:
                print(f"[merge] Loading {fn}")
                dfs.append(df)
            else:
                print(f"[merge] Skipping {fn} (no TEAM NO)")

    if not dfs:
        raise ValueError("[merge] No files with 'TEAM NO' found.")

    merged = dfs[0].copy()
    for i, df in enumerate(dfs[1:], start=2):
        common = [c for c in df.columns if c in merged.columns and c != "TEAM NO"]
        rename_map = {}
        merge_on = ["TEAM NO"]

        # Decide which common columns truly match
        for col in common:
            tmp = pd.merge(
                merged[["TEAM NO", col]],
                df[["TEAM NO", col]],
                on="TEAM NO",
                how="inner",
                suffixes=("_m", "_d")
            ).dropna()
            # treat NaN == NaN as equal
            if not tmp.empty:
                eq = ((tmp[f"{col}_m"] == tmp[f"{col}_d"]) |
                      (tmp[f"{col}_m"].isna() & tmp[f"{col}_d"].isna()))
                if eq.all():
                    merge_on.append(col)
                else:
                    rename_map[col] = f"{col}_file{i}"
            else:
                rename_map[col] = f"{col}_file{i}"

        df2 = df.rename(columns=rename_map)
        merged = pd.merge(merged, df2, on=merge_on, how="outer")
        print(f"[merge] After file #{i}: {merged.shape[0]} rows × {merged.shape[1]} cols")

    return merged

def collapse_duplicate_rows(df: pd.DataFrame, key: str = "TEAM NO") -> pd.DataFrame:
    """
    For each key, keep the first non-null in every column.
    Guarantees one row per key.
    """
    print("[collapse] Collapsing duplicate rows…")
    return df.set_index(key).groupby(level=0).first().reset_index()

def coalesce_duplicate_columns(df: pd.DataFrame, pattern: str = r"(.+?)(?:_file\d+)?$") -> pd.DataFrame:
    """
    For columns sharing a base name (e.g. X, X_file2, X_file3):
      - If all variants are identical (treating NaN==NaN), drop the extras.
      - Otherwise, coalesce via first non-null across variants.
    """
    print("[coalesce] Coalescing duplicate columns…")
    cols = df.columns.tolist()
    groups = {}
    for c in cols:
        base = re.match(pattern, c).group(1)
        groups.setdefault(base, []).append(c)

    for base, variants in groups.items():
        if len(variants) <= 1:
            continue
        master, *others = variants
        # check if all variants equal master (NaN == NaN)
        identical = True
        for v in others:
            s1, s2 = df[master], df[v]
            eq = (s1 == s2) | (s1.isna() & s2.isna())
            if not eq.all():
                identical = False
                break

        if identical:
            df.drop(columns=others, inplace=True)
        else:
            # coalesce: first non-null in the variants
            df[base] = df[variants].bfill(axis=1).iloc[:, 0]
            df.drop(columns=variants, inplace=True)

    return df
def process_team_data(
    folder: str,
    collapse_rows: bool = False,
    coalesce_cols: bool = False,
    optimize: bool = False,
    exclude_non_numeric: bool = False
) -> pd.DataFrame:
    """
    Full pipeline:
      1) merge all files on 'TEAM NO'
      2) optionally drop any columns that are not numeric
      3) collapse duplicate rows by key
      4) coalesce duplicate columns
      5) optimize numeric data types

    Toggle steps via boolean flags.
    """
    # 1) Merge
    df = merge_team_data(folder)

    # 2) Exclude non-numeric columns (if requested)
    if exclude_non_numeric:
        non_num_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
        print(f"[filter] Dropping non-numeric columns: {non_num_cols}")
        df = df.select_dtypes(include=[np.number])

    # 3) Collapse duplicate rows
    if collapse_rows:
        df = collapse_duplicate_rows(df)

    # 4) Coalesce duplicate columns
    if coalesce_cols:
        df = coalesce_duplicate_columns(df)

    # 5) Optimize numeric types
    if optimize:
        df = optimize_data_types(df, verbose=True)

    return df

if __name__ == "__main__":
    teamdata_folder = "./teamdata"

    # ==== SET THESE FLAGS ====
    DO_COLLAPSE           = True
    DO_COALESCE           = True
    DO_OPTIMIZE           = True
    EXCLUDE_NON_NUMERIC   = True 
    # =========================

    final_df = process_team_data(
        teamdata_folder,
        collapse_rows=DO_COLLAPSE,
        coalesce_cols=DO_COALESCE,
        optimize=DO_OPTIMIZE,
        exclude_non_numeric=EXCLUDE_NON_NUMERIC
    )
    final_df.to_csv("merged_team_data.csv", index=False)
    print(f"[done] Saved 'merged_team_data.csv' "
          f"({final_df.shape[0]} rows × {final_df.shape[1]} cols)")