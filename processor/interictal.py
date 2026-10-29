"""
Interictal Biomarker Mapping: per subject, one row per channel with its spike
rate (ieeg-spikes), ripple / fast-ripple rate (ieeg-hfo) and band-power
abnormality (ieeg-normative), the expert labels, and how well each measure
separates the labelled channels (ROC AUC). The report does not fit anything:
leave-one-patient-out is done upstream by ieeg-normative.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from processor import stats as S
from processor.inputs import Inputs, subject_of
from processor.study import Recording, Study, channel_frame, contact_number

# measure key -> (label, unit, source table)
MEASURES: dict[str, tuple[str, str, str]] = {
    "spike_rate": ("Spike rate", "/min", "spike_rates.csv"),
    "ripple_rate": ("Ripple rate", "/min", "hfo_rates.csv"),
    "fast_ripple_rate": ("Fast-ripple rate", "/min", "hfo_rates.csv"),
    "max_abs_z": ("Band-power abnormality", "max |z|", "channel_abnormality.csv"),
}

# Labels an AUC is computed against, in order. "onset" = expert seizure-onset channel
# in at least one seizure of the subject (only when soz/resected are not known).
TARGETS = {"soz": "SOZ", "resected": "resected", "onset_any": "seizure onset (any seizure)"}

WHAT_IT_TELLS = {
    "spike_rate": ("Interictal spikes mark the irritative zone. It overlaps the seizure-onset zone but is usually larger; "
                   "a high spike rate is common outside the SOZ, and rates change with sleep, medication and time since the "
                   "last seizure. A rate from a short clip is a sample, not a patient's typical rate."),
    "ripple_rate": ("Ripples (80–250 Hz) occur in epileptic tissue but are also physiological, notably in mesial temporal "
                    "and occipital cortex, so a high ripple rate alone does not separate pathological from normal tissue. "
                    "Detector settings change the counts."),
    "fast_ripple_rate": ("Fast ripples (250–500 Hz) are more specific to epileptogenic tissue than ripples but need a "
                         "sampling rate of at least ~2000 Hz and are rare; zero counts are common."),
    "max_abs_z": ("How far a channel's band power lies from normative channels at the same brain location (HUP atlas, "
                  "MNI space). In ieeg-normative's own leave-one-patient-out validation over all 60 atlas patients this "
                  "maximum |z| separated SOZ channels from the others at about chance (pooled AUC 0.48 SOZ, 0.47 resected). "
                  "Treat it as exploratory. Channels without MNI coordinates, or with too few atlas channels nearby, are not scored."),
}


def _per_channel(df: pd.DataFrame, value: str, count: str | None, subj) -> pd.DataFrame:
    """Per (subject, channel): pooled rate (sum of counts / sum of minutes) when
    counts and minutes exist, else the mean over recordings."""
    df = df.copy()
    df["subject"] = df["recording_id"].map(subj)
    if count and count in df.columns and "minutes" in df.columns:
        g = df.groupby(["subject", "channel"], sort=False).agg(n=(count, "sum"), minutes=("minutes", "sum"),
                                                                 mean=(value, "mean"), n_rec=("recording_id", "nunique"))
        g[value] = np.where(g["minutes"] > 0, g["n"] / g["minutes"].where(g["minutes"] > 0), g["mean"])
        return g[[value, "n_rec", "minutes"]].reset_index()
    g = df.groupby(["subject", "channel"], sort=False).agg(**{value: (value, "mean"), "n_rec": ("recording_id", "nunique")})
    return g.reset_index()


def analyse(inp: Inputs, study: Study) -> dict[str, Any] | None:
    spikes = inp.table("spike_rates.csv")
    hfo = inp.table("hfo_rates.csv")
    abn = inp.table("channel_abnormality.csv")
    bp = inp.table("bandpower.csv")
    if spikes is None and hfo is None and abn is None and bp is None:
        return None

    def subj(rid: str) -> str:
        r = study.recordings.get(str(rid))
        return r.subject if r else subject_of(rid)

    def sub(df):
        if df is None:
            return None
        df = df.copy()
        df["recording_id"] = df["recording_id"].astype(str)
        return df

    frames = []
    available: dict[str, str] = {}
    notes: list[str] = []
    if spikes is not None and not spikes.empty:
        sp = _per_channel(sub(spikes), "rate_per_min", "n_spikes", subj).rename(columns={"rate_per_min": "spike_rate",
                                                                                    "n_rec": "n_rec_spikes",
                                                                                    "minutes": "spike_minutes"})
        frames.append(sp)
        available["spike_rate"] = "ieeg-spikes"
        if "detector" in spikes.columns:
            notes.append("Spike detector: " + ", ".join(sorted(spikes["detector"].dropna().astype(str).unique())) + ".")
    if hfo is not None and not hfo.empty:
        h = sub(hfo)
        band_col = "band" if "band" in h.columns else None
        for band, key in (("ripple", "ripple_rate"), ("fast_ripple", "fast_ripple_rate")):
            part = h[h[band_col].astype(str) == band] if band_col else (h if band == "ripple" else h.iloc[0:0])
            if part.empty:
                continue
            frames.append(_per_channel(part, "rate_per_min", "n_hfo", subj).rename(columns={"rate_per_min": key, "n_rec": f"n_rec_{key}",
                                                                                     "minutes": f"{key}_minutes"}))
            available[key] = "ieeg-hfo"
    if hfo is not None and hfo.empty:
        notes.append("ieeg-hfo analysed no recording (its table is empty: HFOs need a sampling rate of at least 1000 Hz).")
    if abn is not None and not abn.empty:
        a = sub(abn)
        a["max_abs_z"] = pd.to_numeric(a["max_abs_z"], errors="coerce")
        if a["max_abs_z"].notna().any():
            frames.append(_per_channel(a, "max_abs_z", None, subj).rename(columns={"n_rec": "n_rec_abn"}))
            available["max_abs_z"] = "ieeg-normative"
            if "region" in a.columns:
                reg = a.assign(subject=a["recording_id"].map(subj)).groupby(["subject", "channel"])["region"].first().reset_index()
                frames.append(reg.rename(columns={"region": "abn_region"}))
        else:
            notes.append("ieeg-normative scored no channel (no channel had MNI coordinates with enough atlas channels nearby).")

    if not frames:
        return {"subjects": [], "available": available, "notes": notes, "bandpower_only": bp is not None}

    table = frames[0]
    for f in frames[1:]:
        table = table.merge(f, on=["subject", "channel"], how="outer")

    subjects = []
    all_rows = []
    for subject in sorted(table["subject"].unique()):
        t = table[table["subject"] == subject].copy()
        recs = study.of_subject(subject)
        # labels/coords from the subject's recordings: soz/resected per subject (any recording),
        # onset per seizure -> count.
        info = None
        onset_n = pd.Series(0, index=t["channel"].values, dtype="int64")
        onset_known = pd.Series(0, index=t["channel"].values, dtype="int64")
        for r in recs:
            cf = channel_frame(r, list(t["channel"]))
            if info is None:
                info = cf.set_index("channel")
            else:
                cfi = cf.set_index("channel")
                for lab in ("soz", "resected"):
                    info[lab] = [_any(a, b) for a, b in zip(info[lab], cfi[lab])]
                for c in ("x", "y", "z"):
                    info[c] = info[c].fillna(cfi[c])
                for c in ("space", "roi"):
                    info[c] = [a or b for a, b in zip(info[c], cfi[c])]
            on = cf.set_index("channel")["onset"]
            onset_known += on.notna().astype(int).reindex(onset_known.index).fillna(0).astype(int).values
            onset_n += on.map(lambda v: 1 if v is True else 0).reindex(onset_n.index).fillna(0).astype(int).values
        if info is None:
            info = channel_frame(Recording(recording_id="", subject=subject), list(t["channel"])).set_index("channel")
        t = t.set_index("channel")
        for c in ("electrode", "soz", "resected", "x", "y", "z", "space", "roi"):
            t[c] = info[c].reindex(t.index).values if c in info.columns else None
        t["onset_n"] = onset_n.reindex(t.index).values
        t["onset_known"] = onset_known.reindex(t.index).values
        t["onset_any"] = [(n > 0) if k > 0 else None for n, k in zip(t["onset_n"], t["onset_known"])]
        t = t.reset_index()
        t["contact"] = t["channel"].map(contact_number)

        measures = [m for m in MEASURES if m in t.columns and t[m].notna().any()]
        for m in measures:
            t[f"rank_{m}"] = t[m].rank(ascending=False, method="min")
        sort_key = measures[0] if measures else "channel"
        t = t.sort_values([sort_key, "channel"], ascending=[False, True], na_position="last", kind="mergesort")

        targets = []
        for lab in ("soz", "resected"):
            if t[lab].map(lambda v: v is True or v is False).any() and t[lab].eq(True).any():
                targets.append(lab)
        if not targets and t["onset_any"].eq(True).any():
            targets.append("onset_any")
        aucs = []
        for lab in targets:
            for m in measures:
                a, npos, nneg = S.auc(t[m], t[lab])
                aucs.append({"subject": subject, "measure": m, "label": lab, "auc": a, "n_positive": npos, "n_negative": nneg})
        spaces = sorted({s for s in t["space"].dropna().astype(str) if s})
        n_coords = int(t[["x", "y", "z"]].notna().all(axis=1).sum())
        notes = []
        ictal = [r for r in recs if r.is_ictal]
        if ictal:
            notes.append(f"{len(ictal)} of {len(recs)} recording(s) of this subject are seizure clips: the rates come from "
                         "their non-seizure part (mostly the minutes before the seizure; the upstream steps leave the "
                         "seizure and a margin out), which is peri-ictal, not a typical interictal sample.")
        subj = {
            "subject": subject, "notes": notes, "table": t, "measures": measures, "targets": targets, "aucs": aucs,
            "n_channels": len(t), "n_recordings": len([r for r in recs]) or int(t.filter(like="n_rec").max().max() or 0),
            "spaces": spaces, "n_coords": n_coords,
            "label_counts": {lab: int(t[lab].eq(True).sum()) for lab in ("soz", "resected", "onset_any")},
            "observations": _observations(subject, t, measures, targets, aucs),
        }
        subjects.append(subj)
        all_rows.append(t.assign(subject=subject))

    # cohort AUC summary per measure x label
    cohort = []
    allauc = pd.DataFrame([a for s in subjects for a in s["aucs"]])
    if not allauc.empty:
        for (m, lab), g in allauc.groupby(["measure", "label"], sort=False):
            d = S.describe(g["auc"])
            cohort.append({"measure": m, "label": lab, **d, "n_subjects": int(g["auc"].notna().sum()),
                           "n_above": int((g["auc"] > 0.5).sum())})
    return {"subjects": subjects, "available": available, "notes": notes, "cohort_auc": cohort,
            "measures": [m for m in MEASURES if m in available],
            "table": pd.concat(all_rows, ignore_index=True) if all_rows else None}


def _any(a, b):
    if a is True or b is True:
        return True
    if a is False or b is False:
        return False
    return None


def _observations(subject: str, t: pd.DataFrame, measures: list[str], targets: list[str], aucs: list[dict]) -> list[str]:
    obs = []
    for m in measures:
        name, unit, _ = MEASURES[m]
        v = t[m].dropna()
        if v.empty:
            continue
        top = t.dropna(subset=[m]).head(3) if m == measures[0] else t.dropna(subset=[m]).sort_values(m, ascending=False).head(3)
        tops = ", ".join(f"{c} ({x:.2f})" for c, x in zip(top["channel"], top[m]))
        obs.append(f"{name}: median {v.median():.2f} {unit} over {v.size} channels; highest {tops}.")
    for a in aucs:
        if a["auc"] is None:
            continue
        name = MEASURES[a["measure"]][0]
        a_ = a["auc"]
        word = ("clearly higher in" if a_ >= 0.7 else "somewhat higher in" if a_ >= 0.6 else "clearly lower in" if a_ <= 0.3
                else "somewhat lower in" if a_ <= 0.4 else "near chance at separating")
        obs.append(f"{name} is {word} {TARGETS[a['label']]} channels{'' if 'chance' in word else ' than in the others'} "
                   f"(AUC {a_:.2f}; {a['n_positive']} vs {a['n_negative']} channels).")
    return obs
