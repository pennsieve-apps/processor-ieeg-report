"""
The report's figures (matplotlib, Agg, PNG). Colours: one sequential blue ramp
for magnitudes; fixed categorical slots for methods/measures (identity never by
colour alone: legends, line styles and marker shapes go with it); expert labels
drawn as outlines (ring = SOZ / onset, square = resected).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from processor import stats as S  # noqa: E402

INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]
SEQ = LinearSegmentedColormap.from_list("seq", ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#104281", "#0d366b"])
METHOD_STYLE = {"dynasd": (SERIES[0], "-"), "ei": (SERIES[1], "--"), "fragility": (SERIES[2], "-."), "consensus": (INK, ":")}
MEASURE_STYLE = {"spike_rate": (SERIES[0], "-"), "ripple_rate": (SERIES[1], "--"), "fast_ripple_rate": (SERIES[2], "-."),
                 "max_abs_z": (SERIES[3], ":")}
DPI = 110

plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "legend.frameon": False, "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.6,
})


def _save(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path.name


def _labels(t: pd.DataFrame) -> tuple[pd.Series, pd.Series, str]:
    """(ring mask, square mask, ring label): SOZ rings when known, else onset (any seizure)."""
    soz = t["soz"].eq(True) if "soz" in t.columns else pd.Series(False, index=t.index)
    ring_name = "SOZ"
    if not soz.any() and "onset_any" in t.columns:
        soz, ring_name = t["onset_any"].eq(True), "seizure onset"
    res = t["resected"].eq(True) if "resected" in t.columns else pd.Series(False, index=t.index)
    return soz, res, ring_name


def channel_map(t: pd.DataFrame, measures: list[str], names: dict[str, str], space: str, path: Path) -> str | None:
    """Rows = measures, columns = axial / coronal / sagittal projections."""
    xyz = t[["x", "y", "z"]].apply(pd.to_numeric, errors="coerce")
    ok = xyz.notna().all(axis=1)
    if ok.sum() < 2 or not measures:
        return None
    t, xyz = t[ok], xyz[ok]
    ring, square, ring_name = _labels(t)
    views = [("axial (x, y)", "x", "y"), ("coronal (x, z)", "x", "z"), ("sagittal (y, z)", "y", "z")]
    fig, axes = plt.subplots(len(measures), 3, figsize=(10.5, 3.1 * len(measures)), squeeze=False)
    for i, m in enumerate(measures):
        v = pd.to_numeric(t[m], errors="coerce")
        vmax = float(np.nanpercentile(v, 95)) if v.notna().any() else 1.0
        vmax = vmax if vmax > 0 else (float(v.max()) if v.notna().any() and v.max() > 0 else 1.0)
        top = v.sort_values(ascending=False).dropna().index[:3]
        for j, (title, a, b) in enumerate(views):
            ax = axes[i][j]
            nan = v.isna()
            ax.scatter(xyz.loc[nan, a], xyz.loc[nan, b], s=10, marker="x", color=MUTED, linewidths=0.8, zorder=1)
            order = v.fillna(-1).sort_values().index  # high values drawn last
            order = [k for k in order if not nan[k]]
            sc = ax.scatter(xyz.loc[order, a], xyz.loc[order, b], c=v[order], cmap=SEQ, vmin=0, vmax=vmax, s=34,
                            edgecolors=SURFACE, linewidths=0.6, zorder=2)
            ax.scatter(xyz.loc[ring, a], xyz.loc[ring, b], s=120, facecolors="none", edgecolors=INK, linewidths=1.4, zorder=3)
            ax.scatter(xyz.loc[square, a], xyz.loc[square, b], s=150, marker="s", facecolors="none", edgecolors="#a33b13",
                       linewidths=1.0, zorder=3)
            for k in top:
                ax.annotate(str(t.loc[k, "channel"]), (xyz.loc[k, a], xyz.loc[k, b]), xytext=(4, 4), textcoords="offset points",
                            fontsize=7, color=INK)
            ax.set_aspect("equal", adjustable="datalim")
            ax.set_xlabel(f"{a} (mm)")
            ax.set_ylabel(f"{b} (mm)")
            if i == 0:
                ax.set_title(title, fontweight="normal", color=INK2)
        cb = fig.colorbar(sc, ax=axes[i].tolist(), fraction=0.025, pad=0.01)
        cb.set_label(names[m])
        cb.outline.set_visible(False)
    handles = [plt.Line2D([], [], marker="o", ls="", mfc="none", mec=INK, ms=9, label=ring_name),
               plt.Line2D([], [], marker="s", ls="", mfc="none", mec="#a33b13", ms=9, label="resected"),
               plt.Line2D([], [], marker="x", ls="", color=MUTED, label="not scored")]
    fig.legend(handles=handles, loc="upper center", ncol=3, bbox_to_anchor=(0.45, 1.0 + 0.04 / len(measures)))
    fig.suptitle(f"Coordinates: {space or 'unknown space'}; colour scale capped at the 95th percentile", y=-0.01,
                 fontsize=8, color=INK2, fontweight="normal")
    return _save(fig, path)


def electrode_strips(t: pd.DataFrame, measures: list[str], names: dict[str, str], path: Path) -> str | None:
    """One bar strip per measure; channels grouped by electrode, in contact order."""
    measures = [m for m in measures if m in t.columns and t[m].notna().any()]
    if not measures:
        return None
    t = t.sort_values(["electrode", "contact", "channel"], kind="mergesort").reset_index(drop=True)
    n = len(t)
    ring, square, ring_name = _labels(t)
    width = min(18.0, max(7.0, 0.075 * n + 2))
    fig, axes = plt.subplots(len(measures), 1, figsize=(width, 1.9 * len(measures) + 0.6), sharex=True, squeeze=False)
    x = np.arange(n)
    groups = t.groupby("electrode", sort=False).indices
    for i, m in enumerate(measures):
        ax = axes[i][0]
        v = pd.to_numeric(t[m], errors="coerce").fillna(0).to_numpy()
        color, _ = MEASURE_STYLE.get(m, (SERIES[0], "-"))
        ax.bar(x, v, width=0.8, color=color, linewidth=0)
        ymax = max(float(v.max()), 1e-9)
        ax.scatter(x[ring.to_numpy()], np.full(int(ring.sum()), -0.09 * ymax), marker="o", s=14, facecolors="none",
                   edgecolors=INK, linewidths=1.0, clip_on=False)
        ax.scatter(x[square.to_numpy()], np.full(int(square.sum()), -0.2 * ymax), marker="s", s=14, facecolors="none",
                   edgecolors="#a33b13", linewidths=1.0, clip_on=False)
        ax.set_ylim(-0.26 * ymax, ymax * 1.08)
        ax.set_ylabel(names[m], rotation=0, ha="right", va="center")
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="x", length=0)
        for _e, idx in groups.items():
            if idx.min() > 0:
                ax.axvline(idx.min() - 0.5, color=GRID, lw=0.8, zorder=0)
        ax.set_yticks([0, ymax])
        ax.set_yticklabels(["0", f"{ymax:.2g}"])
    ax = axes[-1][0]
    ax.set_xticks([float(np.mean(idx)) for idx in groups.values()])
    ax.set_xticklabels(list(groups.keys()), rotation=90 if len(groups) > 12 else 0, fontsize=8)
    ax.set_xlim(-0.8, n - 0.2)
    handles = [plt.Line2D([], [], marker="o", ls="", mfc="none", mec=INK, ms=6, label=ring_name),
               plt.Line2D([], [], marker="s", ls="", mfc="none", mec="#a33b13", ms=6, label="resected")]
    axes[0][0].legend(handles=handles, loc="upper right", ncol=2, bbox_to_anchor=(1, 1.35))
    return _save(fig, path)


def roc_curves(t: pd.DataFrame, measures: list[str], targets: list[str], names: dict[str, str],
               target_names: dict[str, str], path: Path) -> str | None:
    if not measures or not targets:
        return None
    fig, axes = plt.subplots(1, len(targets), figsize=(3.6 * len(targets), 3.5), squeeze=False)
    drew = False
    for j, lab in enumerate(targets):
        ax = axes[0][j]
        ax.plot([0, 1], [0, 1], color=GRID, lw=1)
        for m in measures:
            r = S.roc_curve(t[m], t[lab])
            if r is None:
                continue
            a, npos, nneg = S.auc(t[m], t[lab])
            color, ls = MEASURE_STYLE.get(m, (SERIES[0], "-"))
            ax.step(r[0], r[1], where="post", color=color, ls=ls, lw=2, label=f"{names[m]} {a:.2f}")
            drew = True
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.02)
        ax.set_aspect("equal")
        ax.set_xlabel("false positive rate")
        ax.set_ylabel("true positive rate")
        ax.set_title(f"vs {target_names[lab]}")
        ax.legend(title="AUC", loc="upper center", bbox_to_anchor=(0.5, -0.2), fontsize=8, title_fontsize=8)
    if not drew:
        plt.close(fig)
        return None
    return _save(fig, path)


def cohort_auc(rows: pd.DataFrame, names: dict[str, str], target_names: dict[str, str], path: Path) -> str | None:
    """Dots = per-subject AUC; one row per measure x label; 0.5 = chance."""
    rows = rows.dropna(subset=["auc"])
    if rows.empty:
        return None
    keys = list(dict.fromkeys(zip(rows["measure"], rows["label"])))
    fig, ax = plt.subplots(figsize=(7, 0.42 * len(keys) + 0.9))
    ax.axvline(0.5, color=MUTED, lw=1, ls="--")
    for i, (m, lab) in enumerate(keys):
        g = rows[(rows["measure"] == m) & (rows["label"] == lab)]
        color, _ = MEASURE_STYLE.get(m, (SERIES[0], "-"))
        jitter = (np.arange(len(g)) - (len(g) - 1) / 2) * 0.06
        ax.scatter(g["auc"], i + jitter, s=36, color=color, edgecolors=SURFACE, linewidths=1.2, zorder=3)
        med = float(g["auc"].median())
        ax.plot([med, med], [i - 0.3, i + 0.3], color=INK, lw=2)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([f"{names[m]} vs {target_names[l]}" for m, l in keys])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("ROC AUC per subject (dots), median (bar); dashed line = chance")
    ax.grid(axis="x")
    return _save(fig, path)


def seizure_overview(sz: dict[str, Any], scores_time: pd.DataFrame | None, max_channels: int, path: Path) -> str | None:
    """Left: channels x time (DynaSD scores over time when given, else each channel's
    recruitment from its DynaSD onset); right: each method's rank of those channels."""
    z: pd.DataFrame | None = sz.get("table")
    if z is None or z.empty:
        return None
    z = z.head(max_channels)
    chans = list(z["channel"])
    n = len(chans)
    methods = [m for m in ("dynasd", "ei", "fragility", "consensus") if f"rank_{m}" in z.columns]
    has_time = (scores_time is not None and not scores_time.empty) or ("dynasd_onset_s" in z.columns and z["dynasd_onset_s"].notna().any())
    ncols = (1 if has_time else 0) + (1 if methods else 0)
    if ncols == 0:
        return None
    ratios = ([3.2] if has_time else []) + ([0.35 * max(len(methods), 1) + 0.4] if methods else [])
    fig, axes = plt.subplots(1, ncols, figsize=(sum(ratios) * 2.2 + 1.5, 0.19 * n + 1.5), squeeze=False,
                             gridspec_kw={"width_ratios": ratios, "wspace": 0.05})
    y = np.arange(n)
    expert = z["onset"].eq(True).to_numpy() if "onset" in z.columns else np.zeros(n, bool)
    col = 0
    if has_time:
        ax = axes[0][col]
        col += 1
        dur = sz.get("duration_s")
        if scores_time is not None and not scores_time.empty:
            piv = scores_time.pivot_table(index="channel", columns="time_s", values="score", aggfunc="mean").reindex(chans)
            times = piv.columns.to_numpy(dtype=float)
            vmax = float(np.nanpercentile(piv.to_numpy(), 99)) if np.isfinite(piv.to_numpy()).any() else 1
            im = ax.imshow(piv.to_numpy(), aspect="auto", cmap=SEQ, vmin=0, vmax=vmax, interpolation="nearest",
                           extent=[times.min(), times.max(), n - 0.5, -0.5])
            cb = fig.colorbar(im, cax=ax.inset_axes([0.6, -0.95 / (0.19 * n + 1.5), 0.38, 0.14 / (0.19 * n + 1.5)]), orientation="horizontal")
            cb.set_label("DynaSD score", fontsize=8)
            cb.outline.set_visible(False)
            ax.set_title("DynaSD score over time", loc="left")
        else:
            on = pd.to_numeric(z["dynasd_onset_s"], errors="coerce").to_numpy()
            score = pd.to_numeric(z.get("dynasd_score", pd.Series(np.nan, index=z.index)), errors="coerce").to_numpy()
            recruited = z["dynasd_recruited"].eq(True).to_numpy() if "dynasd_recruited" in z.columns else np.ones(n, bool)
            end = dur if dur else (np.nanmax(on) + 30 if np.isfinite(on).any() else 1)
            if sz.get("seizure_end_s"):
                end = min(end, sz["seizure_end_s"] + 30) if dur else sz["seizure_end_s"] + 30
            sfin = score[np.isfinite(score)]
            vmax = float(np.nanpercentile(sfin, 95)) if sfin.size else 1.0
            for i in range(n):
                if not np.isfinite(on[i]):
                    continue
                c = SEQ(min(score[i] / vmax, 1.0)) if np.isfinite(score[i]) and vmax > 0 else SEQ(0.5)
                ax.barh(i, end - on[i], left=on[i], height=0.72, color=c if recruited[i] else "none",
                        edgecolor=c, linewidth=0.8)
            sm = plt.cm.ScalarMappable(cmap=SEQ, norm=plt.Normalize(0, vmax))
            cb = fig.colorbar(sm, cax=ax.inset_axes([0.6, -0.95 / (0.19 * n + 1.5), 0.38, 0.14 / (0.19 * n + 1.5)]),
                              orientation="horizontal")
            cb.set_label("DynaSD score (÷ threshold)", fontsize=8)
            cb.outline.set_visible(False)
            refs = [v for v in (sz.get("expert_onset_s"), sz.get("detected_onset_s")) if v is not None]
            pts = list(on[np.isfinite(on)]) + refs
            lo = (min(pts) if pts else 0.0) - 15
            hi = min(end, (max(pts) if pts else end) + 30)
            ax.set_xlim(max(0.0, lo), max(hi, lo + 30))
            ax.set_title("DynaSD onset per channel (filled = recruited, outline = not)", loc="left")
        if sz.get("expert_onset_s") is not None:
            ax.axvline(sz["expert_onset_s"], color=INK, lw=1.6, label=f"expert onset {sz['expert_onset_s']:.1f} s")
        if sz.get("detected_onset_s") is not None:
            ax.axvline(sz["detected_onset_s"], color="#a33b13", lw=1.6, ls="--", label=f"detected onset {sz['detected_onset_s']:.1f} s")
        ax.set_ylim(n - 0.5, -0.5)
        ax.set_yticks(y)
        ax.set_yticklabels([("● " if e else "") + c for c, e in zip(chans, expert)], fontsize=7)
        for lbl, e in zip(ax.get_yticklabels(), expert):
            if e:
                lbl.set_fontweight("bold")
        ax.set_xlabel("time from recording start (s)")
        ax.legend(loc="lower right", fontsize=7.5)
    if methods:
        ax = axes[0][col]
        ranks = np.column_stack([pd.to_numeric(z[f"rank_{m}"], errors="coerce").to_numpy() for m in methods])
        nmax = max(float(np.nanmax(ranks)) if np.isfinite(ranks).any() else 1, 1)
        shade = 1 - np.clip((ranks - 1) / max(min(nmax, 3 * max_channels) - 1, 1), 0, 1)
        ax.imshow(np.where(np.isfinite(ranks), shade, np.nan), aspect="auto", cmap=SEQ, vmin=0, vmax=1,
                  interpolation="nearest")
        for i in range(n):
            for j in range(len(methods)):
                if np.isfinite(ranks[i, j]):
                    ax.text(j, i, f"{int(ranks[i, j])}", ha="center", va="center", fontsize=6.5,
                            color=SURFACE if shade[i, j] > 0.55 else INK)
        ax.set_xticks(range(len(methods)))
        ax.set_xticklabels([{"dynasd": "DynaSD", "ei": "EI", "fragility": "Fragility", "consensus": "Consensus"}[m]
                            for m in methods], rotation=45, ha="left")
        ax.xaxis.tick_top()
        ax.tick_params(length=0)
        ax.set_yticks(y)
        if has_time:
            ax.set_yticklabels([])
        else:
            ax.set_yticklabels([("● " if e else "") + c for c, e in zip(chans, expert)], fontsize=7)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title("rank (1 = most onset-like)", loc="left", fontsize=8, fontweight="normal", pad=28)
    return _save(fig, path)


