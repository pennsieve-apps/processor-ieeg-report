"""
Finding the upstream outputs.

Linked layout: each input port arrives in INPUT_DIR/<port>/ (placement: subfolder).
Flat layout (no links, files dropped together): everything somewhere under
INPUT_DIR. Either way a table is recognised by its file name and its columns
(conventions.md, "Tables written by the analysis steps"), and looked for in its
port's folder first, then anywhere. INPUT_DIR entries are often symlinks, so the
walk follows them.

Several links may feed one port (methods is a fan-in of seizure-dynasd,
seizure-ei and seizure-fragility): their folders arrive side by side and the
tables are found inside them by name.

Every table is optional. Tables with the same name in several folders (one
folder per LABEL, or two runs) are concatenated; a row that repeats a
(recording_id, channel[, band]) key already read is dropped with a warning.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger("processor-ieeg-report")

PORTS = ["ieeg", "qc", "spikes", "bandpower", "hfo", "abnormality", "onsets", "methods", "onset-zone"]

# name -> (port, required columns, key columns)
TABLES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "recordings.csv": ("ieeg", ("recording_id",), ("recording_id",)),
    "qc.csv": ("qc", ("recording_id", "channel", "status"), ("recording_id", "channel")),
    "spike_rates.csv": ("spikes", ("recording_id", "channel", "rate_per_min"), ("recording_id", "channel")),
    "bandpower.csv": ("bandpower", ("recording_id", "channel", "band", "rel_power"), ("recording_id", "channel", "band")),
    "hfo_rates.csv": ("hfo", ("recording_id", "channel", "rate_per_min"), ("recording_id", "channel", "band")),
    "channel_abnormality.csv": ("abnormality", ("recording_id", "channel", "max_abs_z"), ("recording_id", "channel")),
    "abnormality.csv": ("abnormality", ("recording_id", "channel", "band", "abs_z"), ("recording_id", "channel", "band")),
    "seizure_onsets.csv": ("onsets", ("recording_id", "onset_s"), ("recording_id", "method")),
    "channel_onsets.csv": ("onsets", ("recording_id", "channel", "onset_s"), ("recording_id", "channel", "method")),
    # Optional, not (yet) in conventions.md: DynaSD scores over time, long format.
    "channel_scores.csv": ("onsets", ("recording_id", "channel", "time_s", "score"), ("recording_id", "channel", "time_s")),
    "ei.csv": ("methods", ("recording_id", "channel", "ei"), ("recording_id", "channel")),
    "fragility.csv": ("methods", ("recording_id", "channel"), ("recording_id", "channel")),
    "onset_zone.csv": ("onset-zone", ("recording_id", "channel", "rank"), ("recording_id", "channel")),
    "scores.csv": ("onset-zone", ("recording_id", "method", "metric", "value"), ("recording_id", "method", "metric")),
}

# Files ieeg-prep's ieeg port may also carry; channel tables are matched by suffix.
CHANNELS_RE = re.compile(r"^(?P<stem>.+?)(?:_desc-[A-Za-z0-9]+)?_channels\.tsv$")
EVENTS_RE = re.compile(r"^(?P<stem>.+?)(?:_desc-[A-Za-z0-9]+)?_events\.tsv$")
SUBJECT_RE = re.compile(r"sub-([A-Za-z0-9]+)")


def walk(root: Path) -> list[Path]:
    """Every file under root, following symlinked folders, in a stable order."""
    out: list[Path] = []
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        real = os.path.realpath(dirpath)
        if real in seen:
            dirnames[:] = []
            continue
        seen.add(real)
        dirnames.sort()
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.is_file():
                out.append(p)
    return out


def read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        with open(path) as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError) as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None


def read_table(path: Path, sep: str = ",") -> pd.DataFrame | None:
    try:
        return pd.read_csv(path, sep=sep, dtype={"recording_id": str, "channel": str, "name": str,
                                                 "subject": str, "session": str, "run": str, "task": str})
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None


def under(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
        return True
    except ValueError:
        return False


def to_bool(v: Any) -> bool | None:
    """'true'/'false' (any case), 1/0, True/False; empty or anything else = unknown."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if pd.isna(v):
            return None
        return bool(v)
    s = str(v).strip().lower()
    if s in ("true", "t", "yes", "y", "1", "1.0"):
        return True
    if s in ("false", "f", "no", "n", "0", "0.0"):
        return False
    return None


def subject_of(recording_id: str) -> str:
    m = SUBJECT_RE.search(str(recording_id))
    return m.group(1) if m else str(recording_id).split("_")[0]


