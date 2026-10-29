"""
A tiny synthetic set of upstream outputs that follows conventions.md: two
subjects, one with two seizures (one spontaneous with LVFA, one
stimulation-induced) and one interictal recording; every table of every step,
including seizure-fragility and seizure-consensus, plus the optional DynaSD
scores over time. Labelled channels are made to score higher, so the expected
AUCs are known.

  python -m tests.make_fixture data/fixture --layout both   # linked/ and flat/
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ELECTRODES = {"LA": 6, "LB": 6, "RA": 6}


def channels() -> list[tuple[str, str, int]]:
    out = []
    for e, n in ELECTRODES.items():
        for i in range(1, n):
            out.append((f"{e}{i:02d}-{e}{i + 1:02d}", e, i))
    return out


RECS = [
    # recording_id, subject, task, kind, onset_s, stim, lvfa
    ("sub-P01_ses-implant_task-ictal1_run-01", "P01", "ictal1", "ictal", 60.0, False, True),
    ("sub-P01_ses-implant_task-stim2_run-01", "P01", "stim2", "ictal", 62.0, True, False),
    ("sub-P02_task-interictal", "P02", "interictal", "interictal", None, None, None),
]
SOZ = {"P01": {"LA01-LA02", "LA02-LA03", "LA03-LA04"}, "P02": {"RA01-RA02", "RA02-RA03"}}
RESECTED = {"P01": {"LA01-LA02", "LA02-LA03", "LA03-LA04", "LA04-LA05"}, "P02": {"RA01-RA02", "RA02-RA03", "RA03-RA04"}}
ONSET = {"sub-P01_ses-implant_task-ictal1_run-01": {"LA01-LA02", "LA02-LA03"},
         "sub-P01_ses-implant_task-stim2_run-01": {"LA02-LA03", "LA03-LA04"}}


def _prov(folder: Path, app: str, params: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "provenance.json").write_text(json.dumps({"app": app, "version": "0.1.0", "tools": {"python": "3.12"},
                                                        "parameters": params}, indent=1))


def write(root: Path, linked: bool, dynasd_in_methods: bool = False) -> None:
    rng = np.random.default_rng(42)
    p = (lambda port: root / port) if linked else (lambda port: root / "everything" / port.replace("-", "_"))
    chans = channels()
    # ---- ieeg (ieeg-prep derivative)
    ieeg = p("ieeg")
    rows = []
    for rid, subj, task, kind, onset, stim, lvfa in RECS:
        d = ieeg / f"sub-{subj}" / "ieeg"
        d.mkdir(parents=True, exist_ok=True)
        ch = []
        for k, (name, e, i) in enumerate(chans):
            x = (-30 if e.startswith("L") else 30) + i * 3
            y = {"LA": 10, "LB": -20, "RA": 5}[e]
            ch.append({"name": name, "type": "SEEG", "units": "µV", "low_cutoff": 0.5, "high_cutoff": 512,
                       "sampling_frequency": 1024, "status": "good", "status_description": "",
                       "contacts": name.replace("-", "|"),
                       "soz": str(name in SOZ[subj]).lower(), "resected": str(name in RESECTED[subj]).lower(),
                       "onset": (str(name in ONSET[rid]).lower() if rid in ONSET else ""), "spread": "",
                       "x": x, "y": y, "z": -10 + i, "space": "MNI152", "roi": f"{e}-region"})
        pd.DataFrame(ch).to_csv(d / f"{rid}_desc-preproc_channels.tsv", sep="\t", index=False)
        ev = [{"onset": 0, "duration": 40, "trial_type": "baseline", "source": "fixture"}]
        if onset is not None:
            ev.append({"onset": onset, "duration": 30, "trial_type": "seizure", "source": "fixture"})
        pd.DataFrame(ev).to_csv(d / f"{rid}_desc-preproc_events.tsv", sep="\t", index=False)
        rows.append({"recording_id": rid, "subject": subj, "session": "implant" if "ses-" in rid else "", "task": task,
                     "run": "01", "path": f"sub-{subj}/ieeg/{rid}_desc-preproc_ieeg.edf", "sfreq": 1024,
                     "n_channels": len(chans), "n_good": len(chans), "duration_s": 120, "montage": "bipolar", "kind": kind,
                     "onset_s": onset if onset is not None else "", "baseline_start_s": 0, "baseline_end_s": 40,
                     "source_format": "bids-edf", "stim_induced": "" if stim is None else str(stim).lower(),
                     "lvfa": "" if lvfa is None else str(lvfa).lower()})
    pd.DataFrame(rows).to_csv(ieeg / "recordings.csv", index=False)
    (ieeg / "dataset_description.json").write_text(json.dumps({"Name": "ieeg-prep derivative", "DatasetType": "derivative",
                                                                "SourceDatasets": [{"Name": "Synthetic fixture"}]}))
    _prov(ieeg, "processor-ieeg-prep", {"MONTAGE": "bipolar"})
    # ---- qc
    qc = p("qc")
    qrows = []
    for rid, *_ in RECS:
        for name, e, i in chans:
            for c in name.split("-"):
                qrows.append({"recording_id": rid, "channel": c, "status": "good", "reason": ""})
        qrows.append({"recording_id": rid, "channel": "RA07", "status": "bad", "reason": "line noise (80% of 1–250 Hz power at 60 Hz and harmonics)"})
        qrows.append({"recording_id": rid, "channel": "ECG1", "status": "dropped", "reason": "type ECG"})
    qc.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(qrows).drop_duplicates(["recording_id", "channel"]).to_csv(qc / "qc.csv", index=False)
    # a minimal PNG (1x1)
    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")
    (qc / f"{RECS[0][0]}.png").write_bytes(png)
    _prov(qc, "processor-ieeg-prep", {"MONTAGE": "bipolar"})
    # ---- spikes / hfo / bandpower / abnormality (labelled channels higher)
    sp, hf, bp, ab = [], [], [], []
    for rid, subj, *_ in RECS:
        for name, e, i in chans:
            hot = name in SOZ[subj]
            n = int(rng.poisson(20 if hot else 3))
            sp.append({"recording_id": rid, "channel": name, "n_spikes": n, "minutes": 1.5, "rate_per_min": n / 1.5, "detector": "janca"})
            r = int(rng.poisson(10 if name in RESECTED[subj] else 2))
            hf.append({"recording_id": rid, "channel": name, "band": "ripple", "n_hfo": r, "minutes": 1.5, "rate_per_min": r / 1.5, "detector": "linelength"})
            for b in ("delta", "theta", "alpha", "beta", "gamma", "broadband"):
                bp.append({"recording_id": rid, "channel": name, "band": b, "abs_power": 1.0, "rel_power": 0.2})
            z = float(rng.normal(3 if hot else 1, 0.3)) if e != "LB" or i < 5 else None
            ab.append({"recording_id": rid, "channel": name, "max_abs_z": z, "region": "within-20mm" if z else "unknown",
                       "n_reference": 30 if z else 0})
    for port, name, data, app in (("spikes", "spike_rates.csv", sp, "processor-ieeg-spikes"),
                                  ("hfo", "hfo_rates.csv", hf, "processor-ieeg-hfo"),
                                  ("bandpower", "bandpower.csv", bp, "processor-ieeg-bandpower"),
                                  ("abnormality", "channel_abnormality.csv", ab, "processor-ieeg-normative")):
        p(port).mkdir(parents=True, exist_ok=True)
        pd.DataFrame(data).to_csv(p(port) / name, index=False)
        _prov(p(port), app, {"LABEL": ""})
    # ---- onsets (seizure-dynasd), methods (ei, fragility), onset-zone (consensus)
    so, co, cs, ei, fr, oz, sc = [], [], [], [], [], [], []
    for rid, subj, task, kind, onset, stim, lvfa in RECS:
        if onset is None:
            continue
        so.append({"recording_id": rid, "onset_s": onset - 1.5, "method": "dynasd-lindda"})
        for k, (name, e, i) in enumerate(chans):
            on = name in ONSET[rid]
            t0 = onset - 1 + (0 if on else 5 + k * 0.5)
            co.append({"recording_id": rid, "channel": name, "onset_s": round(t0, 3), "recruited": str(on or k % 4 == 0).lower(),
                       "score": round(2.0 - 0.05 * k if on else 0.5 + 0.01 * k, 3), "method": "dynasd-lindda"})
            for tt in np.arange(onset - 20, onset + 30, 2.0):
                cs.append({"recording_id": rid, "channel": name, "time_s": float(tt),
                           "score": float(max(0.0, (2 if on else 0.6) * (1 if tt >= t0 else 0.1)))})
            ei.append({"recording_id": rid, "channel": name, "ei": 0.9 if on else 0.1 + 0.01 * k, "detection_s": onset + 2, "ratio_peak": 10})
            fr.append({"recording_id": rid, "channel": name, "fragility_pre": 0.5, "fragility_post": 0.95 if on else 0.4 + 0.01 * k, "rank": 0})
        f = pd.DataFrame(fr[-len(chans):])
        for r_, v in zip(f.index, f["fragility_post"].rank(ascending=False, method="min")):
            fr[-len(chans) + r_]["rank"] = int(v)
        for k, (name, e, i) in enumerate(chans):
            on = name in ONSET[rid]
            oz.append({"recording_id": rid, "channel": name, "dynasd_onset_s": "", "dynasd_score": "", "dynasd_recruited": "",
                       "ei": "", "fragility": "", "rank_dynasd": "", "rank_ei": "", "rank_fragility": "", "n_methods": 3,
                       "consensus_score": 0.95 if on else 0.5 - 0.01 * k, "rank": 0, "in_onset_zone": str(on).lower(),
                       "expert_onset": str(on).lower()})
        for m in ("dynasd", "ei", "fragility", "consensus"):
            for metric, v in (("auc", 1.0), ("precision", 1.0), ("recall", 1.0), ("f1", 1.0), ("r_precision", 1.0), ("n_selected", 2)):
                sc.append({"recording_id": rid, "method": m, "metric": metric, "value": v})
        sc.append({"recording_id": rid, "method": "dynasd", "metric": "event_tp", "value": 1})
    ozdf = pd.DataFrame(oz)
    ozdf["rank"] = ozdf.groupby("recording_id")["consensus_score"].rank(ascending=False, method="min").astype(int)
    dyn = "methods/dynasd" if dynasd_in_methods else "onsets"
    tables = [(dyn, "seizure_onsets.csv", pd.DataFrame(so), "processor-seizure-dynasd"),
              (dyn, "channel_onsets.csv", pd.DataFrame(co), None),
              (dyn, "channel_scores.csv", pd.DataFrame(cs), None),
              ("methods/ei", "ei.csv", pd.DataFrame(ei), "processor-seizure-ei"),
              ("methods/fragility", "fragility.csv", pd.DataFrame(fr), "processor-seizure-fragility"),
              ("onset-zone", "onset_zone.csv", ozdf, "processor-seizure-consensus"),
              ("onset-zone", "scores.csv", pd.DataFrame(sc), None)]
    for port, name, df, app in tables:
        folder = p(port) if linked else root / "everything" / port.replace("/", "_").replace("-", "_")
        folder.mkdir(parents=True, exist_ok=True)
        df.to_csv(folder / name, index=False)
        if app:
            _prov(folder, app, {"LABEL": ""})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--layout", choices=["linked", "flat", "both"], default="both")
    a = ap.parse_args()
    out = Path(a.out)
    for layout in (["linked", "flat"] if a.layout == "both" else [a.layout]):
        d = out / layout
        if d.exists():
            shutil.rmtree(d)
        write(d, linked=layout == "linked")
        print(f"wrote {d}")


if __name__ == "__main__":
    main()