def onset_errors(seizures: list[dict], path: Path) -> str | None:
    rows = [s for s in seizures if s.get("onset_error_s") is not None]
    if not rows:
        return None
    subjects = sorted({s["subject"] for s in rows})
    fig, ax = plt.subplots(figsize=(7, 0.42 * len(subjects) + 1.0))
    ax.axvline(0, color=MUTED, lw=1, ls="--")
    markers = {True: ("^", "stimulation-induced"), False: ("o", "spontaneous"), None: ("D", "type unknown")}
    seen = set()
    for i, subj in enumerate(subjects):
        g = [s for s in rows if s["subject"] == subj]
        for k, s in enumerate(g):
            mk, name = markers[s.get("stim_induced")]
            ax.scatter(s["onset_error_s"], i + (k - (len(g) - 1) / 2) * 0.12, marker=mk, s=40, color=SERIES[0],
                       edgecolors=SURFACE, linewidths=1.0, zorder=3, label=name if name not in seen else None)
            seen.add(name)
    ax.set_yticks(range(len(subjects)))
    ax.set_yticklabels(subjects)
    ax.invert_yaxis()
    ax.set_xlabel("detected − expert onset (s); negative = detected early")
    ax.grid(axis="x")
    ax.legend(loc="lower right", fontsize=8)
    return _save(fig, path)


