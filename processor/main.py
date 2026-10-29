"""
processor-ieeg-report: the last step of both epilepsy iEEG workflows
(Interictal Biomarker Mapping; Seizure Onset Localisation). It reads whatever
upstream outputs it is given and writes

  OUTPUT_DIR/report/index.html             cohort page: modes found, cohort summaries, QC, methods & citations
  OUTPUT_DIR/report/sub-<label>.html       one page per subject (channel table, map, strips, ROC; per seizure)
  OUTPUT_DIR/report/figures/*.png          their figures (own, plus ieeg-prep's QC plots)
  OUTPUT_DIR/report/provenance.json
  OUTPUT_DIR/tables/*.csv, metrics.json, provenance.json

Every input is optional; a section is rendered when its inputs are present. The
run fails only when none of the inputs is found.
"""
from __future__ import annotations

import json
import logging
import os
import re
import resource
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("processor-ieeg-report")
log.setLevel(logging.INFO)
for noisy in ("matplotlib", "PIL", "fontTools"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

APP_NAME = "processor-ieeg-report"
PARAMETERS = ("REPORT_TITLE", "TOP_K", "MAX_CHANNELS")
DEFAULT_TITLE = "Epilepsy iEEG Report"
REPO_ROOT = Path(__file__).resolve().parent.parent


def version_of(root: Path) -> str:
    for p in (root / "VERSION", Path("/processor/VERSION")):
        if p.is_file():
            return p.read_text().strip()
    return "unknown"


def tool_versions() -> dict[str, str]:
    import jinja2
    import matplotlib
    import numpy
    import pandas

    return {"python": sys.version.split()[0], "pandas": pandas.__version__, "numpy": numpy.__version__,
            "matplotlib": matplotlib.__version__, "jinja2": jinja2.__version__}


def int_param(name: str, default: int, lo: int, hi: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    v = int(float(raw))
    if not lo <= v <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}, got {raw}")
    return v


def _section(name: str, fn, errors: list[dict[str, str]], *args):
    """Run one section; a failing section is logged, reported on the page, and the rest goes on."""
    t0 = time.monotonic()
    try:
        result = fn(*args)
        log.info("section %s: %s (%.1fs)", name, "rendered" if result else "no inputs", time.monotonic() - t0)
        return result
    except Exception as exc:  # noqa: BLE001 - one broken input must not sink the report
        log.error("section %s FAILED: %s\n%s", name, exc, traceback.format_exc())
        errors.append({"section": name, "error": f"{type(exc).__name__}: {exc}"})
        return None


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s))


def methods(inp, own: dict[str, Any]) -> dict[str, Any]:
    from processor import citations as C

    runs: dict[str, list[dict[str, Any]]] = {}
    for path, prov in inp.provenances:
        app = str(prov.get("app"))
        entry = {"version": prov.get("version") or prov.get("appVersion") or "?", "parameters": prov.get("parameters") or {},
                 "tools": prov.get("tools") or {}, "path": inp.rel(path)}
        same = [r for r in runs.get(app, []) if r["version"] == entry["version"] and r["parameters"] == entry["parameters"]]
        if same:
            same[0].setdefault("paths", []).append(entry["path"])
            continue
        runs.setdefault(app, []).append(entry)
    runs.setdefault(APP_NAME, []).append({"version": own["version"], "parameters": own["parameters"], "tools": own["tools"],
                                          "path": "(this run)"})
    order = C.ORDER + sorted(a for a in runs if a not in C.ORDER)
    apps = []
    for app in order:
        if app not in runs:
            continue
        meta = C.APPS.get(app, {"step": "", "cite": []})
        apps.append({"app": app, "step": meta["step"], "runs": runs[app], "citations": [C.reference(k) for k in meta["cite"]]})
    return {"apps": apps}


