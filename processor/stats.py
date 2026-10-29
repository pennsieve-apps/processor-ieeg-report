"""Small statistics used by the report (NumPy/pandas only)."""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd


def auc(scores: Iterable[float], labels: Iterable[bool]) -> tuple[float | None, int, int]:
    """ROC AUC as the Mann-Whitney probability that a positive outranks a negative
    (ties count one half; Hanley & McNeil 1982). Rows with a missing score or label
    are left out. Returns (auc or None, n_positive, n_negative)."""
    s = pd.Series(list(scores), dtype="float64")
    y = pd.Series(list(labels), dtype="object")
    ok = s.notna() & y.notna()
    s, y = s[ok].to_numpy(), y[ok].astype(bool).to_numpy()
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return None, n_pos, n_neg
    ranks = pd.Series(s).rank(method="average").to_numpy()
    u = ranks[y].sum() - n_pos * (n_pos + 1) / 2
    return float(u / (n_pos * n_neg)), n_pos, n_neg


def roc_curve(scores: Iterable[float], labels: Iterable[bool]) -> tuple[np.ndarray, np.ndarray] | None:
    """False and true positive rates over every threshold (ties stepped together)."""
    s = pd.Series(list(scores), dtype="float64")
    y = pd.Series(list(labels), dtype="object")
    ok = s.notna() & y.notna()
    s, y = s[ok].to_numpy(), y[ok].astype(bool).to_numpy()
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    order = np.argsort(-s, kind="mergesort")
    s, y = s[order], y[order]
    distinct = np.r_[np.where(np.diff(s))[0], len(s) - 1]
    tps = np.cumsum(y)[distinct]
    fps = np.cumsum(~y)[distinct]
    return np.r_[0.0, fps / n_neg], np.r_[0.0, tps / n_pos]


def spearman(a: Iterable[float], b: Iterable[float]) -> tuple[float | None, int]:
    x = pd.Series(list(a), dtype="float64")
    y = pd.Series(list(b), dtype="float64")
    ok = x.notna() & y.notna()
    n = int(ok.sum())
    if n < 3:
        return None, n
    rx, ry = x[ok].rank(), y[ok].rank()
    if rx.std() == 0 or ry.std() == 0:
        return None, n
    return float(np.corrcoef(rx, ry)[0, 1]), n


def top_k(series: pd.Series, k: int) -> set[str]:
    """Index labels of the k largest values (missing values never selected)."""
    s = series.dropna().sort_values(ascending=False, kind="mergesort")
    return set(s.index[:k])


def overlap(a: set[str], b: set[str]) -> float | None:
    if not a or not b:
        return None
    return len(a & b) / min(len(a), len(b))


def describe(values: Iterable[float]) -> dict[str, Any]:
    v = pd.Series(list(values), dtype="float64").dropna()
    if v.empty:
        return {"n": 0, "median": None, "q1": None, "q3": None, "min": None, "max": None}
    return {"n": int(v.size), "median": float(v.median()), "q1": float(v.quantile(0.25)),
            "q3": float(v.quantile(0.75)), "min": float(v.min()), "max": float(v.max())}


def clean(obj: Any) -> Any:
    """JSON-safe: NaN/inf -> None, NumPy scalars -> Python, Paths -> str."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, pd.DataFrame):
        return clean(obj.to_dict(orient="records"))
    if obj is pd.NA or obj is pd.NaT:
        return None
    if hasattr(obj, "__fspath__"):
        return str(obj)
    return obj


def num(v: Any, d: int = 2) -> str:
    if v is None:
        return "–"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return "–"
    return f"{f:.{d}f}"