def seizure_aucs(seizures: list[dict], methods: list[str], path: Path) -> str | None:
    data = [(m, s) for m in methods for s in seizures for r in s["scores"] if r["method"] == m and r.get("auc") is not None]
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(7, 0.5 * len(methods) + 1.0))
    ax.axvline(0.5, color=MUTED, lw=1, ls="--")
    names = {"dynasd": "DynaSD", "ei": "EI", "fragility": "Fragility", "consensus": "Consensus"}
    markers = {True: "^", False: "o", None: "D"}
    for i, m in enumerate(methods):
        vals = [(r["auc"], s.get("stim_induced")) for s in seizures for r in s["scores"] if r["method"] == m and r.get("auc") is not None]
        if not vals:
            continue
        color, _ = METHOD_STYLE[m]
        rng = np.random.default_rng(42)
        for a, stim in vals:
            ax.scatter(a, i + rng.uniform(-0.18, 0.18), marker=markers[stim], s=26, color=color, edgecolors=SURFACE,
                       linewidths=0.8, zorder=3)
        med = float(np.median([a for a, _ in vals]))
        ax.plot([med, med], [i - 0.3, i + 0.3], color=INK, lw=2)
    ax.set_yticks(range(len(methods)))
    ax.set_yticklabels([names[m] for m in methods])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("ROC AUC per seizure vs expert onset channels; bar = median; ▲ stimulation-induced, ● spontaneous")
    ax.grid(axis="x")
    return _save(fig, path)
