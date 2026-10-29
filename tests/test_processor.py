"""Synthetic upstream outputs through the processor (no Docker)."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from processor import main as app
from processor import stats as S
from tests.make_fixture import write

RUO = "Research use only, not for clinical decisions"


def run(input_dir: Path, output_dir: Path, **params) -> int:
    env = {"INPUT_DIR": str(input_dir), "OUTPUT_DIR": str(output_dir), **{k: str(v) for k, v in params.items()}}
    old = {k: os.environ.get(k) for k in [*env, *app.PARAMETERS]}
    for k in app.PARAMETERS:
        os.environ.pop(k, None)
    os.environ.update(env)
    try:
        return app.main()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture()
def linked(tmp_path: Path) -> Path:
    write(tmp_path / "linked", linked=True)
    return tmp_path / "linked"


def pages(out: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in (out / "report").glob("*.html")}


def test_auc_ties_and_missing():
    assert S.auc([3, 2, 1], [True, False, False])[0] == 1.0
    assert S.auc([1, 1, 1], [True, False, False])[0] == 0.5
    assert S.auc([1, 2, None], [True, False, True]) == (0.0, 1, 1)
    assert S.auc([1, 2], [True, True])[0] is None
    fpr, tpr = S.roc_curve([3, 2, 1], [True, False, False])
    assert list(tpr) == [0.0, 1.0, 1.0, 1.0] and fpr[-1] == 1.0


def test_both_modes_linked(linked: Path, tmp_path: Path):
    out = tmp_path / "out"
    assert run(linked, out, REPORT_TITLE="Fixture report") == 0
    html = pages(out)
    assert set(html) == {"index.html", "sub-P01.html", "sub-P02.html"}
    for name, text in html.items():
        assert RUO in text, name
        assert "<script" not in text and "http://" not in text.replace("http://www.w3.org", "")
    idx = html["index.html"]
    assert "Fixture report" in idx
    assert "Interictal Biomarker Mapping" in idx and "Seizure Onset Localisation" in idx
    assert "stimulation-induced" in idx and "LVFA" in idx
    # every figure referenced exists
    for text in html.values():
        for src in pd.Series(text.split('src="figures/')[1:]).str.split('"').str[0]:
            assert (out / "report" / "figures" / src).is_file(), src
    prov = json.loads((out / "tables" / "provenance.json").read_text())
    assert prov["sectionErrors"] == []
    assert prov["modes"] == ["Interictal Biomarker Mapping", "Seizure Onset Localisation"]

    auc = pd.read_csv(out / "tables" / "interictal_auc.csv")
    soz = auc[(auc.label == "soz") & (auc.measure == "spike_rate")]
    assert len(soz) == 2 and (soz.auc > 0.9).all()
    res = auc[(auc.label == "resected") & (auc.measure == "ripple_rate")]
    assert (res.auc > 0.8).all()
    ch = pd.read_csv(out / "tables" / "interictal_channels.csv")
    assert {"spike_rate", "ripple_rate", "max_abs_z", "rank_spike_rate"} <= set(ch.columns)
    assert set(ch["soz"].dropna().astype(str).str.lower()) <= {"true", "false"}

    on = pd.read_csv(out / "tables" / "seizure_onsets.csv")
    assert len(on) == 2
    assert on["onset_error_s"].round(2).tolist() == [-1.5, -1.5]
    assert set(on["stim_source"]) == {"recordings.csv"}
    sc = pd.read_csv(out / "tables" / "seizure_scores.csv")
    assert set(sc["method"]) >= {"dynasd", "ei", "fragility", "consensus"}
    agree = pd.read_csv(out / "tables" / "method_agreement.csv")
    assert len(agree) == 6 and agree["top_k_overlap"].between(0, 1).all()
    pat = pd.read_csv(out / "tables" / "patient_summary.csv")
    assert {"all", "spontaneous", "stimulation-induced", "LVFA", "no LVFA"} <= set(pat["group"])
    assert "DynaSD scores over time" in html["sub-P01.html"]  # channel_scores.csv -> heatmap
    qc = pd.read_csv(out / "tables" / "qc_channels.csv")
    assert {"bad", "dropped"} <= set(qc["status"].dropna())


def test_flat_layout_gives_the_same_numbers(tmp_path: Path, linked: Path):
    write(tmp_path / "flat", linked=False)
    a, b = tmp_path / "a", tmp_path / "b"
    assert run(linked, a) == 0 and run(tmp_path / "flat", b) == 0
    for name in ("interictal_auc.csv", "seizure_scores.csv", "seizure_onsets.csv"):
        pd.testing.assert_frame_equal(pd.read_csv(a / "tables" / name), pd.read_csv(b / "tables" / name))


def test_without_fragility_and_consensus_scores_are_computed(linked: Path, tmp_path: Path):
    shutil.rmtree(linked / "onset-zone")
    shutil.rmtree(linked / "methods" / "fragility")
    (linked / "onsets" / "channel_scores.csv").unlink()
    out = tmp_path / "out"
    assert run(linked, out, TOP_K=2) == 0
    sc = pd.read_csv(out / "tables" / "seizure_scores.csv")
    assert set(sc["method"]) == {"dynasd", "ei"}
    assert set(sc["source"]) == {"computed by this report"}
    aucs = sc[sc.metric == "auc"]["value"]
    assert (aucs == 1.0).all()
    prec = sc[(sc.metric == "precision")]["value"]
    assert (prec == 1.0).all()  # top-2 = the two onset channels
    html = pages(out)["sub-P01.html"]
    assert "DynaSD scores over time were not among the inputs" in html
    assert "top 2 by DynaSD" in html


def test_interictal_only(tmp_path: Path, linked: Path):
    only = tmp_path / "only"
    only.mkdir()
    shutil.copytree(linked / "spikes", only / "spikes")
    out = tmp_path / "out"
    assert run(only, out) == 0
    prov = json.loads((out / "report" / "provenance.json").read_text())
    assert prov["modes"] == ["Interictal Biomarker Mapping"]
    # no labels without the ieeg port: a channel table and strips, no ROC
    html = pages(out)["sub-P01.html"]
    assert "no ROC" in html
    assert (out / "tables" / "interictal_channels.csv").is_file()
    assert not (out / "tables" / "seizure_scores.csv").exists()


def test_bad_table_is_ignored_and_nothing_found_fails(tmp_path: Path, linked: Path):
    (linked / "methods" / "ei" / "ei.csv").write_text("foo,bar\n1,2\n")
    out = tmp_path / "out"
    assert run(linked, out) == 0
    sc = pd.read_csv(out / "tables" / "seizure_scores.csv")
    assert "ei" not in set(sc["method"])
    empty = tmp_path / "empty"
    (empty / "x").mkdir(parents=True)
    (empty / "x" / "readme.txt").write_text("nothing")
    assert run(empty, tmp_path / "out2") == 1


def test_bad_parameter(tmp_path: Path, linked: Path):
    assert run(linked, tmp_path / "o", TOP_K="0") == 2


def test_lambda_handler(tmp_path: Path, linked: Path, monkeypatch):
    from processor import handler

    monkeypatch.setenv("TOP_K", "99")  # left over from a warm invocation: must be cleared
    res = handler.handler({"inputDir": str(linked), "outputDir": str(tmp_path / "out"), "REPORT_TITLE": "From Lambda"}, None)
    assert res["status"] == "ok"
    prov = json.loads((tmp_path / "out" / "tables" / "provenance.json").read_text())
    assert prov["parameters"]["TOP_K"] == 10 and prov["parameters"]["REPORT_TITLE"] == "From Lambda"
    with pytest.raises(RuntimeError):
        handler.handler({"inputDir": str(tmp_path / "missing"), "outputDir": str(tmp_path / "o2")}, None)


def test_method_apps_in_named_folders_of_one_methods_port(tmp_path: Path, linked: Path):
    """dynasd/, ei/, fragility/ fanned into methods/, each with its own provenance.json; no onsets port."""
    named = tmp_path / "named"
    write(named, linked=True, dynasd_in_methods=True)
    assert not (named / "onsets").exists()
    a, b = tmp_path / "a", tmp_path / "b"
    assert run(linked, a) == 0 and run(named, b) == 0
    for name in ("seizure_scores.csv", "seizure_onsets.csv", "method_agreement.csv"):
        pd.testing.assert_frame_equal(pd.read_csv(a / "tables" / name), pd.read_csv(b / "tables" / name))
    apps = [m["app"] for m in json.loads((b / "tables" / "metrics.json").read_text())["methods"]]
    assert {"processor-seizure-dynasd", "processor-seizure-ei", "processor-seizure-fragility"} <= set(apps)