def data_credit(inp, study) -> list[dict[str, str]]:
    from processor import citations as C

    text = json.dumps(inp.dataset_description or {})
    for _, p in inp.provenances:
        if p.get("app") == "processor-ieeg-prep":
            text += json.dumps(p.get("inputsFound") or p.get("inputs") or "")
    subjects = " ".join(study.subjects())
    out = []
    for doi, d in C.DATASETS.items():
        if doi in text or any(m in text for m in d["match"]) or (doi == "10.26275/lzhy-ox20" and "HUPatlas" in subjects):
            out.append({"doi": doi, "citation": d["citation"], "licence": d["licence"], "url": f"https://doi.org/{doi}"})
    if not out and inp.dataset_description:
        for s in inp.dataset_description.get("SourceDatasets") or []:
            if isinstance(s, dict) and s.get("Name"):
                out.append({"doi": str(s.get("DOI") or s.get("DatasetDOI") or ""), "citation": str(s["Name"]),
                            "licence": "", "url": ""})
    return out


def main() -> int:
    started = datetime.now(timezone.utc)
    t_start = time.monotonic()
    input_dir = os.environ.get("INPUT_DIR")
    output_dir = os.environ.get("OUTPUT_DIR")
    if not input_dir or not output_dir:
        log.error("INPUT_DIR and OUTPUT_DIR must be set")
        return 2
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if not input_dir.is_dir():
        log.error("INPUT_DIR %s is not a folder", input_dir)
        return 2
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

    title = os.environ.get("REPORT_TITLE") or DEFAULT_TITLE
    try:
        top_k = int_param("TOP_K", 10, 1, 200)
        max_channels = int_param("MAX_CHANNELS", 30, 5, 500)
    except ValueError as exc:
        log.error("bad parameter: %s", exc)
        return 2
    parameters = {"REPORT_TITLE": title, "TOP_K": top_k, "MAX_CHANNELS": max_channels}

    from processor import figures as F, inputs as I, interictal as II, qc as Q, report as R, seizure as SZ, study as ST
    from processor.stats import clean

    inp = I.gather(input_dir)
    for port in I.PORTS:
        files = inp.found.get(port, [])
        log.info("input %s: %d file(s)%s", port, len(files),
                 (": " + ", ".join(inp.rel(f) for f in files[:5]) + (" …" if len(files) > 5 else "")) if files else "")
    if not inp.has_any:
        listing = [inp.rel(p) for p in inp.files]
        log.error("none of the expected inputs was found (recordings.csv, *_channels.tsv, qc.csv, spike_rates.csv, "
                  "bandpower.csv, hfo_rates.csv, channel_abnormality.csv, seizure_onsets.csv, channel_onsets.csv, ei.csv, "
                  "fragility.csv, onset_zone.csv, scores.csv); INPUT_DIR holds %d file(s): %s", len(listing),
                  ", ".join(listing[:40]) + (" …" if len(listing) > 40 else ""))
        return 1

    report_dir, tables_dir = output_dir / "report", output_dir / "tables"
    fig_dir = report_dir / "figures"
    for d in (report_dir, tables_dir, fig_dir):
        d.mkdir(parents=True, exist_ok=True)

    errors: list[dict[str, str]] = []
    study = ST.build(inp)
    log.info("study: %d subject(s), %d recording(s); labels known: %s", len(study.subjects()), len(study.recordings),
             ", ".join(sorted(study.labels_known())) or "none")

    qc = _section("qc", Q.analyse, errors, inp, study)
    if qc:
        for r in qc["rows"]:
            src = inp.qc_figures.get(r["recording_id"])
            if src is not None:
                name = f"qc_{safe_name(r['recording_id'])}.png"
                shutil.copyfile(src, fig_dir / name)
                r["qc_figure"] = name

    ii = _section("interictal", II.analyse, errors, inp, study)
    names = {k: f"{v[0]} ({v[1]})" for k, v in II.MEASURES.items()}
    if ii and ii.get("subjects"):
        for s in ii["subjects"]:
            stem = safe_name(s["subject"])
            t, ms = s["table"], s["measures"]
            s["fig_map"] = _section(f"map {s['subject']}", F.channel_map, errors, t, ms, names,
                                    ", ".join(s["spaces"]), fig_dir / f"map_{stem}.png")
            strip = [m for m in ms if m in ("spike_rate", "ripple_rate", "fast_ripple_rate")]
            s["fig_strips"] = _section(f"strips {s['subject']}", F.electrode_strips, errors, t, strip, names,
                                       fig_dir / f"strips_{stem}.png")
            s["fig_roc"] = _section(f"roc {s['subject']}", F.roc_curves, errors, t, ms, s["targets"], names, II.TARGETS,
                                    fig_dir / f"roc_{stem}.png")
        import pandas as pd
        allauc = pd.DataFrame([a for s in ii["subjects"] for a in s["aucs"]])
        ii["fig_cohort_auc"] = (_section("cohort auc", F.cohort_auc, errors, allauc, names, II.TARGETS, fig_dir / "cohort_auc.png")
                                if not allauc.empty else None)

    sz = _section("seizures", SZ.analyse, errors, inp, study, top_k)
    if sz:
        st = inp.table("channel_scores.csv")
        for s in sz["seizures"]:
            scores_time = st[st["recording_id"] == s["recording_id"]] if st is not None else None
            s["figure"] = _section(f"seizure {s['recording_id']}", F.seizure_overview, errors, s, scores_time, max_channels,
                                   fig_dir / f"seizure_{safe_name(s['recording_id'])}.png")
            s["heatmap"] = scores_time is not None and not scores_time.empty
        sz["fig_errors"] = _section("onset errors", F.onset_errors, errors, sz["seizures"], fig_dir / "onset_errors.png")
        sz["fig_aucs"] = _section("seizure aucs", F.seizure_aucs, errors, sz["seizures"], sz["methods"], fig_dir / "seizure_aucs.png")

    app_version = version_of(REPO_ROOT)
    tools = tool_versions()
    own = {"app": APP_NAME, "version": app_version, "tools": tools, "parameters": parameters}
    meth = _section("methods", methods, errors, inp, own) or {"apps": []}
    credit = _section("data credit", data_credit, errors, inp, study) or []

    modes = []
    if ii and ii.get("subjects"):
        modes.append("Interictal Biomarker Mapping")
    if sz:
        modes.append("Seizure Onset Localisation")
    ctx = {"title": title, "generated_at": started.isoformat(timespec="seconds"), "app_version": app_version,
           "tools": tools, "parameters": parameters, "study": study, "qc": qc, "ii": ii, "sz": sz, "methods": meth,
           "credit": credit, "errors": errors, "modes": modes, "names": names, "measures_info": II.MEASURES,
           "what_ii": II.WHAT_IT_TELLS, "what_sz": SZ.WHAT_IT_TELLS, "targets": II.TARGETS, "method_names": SZ.METHODS,
           "top_k": top_k, "max_channels": max_channels,
           "inputs_found": {k: len(v) for k, v in inp.found.items()}}
    pages = R.write_pages(report_dir, ctx)

    written = R.write_tables(tables_dir, ctx)
    metrics = R.metrics_json(ctx)
    with open(tables_dir / "metrics.json", "w") as fh:
        json.dump(clean(metrics), fh, indent=2)
    written.append("metrics.json")

    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024)
    provenance = {
        "app": APP_NAME, "version": app_version, "tools": tools, "parameters": parameters,
        "startedAt": ctx["generated_at"], "finishedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": round(time.monotonic() - t_start, 2), "peakRssMB": round(peak_mb, 1),
        "runtime": "lambda" if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else "container",
        "inputsFound": {k: [inp.rel(p) for p in v] for k, v in inp.found.items()},
        "provenanceFiles": [inp.rel(p) for p, _ in inp.provenances],
        "modes": modes, "subjects": study.subjects(), "recordings": len(study.recordings),
        "studyNotes": study.notes,
        "sections": {"qc": bool(qc), "interictal": bool(ii and ii.get("subjects")), "seizures": bool(sz)},
        "sectionErrors": errors,
        "outputs": {"report": sorted(str(p.relative_to(report_dir)) for p in report_dir.rglob("*") if p.is_file())
                    + ["provenance.json"], "tables": written + ["provenance.json"]},
    }
    for d in (report_dir, tables_dir):
        with open(d / "provenance.json", "w") as fh:
            json.dump(clean(provenance), fh, indent=2)
    log.info("wrote %d page(s) (%s), %d table(s), %d section error(s) in %.1fs, peak RSS %.0f MB", len(pages),
             ", ".join(modes) or "no analysis section", len(written), len(errors), time.monotonic() - t_start, peak_mb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
