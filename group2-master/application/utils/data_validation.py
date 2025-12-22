import pandas as pd
import numpy as np

def is_exempt(val):
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return (not np.isnan(val)) and (val > 0)
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in {'1','true','yes','y','是','免簽','免簽證','exempt','免'}

def adjust_cost(row, cpi_median):
    base = row['median_daily_acc_cost']
    cpi  = row['CPI'] if 'CPI' in row and pd.notna(row['CPI']) else np.nan
    if pd.notna(base) and pd.notna(cpi) and pd.notna(cpi_median) and cpi_median > 0:
        return base * (cpi / cpi_median)
    return base

def fmt(x, nd=0):
    try:
        return None if pd.isna(x) else (f"{x:.{nd}f}")
    except Exception:
        return x

def minmax(series):
    s = series.dropna()
    if s.empty:
        return pd.Series([np.nan]*len(series), index=series.index)
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series([0.5]*len(series), index=series.index)
    return (series - lo) / (hi - lo)