@dataclass
class Inputs:
    input_dir: Path
    files: list[Path] = field(default_factory=list)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    recordings: pd.DataFrame | None = None
    channels: dict[str, pd.DataFrame] = field(default_factory=dict)  # recording_id -> _channels.tsv
    events: dict[str, pd.DataFrame] = field(default_factory=dict)
    qc_figures: dict[str, Path] = field(default_factory=dict)  # recording_id -> png
    provenances: list[tuple[Path, dict[str, Any]]] = field(default_factory=list)
    dataset_description: dict[str, Any] | None = None
    found: dict[str, list[Path]] = field(default_factory=dict)

    def rel(self, path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return str(Path(path).relative_to(self.input_dir))
        except ValueError:
            return str(path)

    def table(self, name: str) -> pd.DataFrame | None:
        return self.tables.get(name)

    @property
    def has_any(self) -> bool:
        return any(self.found.get(p) for p in PORTS)


def _candidates(inp: Inputs, port: str, name: str) -> list[Path]:
    port_dir = inp.input_dir / port
    if port_dir.is_dir():
        inside = [f for f in inp.files if f.name == name and under(f, port_dir)]
        if inside:
            return inside
    return [f for f in inp.files if f.name == name]


def _gather_table(inp: Inputs, name: str) -> tuple[pd.DataFrame | None, list[Path]]:
    port, cols, keys = TABLES[name]
    frames, used = [], []
    for path in _candidates(inp, port, name):
        df = read_table(path)
        if df is None:
            continue
        if not all(c in df.columns for c in cols):
            log.warning("%s: not the expected table (needs %s); ignored", inp.rel(path), ", ".join(cols))
            continue
        if name == "fragility.csv" and not ({"rank", "fragility_post", "fragility_pre"} & set(df.columns)):
            log.warning("%s: no fragility_post/fragility_pre/rank column; ignored", inp.rel(path))
            continue
        df["recording_id"] = df["recording_id"].astype(str)
        if "channel" in df.columns:
            df["channel"] = df["channel"].astype(str)
        frames.append(df)
        used.append(path)
    if not frames:
        return None, []
    out = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    k = [c for c in keys if c in out.columns]
    if len(frames) > 1 and k:
        dup = out.duplicated(subset=k, keep="first")
        if dup.any():
            log.warning("%s: %d row(s) repeat a key already read from another folder; kept the first", name, int(dup.sum()))
            out = out[~dup].reset_index(drop=True)
    return out, used


def gather(input_dir: Path) -> Inputs:
    inp = Inputs(input_dir=input_dir, files=walk(input_dir))
    found: dict[str, list[Path]] = {p: [] for p in PORTS}

    for name, (port, _cols, _keys) in TABLES.items():
        df, used = _gather_table(inp, name)
        if df is not None:
            inp.tables[name] = df
            found[port].extend(used)
    inp.recordings = inp.tables.pop("recordings.csv", None)

    # BIDS sidecars: _channels.tsv / _events.tsv, preferring the ieeg port.
    ieeg_dir = inp.input_dir / "ieeg"
    pool = [f for f in inp.files if under(f, ieeg_dir)] if ieeg_dir.is_dir() else []
    if not any(CHANNELS_RE.match(f.name) for f in pool):
        pool = inp.files
    for f in pool:
        m = CHANNELS_RE.match(f.name)
        if m:
            df = read_table(f, sep="\t")
            if df is not None and "name" in df.columns:
                rid = m.group("stem")
                if rid in inp.channels:
                    log.warning("channels of %s found twice; keeping %s", rid, inp.rel(inp.channels[rid].attrs["path"]))
                    continue
                df["name"] = df["name"].astype(str)
                df.attrs["path"] = f
                inp.channels[rid] = df
                found["ieeg"].append(f)
            continue
        m = EVENTS_RE.match(f.name)
        if m:
            df = read_table(f, sep="\t")
            if df is not None and {"onset", "trial_type"} <= set(df.columns):
                inp.events.setdefault(m.group("stem"), df)
    for f in _candidates(inp, "ieeg", "dataset_description.json"):
        inp.dataset_description = read_json(f)
        if inp.dataset_description:
            break

    # QC figures of ieeg-prep: <recording_id>.png next to qc.csv.
    qc_dirs = {p.parent for p in found["qc"]}
    for d in qc_dirs:
        for f in sorted(d.glob("*.png")):
            inp.qc_figures.setdefault(f.stem, f)

    for f in inp.files:
        if f.name == "provenance.json":
            prov = read_json(f)
            if prov and prov.get("app"):
                inp.provenances.append((f, prov))

    inp.found = {k: sorted(set(v), key=str) for k, v in found.items()}
    return inp
