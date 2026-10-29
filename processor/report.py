"""
The HTML pages (Jinja2, inline CSS, no scripts, no external resources: they open
offline from a dataset folder), the summary tables and metrics.json.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from processor import qc as Q
from processor import stats as S

TEMPLATES = Path(__file__).parent / "templates"


def page_name(subject: str) -> str:
    from processor.main import safe_name
    return f"sub-{safe_name(subject)}.html"


def _yn(v: Any) -> str:
    return "yes" if v is True else "no" if v is False else ""


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["num"] = S.num
    env.filters["yn"] = _yn
    env.filters["sec"] = lambda v, d=1: "–" if v is None else f"{float(v):+.{d}f} s"
    env.filters["pct"] = lambda v: "–" if v is None else f"{100 * float(v):.0f}%"
    env.filters["extract"] = lambda key, mapping: mapping.get(key)
    env.globals["page_name"] = page_name
    return env


def channel_rows(s: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    t = s["table"].head(limit)
    rows = []
    for _, r in t.iterrows():
        row = {"channel": r["channel"], "electrode": r.get("electrode") or "", "roi": r.get("roi") or "",
               "soz": r.get("soz"), "resected": r.get("resected"),
               "onset": (f"{int(r['onset_n'])}/{int(r['onset_known'])}" if r.get("onset_known") else ""),
               "values": {m: (None if pd.isna(r.get(m)) else float(r[m])) for m in s["measures"]},
               "ranks": {m: (None if pd.isna(r.get(f"rank_{m}")) else int(r[f"rank_{m}"])) for m in s["measures"]}}
        rows.append(row)
    return rows


def seizure_rows(sz: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    z = sz.get("table")
    if z is None:
        return []
    rows = []
    zone = set(sz.get("zone") or [])
    for _, r in z.head(limit).iterrows():
        rows.append({"channel": r["channel"], "roi": r.get("roi") or "", "expert": r.get("onset"), "zone": r["channel"] in zone,
                     "dynasd_onset_s": None if pd.isna(r.get("dynasd_onset_s", float("nan"))) else float(r["dynasd_onset_s"]),
                     "ranks": {m: (None if pd.isna(r.get(f"rank_{m}", float("nan"))) else int(r[f"rank_{m}"])) for m in sz["methods"]}})
    return rows


def write_pages(report_dir: Path, ctx: dict[str, Any]) -> list[Path]:
    env = environment()
    study = ctx["study"]
    ii, sz, qc = ctx.get("ii"), ctx.get("sz"), ctx.get("qc")
    ii_by = {s["subject"]: s for s in (ii or {}).get("subjects", [])}
    for s in ii_by.values():
        s["rows"] = channel_rows(s, ctx["max_channels"])
    sz_by: dict[str, list[dict]] = {}
    for s in (sz or {}).get("seizures", []):
        s["rows"] = seizure_rows(s, ctx["max_channels"])
        sz_by.setdefault(s["subject"], []).append(s)
    qc_by: dict[str, list[dict]] = {}
    for r in (qc or {}).get("rows", []):
        qc_by.setdefault(r["subject"], []).append(r)
    subjects = sorted(set(ii_by) | set(sz_by) | set(qc_by) | set(study.subjects()))
    summary = []
    for subj in subjects:
        recs = study.of_subject(subj)
        summary.append({"subject": subj, "page": page_name(subj), "n_recordings": len(recs),
                        "n_seizures": len(sz_by.get(subj, [])), "ii": ii_by.get(subj), "seizures": sz_by.get(subj, []),
                        "qc": qc_by.get(subj, []),
                        "labels": sorted({lab for r in recs if r.channels is not None for lab in ("soz", "resected", "onset")
                                          if r.channels[lab].notna().any()})})
    ctx = dict(ctx, subjects=summary)
    pages = []
    page = report_dir / "index.html"
    page.write_text(env.get_template("index.html.j2").render(**ctx), encoding="utf-8")
    pages.append(page)
    tpl = env.get_template("subject.html.j2")
    for s in summary:
        p = report_dir / s["page"]
        p.write_text(tpl.render(**ctx, s=s), encoding="utf-8")
        pages.append(p)
    return pages


def _csv(df: pd.DataFrame, path: Path) -> None:
    df = df.copy()
    for c in df.columns:
        col = df[c]
        if c.startswith("rank_") or c in ("n", "k", "n_positive", "n_negative"):
            df[c] = pd.to_numeric(col, errors="coerce").round().astype("Int64")
        elif pd.api.types.is_float_dtype(col):
            df[c] = col.round(4)
        elif col.map(lambda v: v is None or isinstance(v, bool) or (isinstance(v, float) and pd.isna(v))).all():
            df[c] = col.map(lambda v: "true" if v is True else "false" if v is False else "")
    df.to_csv(path, index=False)


def write_tables(tables_dir: Path, ctx: dict[str, Any]) -> list[str]:
    written = []
    ii, sz, qc = ctx.get("ii"), ctx.get("sz"), ctx.get("qc")
    if ii and ii.get("table") is not None:
        t = ii["table"].copy()
        cols = ["subject", "channel", "electrode", "roi", "x", "y", "z", "space", "soz", "resected", "onset_n", "onset_known",
                *[m for m in ("spike_rate", "ripple_rate", "fast_ripple_rate", "max_abs_z") if m in t.columns],
                *[f"rank_{m}" for m in ("spike_rate", "ripple_rate", "fast_ripple_rate", "max_abs_z") if f"rank_{m}" in t.columns]]
        t = t[[c for c in cols if c in t.columns]]
        for c in ("soz", "resected"):
            t[c] = t[c].map(lambda v: "true" if v is True else "false" if v is False else "")
        _csv(t, tables_dir / "interictal_channels.csv")
        written.append("interictal_channels.csv")
        aucs = pd.DataFrame([a for s in ii["subjects"] for a in s["aucs"]],
                            columns=["subject", "measure", "label", "auc", "n_positive", "n_negative"])
        _csv(aucs, tables_dir / "interictal_auc.csv")
        written.append("interictal_auc.csv")
    if sz:
        on, ch, sc, ag = [], [], [], []
        for s in sz["seizures"]:
            on.append({k: s.get(k) for k in ("recording_id", "subject", "task", "expert_onset_s", "detected_onset_s",
                                              "onset_error_s", "detected_source", "stim_induced", "stim_source", "lvfa",
                                              "n_channels", "n_expert_onset")} | {"onset_zone": "|".join(s.get("zone") or []),
                                                                                 "onset_zone_source": s.get("zone_source", "")})
            z = s.get("table")
            if z is not None:
                keep = ["channel", "electrode", "roi", "onset", "dynasd_onset_s", "dynasd_recruited", "dynasd_score", "ei",
                        "fragility", "consensus_score", *[f"rank_{m}" for m in s["methods"]]]
                zz = z[[c for c in keep if c in z.columns]].copy()
                zz.insert(0, "recording_id", s["recording_id"])
                zz["in_onset_zone"] = zz["channel"].isin(set(s.get("zone") or []))
                zz = zz.rename(columns={"onset": "expert_onset"})
                ch.append(zz)
            for r in s["scores"]:
                for k, v in r.items():
                    if k != "method" and v is not None:
                        sc.append({"recording_id": s["recording_id"], "method": r["method"], "metric": k, "value": v,
                                   "source": s.get("scores_source", "")})
            if s["onset_error_s"] is not None:
                sc.append({"recording_id": s["recording_id"], "method": "dynasd", "metric": "onset_error_s",
                           "value": s["onset_error_s"], "source": "computed by this report"})
            for a in s["agreement"]:
                ag.append({"recording_id": s["recording_id"], **a})
        _csv(pd.DataFrame(on), tables_dir / "seizure_onsets.csv")
        written.append("seizure_onsets.csv")
        if ch:
            _csv(pd.concat(ch, ignore_index=True), tables_dir / "seizure_channels.csv")
            written.append("seizure_channels.csv")
        _csv(pd.DataFrame(sc, columns=["recording_id", "method", "metric", "value", "source"]), tables_dir / "seizure_scores.csv")
        written.append("seizure_scores.csv")
        _csv(pd.DataFrame(ag, columns=["recording_id", "a", "b", "spearman", "n", "top_k_overlap", "k"]),
             tables_dir / "method_agreement.csv")
        written.append("method_agreement.csv")
        _csv(pd.DataFrame(sz["patients"]), tables_dir / "patient_summary.csv")
        written.append("patient_summary.csv")
    if qc:
        _csv(Q.table(qc), tables_dir / "qc_channels.csv")
        written.append("qc_channels.csv")
    return written


def metrics_json(ctx: dict[str, Any]) -> dict[str, Any]:
    ii, sz, qc = ctx.get("ii"), ctx.get("sz"), ctx.get("qc")
    out: dict[str, Any] = {"app": "processor-ieeg-report", "appVersion": ctx["app_version"], "generatedAt": ctx["generated_at"],
                           "title": ctx["title"], "modes": ctx["modes"], "sectionErrors": ctx["errors"],
                           "subjects": [s["subject"] for s in ctx.get("subjects", [])]}
    if ii:
        out["interictal"] = {"available": ii.get("available"), "notes": ii.get("notes"), "cohortAuc": ii.get("cohort_auc"),
                             "subjects": [{k: s[k] for k in ("subject", "measures", "targets", "aucs", "n_channels",
                                                             "label_counts", "spaces", "observations")} for s in ii["subjects"]]}
    if sz:
        out["seizures"] = {"cohort": sz["cohort"], "observations": sz.get("observations"), "patients": sz["patients"], "topK": sz["top_k"],
                           "perSeizure": [{k: s.get(k) for k in ("recording_id", "subject", "expert_onset_s", "detected_onset_s",
                                                                  "onset_error_s", "stim_induced", "stim_source", "lvfa",
                                                                  "methods", "zone", "zone_source", "scores", "scores_source",
                                                                  "agreement", "n_expert_onset")} for s in sz["seizures"]]}
    if qc:
        out["qc"] = {"montages": qc["montages"], "reasons": qc["reasons"], "n_bad": qc["n_bad"], "n_dropped": qc["n_dropped"]}
    out["methods"] = [{"app": a["app"], "versions": [r["version"] for r in a["runs"]], "citations": [c["doi"] for c in a["citations"]]}
                      for a in ctx["methods"]["apps"]]
    out["inputData"] = ctx["credit"]
    return out
