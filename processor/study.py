"""
The recordings and channels the report talks about, from ieeg-prep's derivative
(recordings.csv, _channels.tsv, _events.tsv) when it is linked, and otherwise
from the keys of whatever tables are present.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from processor.inputs import Inputs, subject_of, to_bool

LABELS = ("soz", "resected", "onset", "spread")
_TRAILING_DIGITS = re.compile(r"^(.*?)(\d+)$")


def electrode_of(channel: str, contacts: Any = None) -> str:
    """The electrode (shaft/grid) a channel belongs to: its first contact's name
    without the trailing contact number ('LA01-LA02' -> 'LA', 'RB3' -> 'RB')."""
    first = str(contacts).split("|")[0] if isinstance(contacts, str) and contacts else str(channel).split("-")[0]
    m = _TRAILING_DIGITS.match(first.strip())
    name = m.group(1) if m and m.group(1) else first
    return name.rstrip("_' ") or first


def contact_number(channel: str) -> int:
    m = _TRAILING_DIGITS.match(str(channel).split("-")[0].strip())
    return int(m.group(2)) if m else 0


@dataclass
class Recording:
    recording_id: str
    subject: str
    task: str = ""
    sfreq: float | None = None
    duration_s: float | None = None
    montage: str = ""
    kind: str = ""
    n_channels: int | None = None
    n_good: int | None = None
    onset_s: float | None = None          # expert / clinical onset
    seizure_end_s: float | None = None
    stim_induced: bool | None = None
    stim_source: str = ""                 # 'recordings.csv' | 'task name' | ''
    lvfa: bool | None = None
    channels: pd.DataFrame | None = None  # _channels.tsv with electrode added

    @property
    def is_ictal(self) -> bool:
        return self.kind == "ictal" or self.onset_s is not None


@dataclass
class Study:
    recordings: dict[str, Recording] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def subjects(self) -> list[str]:
        return sorted({r.subject for r in self.recordings.values()})

    def of_subject(self, subject: str) -> list[Recording]:
        return [r for r in sorted(self.recordings.values(), key=lambda r: r.recording_id) if r.subject == subject]

    def labels_known(self) -> set[str]:
        out = set()
        for r in self.recordings.values():
            if r.channels is None:
                continue
            for lab in LABELS:
                if lab in r.channels.columns and r.channels[lab].map(to_bool).notna().any():
                    out.add(lab)
        return out


def _float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def _channels(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["channel"] = df["name"].astype(str)
    contacts = df["contacts"] if "contacts" in df.columns else pd.Series([None] * len(df), index=df.index)
    df["electrode"] = [electrode_of(c, k) for c, k in zip(df["channel"], contacts)]
    for lab in LABELS:
        df[lab] = df[lab].map(to_bool) if lab in df.columns else None
    for c in ("x", "y", "z"):
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df.columns else np.nan
    if "status" not in df.columns:
        df["status"] = "good"
    df["status"] = df["status"].fillna("good").astype(str).str.lower()
    return df


def build(inp: Inputs) -> Study:
    st = Study()
    rec = inp.recordings
    ids: list[str] = []
    if rec is not None:
        ids = list(dict.fromkeys(rec["recording_id"].astype(str)))
    # Recordings named only by the analysis tables (no recordings.csv linked).
    for name, df in inp.tables.items():
        if name in ("scores.csv",):
            continue
        for rid in df["recording_id"].astype(str).unique():
            if rid not in ids and rid not in ("ALL", "all"):
                ids.append(rid)
    for rid in inp.channels:
        if rid not in ids:
            ids.append(rid)
    if rec is None and ids:
        st.notes.append("recordings.csv was not among the inputs: recordings are named from the tables; "
                        "expert onsets, montage and sampling rates are unknown unless the _channels.tsv/_events.tsv files are present.")

    rows = {str(r["recording_id"]): r for r in rec.to_dict(orient="records")} if rec is not None else {}
    for rid in ids:
        r = rows.get(rid, {})
        subject = str(r.get("subject")) if r.get("subject") not in (None, "") and not pd.isna(r.get("subject")) else subject_of(rid)
        task = str(r.get("task")) if r.get("task") not in (None, "") and not pd.isna(r.get("task")) else ""
        if not task:
            m = re.search(r"task-([A-Za-z0-9]+)", rid)
            task = m.group(1) if m else ""
        R = Recording(recording_id=rid, subject=subject, task=task, sfreq=_float(r.get("sfreq")),
                      duration_s=_float(r.get("duration_s")), montage=str(r.get("montage") or "") if not pd.isna(r.get("montage", "")) else "",
                      kind=str(r.get("kind") or "") if not pd.isna(r.get("kind", "")) else "",
                      n_channels=int(r["n_channels"]) if _float(r.get("n_channels")) is not None else None,
                      n_good=int(r["n_good"]) if _float(r.get("n_good")) is not None else None,
                      onset_s=_float(r.get("onset_s")))
        # Seizure type flags: recordings.csv columns first (seizure-consensus reads the same ones).
        if "stim_induced" in r:
            R.stim_induced = to_bool(r.get("stim_induced"))
            R.stim_source = "recordings.csv" if R.stim_induced is not None else ""
        if R.stim_induced is None and R.task:
            # BIDS task names of the Multi-Expert Seizure Annotation dataset: task-stim<N> / task-ictal<N>.
            if re.fullmatch(r"stim\d*", R.task, flags=re.I):
                R.stim_induced, R.stim_source = True, "task name"
            elif re.fullmatch(r"ictal\d*", R.task, flags=re.I):
                R.stim_induced, R.stim_source = False, "task name"
        if "lvfa" in r:
            R.lvfa = to_bool(r.get("lvfa"))
        ev = inp.events.get(rid)
        if ev is not None:
            sz = ev[ev["trial_type"].astype(str).str.lower().isin(["seizure", "ictal"])]
            if not sz.empty:
                on = _float(sz["onset"].iloc[0])
                if R.onset_s is None:
                    R.onset_s = on
                dur = _float(sz["duration"].iloc[0]) if "duration" in sz.columns else None
                if on is not None and dur is not None:
                    R.seizure_end_s = on + dur
        ch = inp.channels.get(rid)
        if ch is not None:
            R.channels = _channels(ch)
            if R.n_channels is None:
                R.n_channels = len(R.channels)
            if R.n_good is None:
                R.n_good = int((R.channels["status"] == "good").sum())
        st.recordings[rid] = R
    return st


def channel_frame(rec: Recording, channels: list[str]) -> pd.DataFrame:
    """Labels, coordinates and electrode for a list of channels of a recording
    (from its _channels.tsv when known)."""
    base = pd.DataFrame({"channel": channels})
    if rec.channels is None:
        base["electrode"] = [electrode_of(c) for c in channels]
        for lab in LABELS:
            base[lab] = None
        for c in ("x", "y", "z"):
            base[c] = np.nan
        base["space"] = ""
        base["roi"] = ""
        return base
    cols = ["channel", "electrode", *LABELS, "x", "y", "z"]
    extra = [c for c in ("space", "roi", "status") if c in rec.channels.columns]
    m = base.merge(rec.channels[cols + extra].drop_duplicates("channel"), on="channel", how="left")
    m["electrode"] = [e if isinstance(e, str) else electrode_of(c) for c, e in zip(m["channel"], m["electrode"])]
    for c in ("space", "roi"):
        if c not in m.columns:
            m[c] = ""
        m[c] = m[c].fillna("").astype(str)
    return m
