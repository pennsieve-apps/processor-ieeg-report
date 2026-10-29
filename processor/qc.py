"""
QC: per recording, the montage, channels kept, and the contacts/channels marked
bad or dropped with ieeg-prep's reason (qc.csv), plus bad channels of the
_channels.tsv files when qc.csv is not linked.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from processor.inputs import Inputs
from processor.study import Study


def analyse(inp: Inputs, study: Study) -> dict[str, Any] | None:
    qc = inp.table("qc.csv")
    if qc is None and not any(r.channels is not None for r in study.recordings.values()) and inp.recordings is None:
        return None
    prep = next((p for _, p in inp.provenances if p.get("app") == "processor-ieeg-prep" and p.get("details")), None)
    details = (prep or {}).get("details") or {}
    rows = []
    for rid, rec in sorted(study.recordings.items()):
        d = details.get(rid) or {}
        row: dict[str, Any] = {"recording_id": rid, "subject": rec.subject, "montage": rec.montage or d.get("montage") or "",
                               "sfreq": rec.sfreq, "duration_s": rec.duration_s, "n_channels": rec.n_channels,
                               "n_good": rec.n_good, "bad": [], "dropped": [], "notes": list(d.get("notes") or []),
                               "line_freq": d.get("line_freq"), "filters": d.get("filters"), "qc_figure": None,
                               "source_channels": d.get("source_channels")}
        if qc is not None:
            q = qc[qc["recording_id"] == rid]
            reason = q["reason"] if "reason" in q.columns else pd.Series([""] * len(q), index=q.index)
            for ch, status, why in zip(q["channel"], q["status"].astype(str).str.lower(), reason.fillna("")):
                if status == "bad":
                    row["bad"].append({"channel": ch, "reason": str(why)})
                elif status == "dropped":
                    row["dropped"].append({"channel": ch, "reason": str(why)})
            row["n_contacts"] = int(len(q))
        elif rec.channels is not None:
            b = rec.channels[rec.channels["status"] == "bad"]
            desc = b["status_description"] if "status_description" in b.columns else pd.Series([""] * len(b), index=b.index)
            row["bad"] = [{"channel": c, "reason": str(w) if pd.notna(w) else ""} for c, w in zip(b["channel"], desc)]
        rows.append(row)
    if not rows:
        return None
    reasons: dict[str, int] = {}
    for r in rows:
        for b in r["bad"]:
            key = _reason_class(b["reason"])
            reasons[key] = reasons.get(key, 0) + 1
    montages = sorted({r["montage"] for r in rows if r["montage"]})
    params = (prep or {}).get("parameters") or {}
    return {"rows": rows, "reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])), "montages": montages,
            "parameters": params, "has_qc_csv": qc is not None,
            "n_bad": sum(len(r["bad"]) for r in rows), "n_dropped": sum(len(r["dropped"]) for r in rows)}


def _reason_class(reason: str) -> str:
    r = (reason or "").lower()
    for key in ("line noise", "flat", "high line length", "amplitude", "clipped", "artifact", "artefact"):
        if key in r:
            return key
    return r.split("(")[0].strip() or "unspecified"


def table(qc: dict[str, Any]) -> pd.DataFrame:
    out = []
    for r in qc["rows"]:
        base = {k: r.get(k) for k in ("recording_id", "subject", "montage", "sfreq", "duration_s", "n_channels", "n_good")}
        if not r["bad"] and not r["dropped"]:
            out.append({**base, "channel": "", "status": "", "reason": ""})
        for b in r["bad"]:
            out.append({**base, "channel": b["channel"], "status": "bad", "reason": b["reason"]})
        for b in r["dropped"]:
            out.append({**base, "channel": b["channel"], "status": "dropped", "reason": b["reason"]})
    return pd.DataFrame(out)
