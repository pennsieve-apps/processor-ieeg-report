"""
Seizure Onset Localisation: per seizure (recording), the detected onset against
the expert onset, each method's channel ranking (DynaSD, EI, fragility) and the
consensus onset zone, agreement between methods, and scores against the expert
onset channels. Scores come from seizure-consensus's scores.csv when it is
linked; the report computes the same metrics itself (AUC, top-k precision and
recall, onset error) when it is not.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from processor import stats as S
from processor.inputs import Inputs, to_bool
from processor.study import Recording, Study, channel_frame

METHODS = {"dynasd": "DynaSD", "ei": "EI", "fragility": "Fragility", "consensus": "Consensus"}

WHAT_IT_TELLS = {
    "dynasd": ("DynaSD (Ojemann et al. 2026) learns each channel's baseline dynamics and scores how far the signal departs "
               "from them; it gives a seizure onset time and, per channel, when it was recruited. Early, strong departure "
               "is a property of the recorded signal, not proof that the tissue generated the seizure."),
    "ei": ("The Epileptogenicity Index (Bartolomei et al. 2008) combines how much fast activity a channel gains and how "
           "early. It was built for SEEG seizures with low-voltage fast activity and is less informative for seizures "
           "starting with other patterns (e.g. rhythmic spikes or slow waves)."),
    "fragility": ("Neural fragility (Li et al. 2021) measures how small a change to a channel's linear model would make the "
                  "network unstable. It is a model property of the recording window and depends on window and "
                  "regularisation choices."),
    "consensus": ("The consensus (seizure-consensus) fuses the methods' ranks. Agreement between methods that use related "
                  "signal features is not independent confirmation."),
}


def dynasd_order(z: pd.DataFrame) -> pd.Series:
    """DynaSD's channel order as seizure-consensus ranks it: recruited channels first
    (a channel with an onset counts as recruited when the column is missing), by
    onset (earliest first), ties by score (highest first); then the others by score.
    Returned as a 'higher = more onset-like' key (minus the rank, ties shared)."""
    onset = pd.to_numeric(z.get("dynasd_onset_s"), errors="coerce") if "dynasd_onset_s" in z.columns else pd.Series(np.nan, index=z.index)
    score = pd.to_numeric(z.get("dynasd_score"), errors="coerce") if "dynasd_score" in z.columns else pd.Series(np.nan, index=z.index)
    if "dynasd_recruited" in z.columns and z["dynasd_recruited"].notna().any():
        rec = z["dynasd_recruited"].eq(True)
    else:
        rec = onset.notna()
    if not (onset.notna().any() or score.notna().any()):
        return pd.Series(np.nan, index=z.index)
    k1 = (~rec).astype(int)
    k2 = onset.where(rec, np.inf).fillna(np.inf)
    k3 = (-score).fillna(np.inf)
    keys = list(zip(k1, k2, k3))
    order = sorted(range(len(keys)), key=lambda i: keys[i])
    rank = np.empty(len(keys))
    for pos, i in enumerate(order):
        rank[i] = pos + 1 if pos == 0 or keys[i] != keys[order[pos - 1]] else rank[order[pos - 1]]
    return pd.Series(-rank, index=z.index)


def _score_columns(z: pd.DataFrame) -> dict[str, str]:
    """method -> column in z holding a 'higher = more onset-like' score."""
    out = {}
    if "dynasd_key" in z.columns and z["dynasd_key"].notna().any():
        out["dynasd"] = "dynasd_key"
    if "ei" in z.columns and z["ei"].notna().any():
        out["ei"] = "ei"
    if "fragility" in z.columns and z["fragility"].notna().any():
        out["fragility"] = "fragility"
    if "consensus_score" in z.columns and z["consensus_score"].notna().any():
        out["consensus"] = "consensus_score"
    return out


def _channel_table(inp: Inputs, rec: Recording) -> pd.DataFrame | None:
    rid = rec.recording_id
    parts = []
    co = inp.table("channel_onsets.csv")
    if co is not None:
        c = co[co["recording_id"] == rid]
        if "method" in c.columns and c["method"].nunique() > 1:
            c = c[c["method"] == c["method"].iloc[0]]
        if not c.empty:
            c = c.drop_duplicates("channel")
            d = pd.DataFrame({"channel": c["channel"], "dynasd_onset_s": pd.to_numeric(c["onset_s"], errors="coerce"),
                              "dynasd_recruited": c["recruited"].map(to_bool) if "recruited" in c.columns else None,
                              "dynasd_score": pd.to_numeric(c["score"], errors="coerce") if "score" in c.columns else np.nan})
            parts.append(d)
    ei = inp.table("ei.csv")
    if ei is not None:
        e = ei[ei["recording_id"] == rid].drop_duplicates("channel")
        if not e.empty:
            parts.append(pd.DataFrame({"channel": e["channel"], "ei": pd.to_numeric(e["ei"], errors="coerce"),
                                       "ei_detection_s": pd.to_numeric(e.get("detection_s"), errors="coerce") if "detection_s" in e.columns else np.nan}))
    fr = inp.table("fragility.csv")
    if fr is not None:
        f = fr[fr["recording_id"] == rid].drop_duplicates("channel")
        if not f.empty:
            if "fragility_post" in f.columns:
                val = pd.to_numeric(f["fragility_post"], errors="coerce")
            elif "fragility_pre" in f.columns:
                val = pd.to_numeric(f["fragility_pre"], errors="coerce")
            else:
                val = -pd.to_numeric(f["rank"], errors="coerce")
            parts.append(pd.DataFrame({"channel": f["channel"], "fragility": val,
                                       "fragility_rank_in": pd.to_numeric(f["rank"], errors="coerce") if "rank" in f.columns else np.nan}))
    oz = inp.table("onset_zone.csv")
    if oz is not None:
        o = oz[oz["recording_id"] == rid].drop_duplicates("channel")
        if not o.empty:
            keep = ["channel"] + [c for c in ("consensus_score", "rank", "in_onset_zone", "n_methods", "expert_onset",
                                               "dynasd_score", "ei", "fragility", "dynasd_onset_s", "dynasd_recruited")
                                  if c in o.columns]
            o = o[keep].copy()
            o["in_onset_zone"] = o["in_onset_zone"].map(to_bool) if "in_onset_zone" in o.columns else None
            if "expert_onset" in o.columns:
                o["expert_onset"] = o["expert_onset"].map(to_bool)
            if "consensus_score" not in o.columns:
                o["consensus_score"] = -pd.to_numeric(o["rank"], errors="coerce")
            o = o.rename(columns={"rank": "consensus_rank"})
            parts.append(o)
    if not parts:
        return None
    z = parts[0]
    for p in parts[1:]:
        dup = [c for c in p.columns if c != "channel" and c in z.columns]
        # The method's own table wins over the copy in onset_zone.csv.
        z = z.merge(p.drop(columns=dup), on="channel", how="outer") if dup else z.merge(p, on="channel", how="outer")
    z["dynasd_key"] = dynasd_order(z)
    info = channel_frame(rec, list(z["channel"]))
    z = z.merge(info, on="channel", how="left")
    if "expert_onset" in z.columns:
        z["onset"] = [a if a is not None else b for a, b in zip(z["onset"], z["expert_onset"])]
    return z


def _detected(inp: Inputs, rec: Recording, z: pd.DataFrame | None) -> tuple[float | None, str]:
    so = inp.table("seizure_onsets.csv")
    if so is not None:
        s = so[so["recording_id"] == rec.recording_id]
        v = pd.to_numeric(s["onset_s"], errors="coerce").dropna()
        if not v.empty:
            return float(v.min()), str(s["method"].iloc[0]) if "method" in s.columns else "dynasd"
    if z is not None and "dynasd_onset_s" in z.columns:
        rec_ = z[z.get("dynasd_recruited", pd.Series(dtype=object)).eq(True)] if "dynasd_recruited" in z.columns else z
        v = pd.to_numeric(rec_["dynasd_onset_s"], errors="coerce").dropna()
        if not v.empty:
            return float(v.min()), "earliest recruited channel (channel_onsets.csv)"
    return None, ""


def _scores_from_table(inp: Inputs, rid: str) -> pd.DataFrame | None:
    sc = inp.table("scores.csv")
    if sc is None:
        return None
    s = sc[sc["recording_id"] == rid]
    return s if not s.empty else None


def analyse(inp: Inputs, study: Study, top_k: int) -> dict[str, Any] | None:
    have = [n for n in ("seizure_onsets.csv", "channel_onsets.csv", "ei.csv", "fragility.csv", "onset_zone.csv", "scores.csv")
            if inp.table(n) is not None]
    if not have:
        return None
    rids = set()
    for n in have:
        rids |= set(inp.table(n)["recording_id"].astype(str))
    rids -= {"ALL", "all"}
    seizures = []
    for rid in sorted(rids):
        rec = study.recordings.get(rid)
        if rec is None:
            continue
        z = _channel_table(inp, rec)
        detected, det_src = _detected(inp, rec, z)
        sz: dict[str, Any] = {"recording_id": rid, "subject": rec.subject, "task": rec.task, "expert_onset_s": rec.onset_s,
                              "seizure_end_s": rec.seizure_end_s, "detected_onset_s": detected, "detected_source": det_src,
                              "onset_error_s": (detected - rec.onset_s) if detected is not None and rec.onset_s is not None else None,
                              "stim_induced": rec.stim_induced, "stim_source": rec.stim_source, "lvfa": rec.lvfa,
                              "duration_s": rec.duration_s, "methods": [], "table": None, "agreement": [], "scores": [],
                              "n_channels": 0, "n_expert_onset": 0}
        if z is not None:
            cols = _score_columns(z)
            sz["methods"] = [m for m in METHODS if m in cols]
            for m, c in cols.items():
                z[f"rank_{m}"] = z[c].rank(ascending=False, method="min")
            order = "rank_consensus" if "consensus" in cols else (f"rank_{sz['methods'][0]}" if sz["methods"] else "channel")
            z = z.sort_values([order, "channel"], na_position="last", kind="mergesort").reset_index(drop=True)
            sz["table"] = z
            sz["n_channels"] = len(z)
            labelled = z["onset"].map(lambda v: v is True or v is False)
            sz["n_expert_onset"] = int(z["onset"].eq(True).sum())
            sz["labelled"] = bool(labelled.any() and z["onset"].eq(True).any())
            # agreement between methods (consensus excluded: it is built from the others)
            base = [m for m in sz["methods"] if m != "consensus"]
            for i, a in enumerate(base):
                for b in base[i + 1:]:
                    rho, n = S.spearman(z[cols[a]], z[cols[b]])
                    ta = S.top_k(z.set_index("channel")[cols[a]], top_k)
                    tb = S.top_k(z.set_index("channel")[cols[b]], top_k)
                    sz["agreement"].append({"a": a, "b": b, "spearman": rho, "n": n, "top_k_overlap": S.overlap(ta, tb),
                                            "k": min(top_k, len(ta), len(tb))})
            if "in_onset_zone" in z.columns and z["in_onset_zone"].notna().any():
                sz["zone"] = list(z.loc[z["in_onset_zone"].eq(True), "channel"])
                sz["zone_source"] = "seizure-consensus (in_onset_zone)"
            else:
                m0 = "consensus" if "consensus" in cols else (base[0] if base else None)
                sz["zone"] = list(z.dropna(subset=[cols[m0]]).sort_values(cols[m0], ascending=False)["channel"][:top_k]) if m0 else []
                sz["zone_source"] = f"top {top_k} by {METHODS.get(m0, m0)} (no seizure-consensus output)" if m0 else ""
            # scores
            table_scores = _scores_from_table(inp, rid)
            sz["scores_source"] = "seizure-consensus scores.csv" if table_scores is not None else "computed by this report"
            for m in sz["methods"]:
                row = {"method": m}
                if table_scores is not None and (table_scores["method"] == m).any():
                    t = table_scores[table_scores["method"] == m].set_index("metric")["value"]
                    for k in ("auc", "precision", "recall", "f1", "r_precision", "n_selected"):
                        row[k] = float(t[k]) if k in t.index and pd.notna(pd.to_numeric(t[k], errors="coerce")) else None
                elif sz["labelled"]:
                    a, npos, nneg = S.auc(z[cols[m]], z["onset"])
                    row["auc"] = a
                    sel = (S.top_k(z.set_index("channel")[cols[m]], top_k) if m != "consensus" or not sz.get("zone")
                           else set(sz["zone"]))
                    pos = set(z.loc[z["onset"].eq(True), "channel"])
                    lab = set(z.loc[labelled, "channel"])
                    sel_l = sel & lab
                    row["precision"] = len(sel_l & pos) / len(sel_l) if sel_l else None
                    row["recall"] = len(sel & pos) / len(pos) if pos else None
                    p, r = row["precision"], row["recall"]
                    row["f1"] = 2 * p * r / (p + r) if p and r else (0.0 if p == 0 or r == 0 else None)
                    npos_ = len(pos)
                    topn = S.top_k(z.set_index("channel")[cols[m]], npos_)
                    row["r_precision"] = len(topn & pos) / npos_ if npos_ else None
                    row["n_selected"] = len(sel)
                if any(row.get(k) is not None for k in ("auc", "precision", "recall")):
                    sz["scores"].append(row)
            if table_scores is not None:
                t = table_scores[table_scores["method"].astype(str).str.startswith("dynasd")].set_index("metric")["value"]
                for k in ("event_tp",):
                    if k in t.index:
                        sz["event_tp"] = to_bool(t[k])
        seizures.append(sz)
    if not seizures:
        return None
    cohort = _cohort(seizures)
    return {"seizures": seizures, "patients": _patients(seizures), "cohort": cohort,
            "observations": _observations(seizures, cohort, top_k),
            "has_expert": any(s.get("labelled") for s in seizures),
            "stim_source": sorted({s["stim_source"] for s in seizures if s["stim_source"]}),
            "lvfa_known": any(s["lvfa"] is not None for s in seizures), "top_k": top_k,
            "methods": [m for m in METHODS if any(m in s["methods"] for s in seizures)]}


def _metric(s: dict, method: str, key: str):
    for r in s["scores"]:
        if r["method"] == method:
            return r.get(key)
    return None


def _group_row(members: list[dict], **keys) -> dict[str, Any]:
    row = dict(keys)
    row["n_seizures"] = len(members)
    for m in METHODS:
        d = S.describe([_metric(s, m, "auc") for s in members])
        row[f"{m}_auc_median"] = d["median"]
        row[f"{m}_auc_n"] = d["n"]
        row[f"{m}_r_precision_median"] = S.describe([_metric(s, m, "r_precision") for s in members])["median"]
    err = S.describe([abs(s["onset_error_s"]) for s in members if s["onset_error_s"] is not None])
    row["abs_onset_error_median_s"] = err["median"]
    row["abs_onset_error_n"] = err["n"]
    row["onset_error_median_s"] = S.describe([s["onset_error_s"] for s in members if s["onset_error_s"] is not None])["median"]
    tps = [s.get("event_tp") for s in members if s.get("event_tp") is not None]
    row["detected_within_tolerance"] = f"{sum(tps)}/{len(tps)}" if tps else None
    return row


def _kind(s: dict) -> str:
    return "stimulation-induced" if s["stim_induced"] is True else "spontaneous" if s["stim_induced"] is False else "unknown"


def _patients(seizures: list[dict]) -> list[dict]:
    rows = []
    for subject in sorted({s["subject"] for s in seizures}):
        g = [s for s in seizures if s["subject"] == subject]
        rows.append(_group_row(g, subject=subject, group="all"))
        kinds = sorted({_kind(s) for s in g})
        if len(kinds) > 1 or kinds != ["unknown"]:
            for k in kinds:
                rows.append(_group_row([s for s in g if _kind(s) == k], subject=subject, group=k))
        if any(s["lvfa"] is not None for s in g):
            for v, name in ((True, "LVFA"), (False, "no LVFA")):
                gg = [s for s in g if s["lvfa"] is v]
                if gg:
                    rows.append(_group_row(gg, subject=subject, group=name))
    return rows


def _cohort(seizures: list[dict]) -> list[dict]:
    rows = [_group_row(seizures, group="all seizures")]
    kinds = sorted({_kind(s) for s in seizures})
    if kinds != ["unknown"]:
        for k in kinds:
            rows.append(_group_row([s for s in seizures if _kind(s) == k], group=k))
    if any(s["lvfa"] is not None for s in seizures):
        for v, name in ((True, "LVFA"), (False, "no LVFA"), (None, "LVFA unknown")):
            gg = [s for s in seizures if s["lvfa"] is v]
            if gg:
                rows.append(_group_row(gg, group=name))
    return rows


def _observations(seizures: list[dict], cohort: list[dict], top_k: int) -> list[str]:
    obs = []
    allrow = cohort[0]
    aucs = [(METHODS[m], allrow.get(f"{m}_auc_median"), allrow.get(f"{m}_auc_n")) for m in METHODS]
    aucs = [(n, a, k) for n, a, k in aucs if a is not None]
    if aucs:
        obs.append("Median AUC against the expert onset channels: " + ", ".join(f"{n} {a:.2f} ({k} seizures)" for n, a, k in aucs) + ".")
    if allrow.get("abs_onset_error_median_s") is not None:
        obs.append(f"Detected onset vs expert onset: median absolute difference {allrow['abs_onset_error_median_s']:.1f} s, "
                   f"median signed difference {allrow['onset_error_median_s']:+.1f} s over {allrow['abs_onset_error_n']} seizures.")
    by = {r["group"]: r for r in cohort}
    st, sp = by.get("stimulation-induced"), by.get("spontaneous")
    if st and sp and st.get("onset_error_median_s") is not None and sp.get("abs_onset_error_median_s") is not None:
        if st["onset_error_median_s"] < 0 and abs(st["onset_error_median_s"]) > 2 * max(sp["abs_onset_error_median_s"], 1.0):
            obs.append(f"In stimulation-induced seizures the detected onset lies a median {abs(st['onset_error_median_s']):.1f} s "
                       f"before the expert onset (spontaneous: {sp['abs_onset_error_median_s']:.1f} s either way). The stimulation "
                       "itself, or its artefact, may be what the detector responds to; check those onsets by eye.")
    rhos = {}
    for s in seizures:
        for a in s["agreement"]:
            rhos.setdefault((a["a"], a["b"]), []).append((a["spearman"], a["top_k_overlap"]))
    if rhos:
        parts = []
        for (a, b), v in rhos.items():
            r = S.describe([x for x, _ in v])["median"]
            o = S.describe([y for _, y in v])["median"]
            if r is not None:
                parts.append(f"{METHODS[a]}–{METHODS[b]} ρ {r:.2f}, top-{top_k} overlap {o:.0%}" if o is not None else
                             f"{METHODS[a]}–{METHODS[b]} ρ {r:.2f}")
        if parts:
            obs.append("Agreement between methods over all channels (median per seizure): " + "; ".join(parts) + ". "
                       "Methods can each rank the expert channels near the top while ordering the remaining channels very "
                       "differently, so low rank correlation over all channels does not contradict high AUCs.")
    return obs
