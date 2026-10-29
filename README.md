# processor-ieeg-report

The last step of both epilepsy iEEG workflows at Penn:

- **Interictal Biomarker Mapping:** `ieeg-prep → {ieeg-spikes, ieeg-bandpower → ieeg-normative, ieeg-hfo} → ieeg-report`
- **Seizure Onset Localisation:** `ieeg-prep → seizure-dynasd → {seizure-ei, seizure-fragility} → seizure-consensus → ieeg-report`

It reads whatever upstream outputs it is given, works out which of the two workflows they come from
(or both), and writes one offline HTML report (a cohort page plus one page per subject) and summary
tables. **Every input is optional**: a section is drawn when its inputs are present and left out,
with a sentence saying why, when they are not. The run fails only when none of the inputs is found.

**Research use only, not for clinical decisions.** Every page says so at the top and the bottom.

## What it is for

*For an epileptologist:* one place to see, per patient, which contacts the detectors and models
single out (spike rate, ripple rate, band-power abnormality; DynaSD recruitment, Epileptogenicity
Index, neural fragility and their consensus), where those contacts sit on the implant, whether
they coincide with the SOZ, resection or the expert-marked onset channels, and how far the
automatic seizure onset time lies from the expert's. The page states what each measure can and
cannot tell, next to the numbers.

*For a researcher:* the per-subject and per-seizure scores (ROC AUC, precision/recall,
R-precision, onset-time error), agreement between methods (rank correlation, top-k overlap),
splits by spontaneous vs stimulation-induced seizures and by LVFA, the QC that shaped the data, and
every step's version, parameters and verified citations from its `provenance.json`; plus CSVs of
all of it.

The report fits nothing and tunes nothing. It computes ROC AUCs, ranks and rank correlations from
the upstream tables. Leave-one-patient-out for the normative atlas is done upstream
(ieeg-normative); the report only reports it.

## Sections

| Section | Inputs | What it shows |
|---|---|---|
| Subjects | any | per subject: recordings, interictal measures, seizures, labels known, median consensus AUC; links to the subject pages |
| Interictal Biomarker Mapping (per subject) | `spikes`, `hfo`, `abnormality` (+ `ieeg` for labels and coordinates) | channels ranked by spike rate with ripple / fast-ripple rate and band-power abnormality (rank of each) and SOZ / resected / onset labels; a channel map (axial, coronal, sagittal projections of the `_channels.tsv` coordinates, MNI or native, one row per measure, labelled channels outlined); per-electrode bar strips of spike and HFO rate in contact order; ROC curves and AUC per measure against SOZ and resected channels (or, when neither is known, the expert seizure-onset channels of the subject's seizures); what each measure can and cannot tell |
| Interictal, across subjects | same | per measure × label: median, IQR and range of the per-subject AUCs, how many subjects above 0.5, a dot plot |
| Seizure Onset Localisation (per seizure) | `onsets`, `methods`, `onset-zone` (+ `ieeg`) | expert vs detected onset and the difference; channels × time (a heat map of DynaSD scores over time when a `channel_scores.csv` is given, else each channel's DynaSD onset, shaded by score) beside each method's rank of the top channels; the ranked channel table; the consensus onset zone; agreement between methods (Spearman ρ, top-k overlap); scores against the expert onset channels (AUC, precision, recall, F1, R-precision) |
| Seizure onset, across seizures | same | per patient and for all seizures: median AUC per method, median absolute and signed onset error, detections within the SzCORE tolerance; split spontaneous / stimulation-induced and LVFA / no LVFA when known; observations (e.g. stimulation-induced onsets detected early) |
| QC | `qc`, `ieeg` | per recording: montage, sampling rate, length, channels kept, bad contacts/channels with ieeg-prep's reason, dropped channels; ieeg-prep's QC plot on the subject page |
| Methods & citations | every `provenance.json` found | per app: step, version(s), parameters, tool versions, the papers (DOI, PMID) |
| Input data | `dataset_description.json`, prep provenance | the source datasets with DOI and licence |

Scores come from seizure-consensus's `scores.csv` when it is linked. Without it the report computes
the same metrics itself, with the same rules (checked: identical AUC, precision, recall, F1 and
R-precision for all three methods on the 24 demo seizures): AUC = Mann-Whitney probability with ties
½; DynaSD ranks recruited channels first by onset time, then the others by score; EI by `ei`;
fragility by `fragility_post` (else `fragility_pre`, else its `rank`); each method's selection = its
top `TOP_K`.

## Ports

Inputs (all `placement: subfolder`, none required). Linked from a workflow each arrives in
`INPUT_DIR/<input>/`; without links (everything side by side at the root of `INPUT_DIR`, possibly
nested) the tables are found by name anywhere. A table is looked for in its port's folder first,
then anywhere; tables of the same name in several folders are concatenated (one folder per LABEL),
a repeated key is dropped with a warning. A table without its required columns is ignored with a
warning. Symlinks are followed.

| Input | Files used | Produced by |
|---|---|---|
| `ieeg` | `recordings.csv`, `*_channels.tsv`, `*_events.tsv`, `dataset_description.json` | ieeg-prep |
| `qc` | `qc.csv`, `<recording_id>.png` | ieeg-prep |
| `spikes` | `spike_rates.csv` | ieeg-spikes |
| `bandpower` | `bandpower.csv` (listed; the abnormality is what is mapped) | ieeg-bandpower |
| `hfo` | `hfo_rates.csv` | ieeg-hfo |
| `abnormality` | `channel_abnormality.csv` | ieeg-normative |
| `onsets` | `seizure_onsets.csv`, `channel_onsets.csv`, optional `channel_scores.csv` | seizure-dynasd |
| `methods` | `ei.csv`, `fragility.csv` (and dynasd's tables, in their own `dynasd/` folder, when dynasd is linked here) | seizure-ei, seizure-fragility (fan-in) |
| `onset-zone` | `onset_zone.csv`, `scores.csv` | seizure-consensus |

Outputs (two, so each goes to `OUTPUT_DIR/<output>/`):

| Output | Files |
|---|---|
| `report` | `index.html`, `sub-<subject>.html`, `figures/*.png`, `provenance.json`. Inline CSS, no scripts, no external resources: open `index.html` from the folder. |
| `tables` | the CSVs below (each when its inputs exist), `metrics.json` (every number and sentence of the pages), `provenance.json` |

| Table | Columns |
|---|---|
| `interictal_channels.csv` | subject, channel, electrode, roi, x, y, z, space, soz, resected, onset_n (seizures in which the channel is an expert onset channel), onset_known, spike_rate, ripple_rate, fast_ripple_rate, max_abs_z (each when present), rank_<measure> |
| `interictal_auc.csv` | subject, measure, label (`soz`, `resected`, `onset_any`), auc, n_positive, n_negative |
| `seizure_onsets.csv` | recording_id, subject, task, expert_onset_s, detected_onset_s, onset_error_s (detected − expert), detected_source, stim_induced, stim_source, lvfa, n_channels, n_expert_onset, onset_zone (`|`-joined), onset_zone_source |
| `seizure_channels.csv` | recording_id, channel, electrode, roi, expert_onset, dynasd_onset_s, dynasd_recruited, dynasd_score, ei, fragility, consensus_score, rank_<method>, in_onset_zone |
| `seizure_scores.csv` | recording_id, method, metric (auc, precision, recall, f1, r_precision, n_selected, onset_error_s), value, source |
| `method_agreement.csv` | recording_id, a, b, spearman, n, top_k_overlap, k |
| `patient_summary.csv` | subject, group (`all`, `spontaneous`, `stimulation-induced`, `LVFA`, `no LVFA`), n_seizures, <method>_auc_median/_n, <method>_r_precision_median, abs_onset_error_median_s, onset_error_median_s, detected_within_tolerance |
| `qc_channels.csv` | recording_id, subject, montage, sfreq, duration_s, n_channels, n_good, channel, status (`bad`/`dropped`), reason |

Rates are pooled per subject and channel over its recordings (events ÷ minutes analysed); the
abnormality is the mean of `max_abs_z` over recordings. `soz`/`resected` count when any recording
of the subject has them; `onset` is per seizure.

**Seizure type.** `stim_induced` and `lvfa` come from `recordings.csv` columns of those names (as
seizure-consensus reads them). When `stim_induced` is missing the report falls back on the BIDS
task name (`task-stim<N>` = stimulation-induced, `task-ictal<N>` = spontaneous, the naming of the
Multi-Expert Seizure Annotation dataset) and says so on the page; there is no fallback for LVFA.

## Parameters

| Name | Default | What it does |
|---|---|---|
| `REPORT_TITLE` | `Epilepsy iEEG Report` | Title of the pages. |
| `TOP_K` | `10` | Size of each method's selected onset zone when the report scores it itself (no seizure-consensus output), and k of the top-k overlap between methods. 1–200. |
| `MAX_CHANNELS` | `30` | Channels listed per subject and drawn per seizure on the pages; the tables hold all. 5–500. |

## Results on the demo data

**Seizure Onset Localisation and interictal measures, 24 SEEG seizure clips of 6 patients**
(Multi-Expert Seizure Annotation via ieeg-prep, bipolar, 1024 Hz; dynasd, ei, fragility and
consensus from `workflow-epilepsy-ieeg/data/work`; spikes, HFO (`SEGMENT=baseline`) and normative
run by `scripts/run-upstream.sh`):

| Group | Seizures | DynaSD AUC | EI AUC | Fragility AUC | Consensus AUC | median \|onset error\| | median onset error |
|---|---|---|---|---|---|---|---|
| all | 24 | 0.96 | 0.90 | 0.98 | 0.99 | 5.0 s | −3.9 s |
| spontaneous | 18 | 0.97 | 0.90 | 0.99 | 0.99 | 3.9 s | −3.1 s |
| stimulation-induced | 6 | 0.66 | 0.85 | 0.91 | 0.91 | 25.8 s | −25.8 s |

A high AUC is not a precise top of the list: median R-precision (share of expert channels among
the top N, N = number of expert channels) is 0.40 for DynaSD, 0.08 for EI, 0.55 for fragility and
0.67 for the consensus. All 24 onsets fall within the SzCORE tolerance used by seizure-consensus (30 s before to 60 s
after). In stimulation-induced seizures DynaSD's onset lies a median 26 s *before* the expert
onset, likely the stimulation itself; the page says so. Over all channels the methods agree little
(median Spearman ρ DynaSD–EI 0.18, DynaSD–fragility 0.06, EI–fragility 0.02; top-10 overlap 10–40%)
although each puts the expert channels near the top. On the same clips, spike rate separates the
expert onset channels from the rest with a median per-patient AUC of 0.88 (6/6 above 0.5) and
ripple rate 0.81, but these rates come from the non-seizure part of seizure clips (peri-ictal), and
the page says that too. ieeg-normative scores no channel here: the clips have native, not MNI,
coordinates. QC: 162 bad contacts (104 line noise, 58 high line length) and 12 dropped channels
(ECG, scalp) over the 24 clips.

**Interictal Biomarker Mapping, 5 HUP atlas patients** (1, 15, 29, 44, 60; 60 s, 200 Hz, MNI
coordinates, SOZ and resected labels; HFOs not analysed at 200 Hz):

| Measure | vs | median AUC (IQR) | per patient | above 0.5 |
|---|---|---|---|---|
| spike rate | SOZ | 0.54 (0.39–0.58) | 0.35, 0.54, 0.39, 0.73, 0.58 | 3/5 |
| spike rate | resected | 0.54 (0.35–0.65) | 0.34, 0.54, 0.35, 0.67, 0.65 | 3/5 |
| band-power abnormality | SOZ | 0.33 (0.33–0.42) | 0.33, 0.10, 0.42, 0.33, 0.42 | 0/5 |
| band-power abnormality | resected | 0.23 (0.20–0.41) | 0.23, 0.10, 0.41, 0.20, 0.48 | 0/5 |

The abnormality AUCs equal ieeg-normative's own `validation.csv` for these patients. They are below
chance here and near chance (0.48) over all 60 atlas patients in ieeg-normative's
leave-one-patient-out validation; the page reports them as they are and says the measure is
exploratory.

## Runtime

`cpu: 1024`, `memory: 1024`, `computeTypes: [standard, lambda]` (the image serves both; see
`processor/entry.py` and `processor/handler.py`), timeout 15 min. Measured with the image under
amd64 emulation on an M-series Mac (`docker run --memory 1g --cpus 1`, peak from
`/sys/fs/cgroup/memory.peak`, page cache included):

| Run | Peak memory | Wall time |
|---|---|---|
| 24 seizure clips, every input (both workflows; 7 pages, 69 figures) | 200–322 MB | 11–13 s |
| same, as a Lambda function (runtime interface emulator 1.22, `--memory 3008m`) | 253 MB | 15.3 s |
| 5 atlas patients (interictal only) | 156 MB | 3.4–4 s |

The report reads only the per-channel tables, never the signals, so memory grows with channels ×
recordings, not with recording length (the largest input here, `channel_onsets.csv` + `ei.csv` +
`fragility.csv` + `onset_zone.csv` for 2,880 channel-seizures, is < 1 MB). Output: 14 MB for the 24
clips (most of it ieeg-prep's QC plots, copied). Image: 123 MB compressed, ~390 MB unpacked
(`python:3.12.11-slim-bookworm`).

## Running it

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
make test PYTHON=.venv/bin/python     # synthetic fixture (both workflows, both layouts, named method folders, missing inputs, Lambda handler)
make run PYTHON=.venv/bin/python      # Docker over data/fixture/linked/ -> data/output/
make upstream && make run-demo        # demo clips (see sample-input/README.md)
make run-demo-atlas                   # atlas patients
INPUT_DIR=/path/to/inputs OUTPUT_DIR=/path/to/out .venv/bin/python -m processor.main
```

As a Lambda function, with the [runtime interface emulator](https://github.com/aws/aws-lambda-runtime-interface-emulator):

```sh
docker run --rm -p 9000:8080 -v "$PWD/data/fixture/linked:/in:ro" -v "$PWD/aws-lambda-rie:/rie:ro" \
  --entrypoint /rie processor-ieeg-report:dev python3 -m processor.entry
curl -XPOST localhost:9000/2015-03-31/functions/function/invocations \
  -d '{"inputDir": "/in", "outputDir": "/tmp/out", "REPORT_TITLE": "My report"}'
```

## Limitations

- **Not a clinical tool.** The detectors and models upstream have not been validated for surgical
  planning; agreement with expert labels on a curated demo set is not evidence of clinical
  usefulness.
- AUCs from one patient rest on few labelled channels (2–16 in the atlas patients): one AUC is
  uncertain by ±0.1–0.2. The report gives no confidence intervals.
- Expert onset labels are a consensus of visual review on clips chosen around a known onset; scores
  against them measure agreement with clinicians, not outcome. Clips make onset detection easier
  than continuous monitoring.
- Interictal rates from seizure clips are peri-ictal; rates from short clips are samples, not a
  patient's typical rate (they change with sleep, medication and time since a seizure).
- Native-space coordinates (as in the demo clips) are drawn as they are and are not comparable
  across patients; ieeg-normative needs MNI coordinates.
- Channels × time is a heat map only when DynaSD scores over time are given (`channel_scores.csv`,
  not yet written by seizure-dynasd); otherwise each channel's DynaSD onset and the ranked table.
  Fragility over time is not available from seizure-fragility.
- Electrodes are named from contact names (`LA01-LA02` → `LA`); channels named without an electrode
  prefix (the atlas's `ch0001`) form one strip.
- Static PNG figures (no hover); every figure has a table or CSV beside it. Light theme only.

## Notes on the contract (conventions.md)

- `channel_scores.csv` (recording_id, channel, time_s, score) is read when present for the DynaSD
  heat map; it is not in conventions.md and no app writes it yet. Proposed as an optional
  seizure-dynasd output.
- `stim_induced` / `lvfa` in `recordings.csv` are used when present (being added to ieeg-prep);
  the task-name fallback for `stim_induced` is demo-specific and labelled as such on the page.
- `channel_abnormality.csv` from ieeg-normative carries an extra `max_band` column; it is ignored.
- The method apps may write into `dynasd/`, `ei/`, `fragility/` folders of one `methods` port, each
  with its own `provenance.json`: supported (tested).

## Licences

Our code is Apache-2.0 (`LICENSE`). The image bundles Python packages under BSD/MIT/Apache/PSF-style
licences; no GPL code is linked. See `THIRD_PARTY.md`. The demo data: Multi-Expert Seizure
Annotation (CC BY 4.0), HUP Interictal iEEG Atlas (ODC-By 1.0).

## Citations

The report lists, for each upstream app whose `provenance.json` it finds, these papers (from
`processor/citations.py`); `CITATION.cff` holds them with full author lists.

- MNE-Python: Gramfort A, Luessi M, Larson E, Engemann DA, Strohmeier D, Brodbeck C, Goj R, Jas M, Brooks T, Parkkonen L, Hämäläinen M. MEG and EEG data analysis with MNE-Python. Front Neurosci 2013;7:267. doi:10.3389/fnins.2013.00267, PMID 24431986.
- Appelhoff S, Sanderson M, Brooks TL, et al. MNE-BIDS: Organizing electrophysiological data into the BIDS format and facilitating their analysis. J Open Source Softw 2019;4(44):1896. doi:10.21105/joss.01896, PMID 35990374.
- Holdgraf C, Appelhoff S, Bickel S, et al. iEEG-BIDS, extending the Brain Imaging Data Structure specification to human intracranial electrophysiology. Sci Data 2019;6(1):102. doi:10.1038/s41597-019-0105-7, PMID 31239438.
- Janca R, Jezdik P, Cmejla R, et al. Detection of interictal epileptiform discharges using signal envelope distribution modelling. Brain Topogr 2015;28(1):172-183. doi:10.1007/s10548-014-0379-1, PMID 24970691.
- Barkmeier DT, Shah AK, Flanagan D, et al. High inter-reviewer variability of spike detection on intracranial EEG addressed by an automated multi-channel algorithm. Clin Neurophysiol 2012;123(6):1088-1095. doi:10.1016/j.clinph.2011.09.023, PMID 22033028.
- Staba RJ, Wilson CL, Bragin A, Fried I, Engel J Jr. Quantitative analysis of high-frequency oscillations (80-500 Hz) recorded in human epileptic hippocampus and entorhinal cortex. J Neurophysiol 2002;88(4):1743-1752. doi:10.1152/jn.2002.88.4.1743, PMID 12364503.
- Gardner AB, Worrell GA, Marsh E, Dlugos D, Litt B. Human and automated detection of high-frequency oscillations in clinical intracranial EEG recordings. Clin Neurophysiol 2007;118(5):1134-1143. doi:10.1016/j.clinph.2006.12.019, PMID 17382583.
- Cimbálník J, Hewitt A, Worrell G, Stead M. The CS algorithm: A novel method for high frequency oscillation detection in EEG. J Neurosci Methods 2018;293:6-16. doi:10.1016/j.jneumeth.2017.08.023, PMID 28860077.
- Zelmann R, Mari F, Jacobs J, Zijlmans M, Dubeau F, Gotman J. A comparison between detectors of high frequency oscillations. Clin Neurophysiol 2012;123(1):106-116. doi:10.1016/j.clinph.2011.06.006, PMID 21763191.
- Welch P. The use of fast Fourier transform for the estimation of power spectra: A method based on time averaging over short, modified periodograms. IEEE Trans Audio Electroacoust 1967;15(2):70-73. doi:10.1109/TAU.1967.1161901.
- Bernabei JM, Sinha N, Arnold TC, et al. Normative intracranial EEG maps epileptogenic tissues in focal epilepsy. Brain 2022;145(6):1949-1961. doi:10.1093/brain/awab480, PMID 35640886.
- Taylor PN, Papasavvas CA, Owen TW, et al. Normative brain mapping of interictal intracranial EEG to localize epileptogenic tissue. Brain 2022;145(3):939-949. doi:10.1093/brain/awab380, PMID 35075485.
- Wang Y, Schroeder GM, Horsley JJ, et al. Temporal stability of intracranial electroencephalographic abnormality maps for localizing epileptogenic tissue. Epilepsia 2023;64(8):2070-2080. doi:10.1111/epi.17663, PMID 37226553.
- Ojemann WKS, Xu Z, Shi H, et al. Unsupervised seizure annotation and detection with neural dynamic divergence. medRxiv 2026 (preprint). doi:10.64898/2026.02.15.26346325.
- Bartolomei F, Chauvel P, Wendling F. Epileptogenicity of brain structures in human temporal lobe epilepsy: a quantified study from intracerebral EEG. Brain 2008;131(Pt 7):1818-1830. doi:10.1093/brain/awn111, PMID 18556663.
- Li A, Huynh C, Fitzgerald Z, et al. Neural fragility as an EEG marker of the seizure onset zone. Nat Neurosci 2021;24(10):1465-1474. doi:10.1038/s41593-021-00901-w, PMID 34354282.
- Wang J, Karas P, Lesage AC, et al. EZFragility: Compute Neural Fragility for Ictal iEEG Time Series. CRAN 2025. doi:10.32614/CRAN.package.EZFragility.
- Wang J, Lesage AC, Zhou O, et al. Building an Ecosystem of Seizure Localization Methods: Neural Fragility as the First Step. eNeuro 2026;13(3). doi:10.1523/ENEURO.0340-25.2026, PMID 41760551.
- Dan J, Pale U, Amirshahi A, et al. SzCORE: Seizure Community Open-Source Research Evaluation framework for the validation of electroencephalography-based automated seizure detection algorithms. Epilepsia 2025;66(Suppl 3):14-24 (online 2024). doi:10.1111/epi.18113, PMID 39292446.
- Hanley JA, McNeil BJ. The meaning and use of the area under a receiver operating characteristic (ROC) curve. Radiology 1982;143(1):29-36. doi:10.1148/radiology.143.1.7063747, PMID 7063747.
- Hunter JD. Matplotlib: A 2D Graphics Environment. Comput Sci Eng 2007;9(3):90-95. doi:10.1109/MCSE.2007.55.
- Ojemann WK, Zhou D, Armstrong C, Sinha N, Litt B, Conrad E. Multi-Expert Seizure Annotation (version 3) [dataset]. Pennsieve Discover; 2026. doi:10.26275/dely-fzwx (CC BY 4.0).
- Bernabei J, Litt B. HUP Interictal iEEG Atlas (version 1) [dataset]. Pennsieve Discover; 2021. doi:10.26275/lzhy-ox20 (ODC-By 1.0).

How they were verified (2026-10-29): every article DOI against Crossref
(`https://api.crossref.org/works/<DOI>`: title, author list, year, journal), the EZFragility DOI
against Crossref too (registered there as a dataset), the two Discover datasets against DataCite
(`https://api.datacite.org/dois/<DOI>`), and every PMID against PubMed E-utilities (esearch by DOI,
esummary: title, authors, journal, volume, issue, pages). Crossref lists only Gramfort for
MNE-Python; `CITATION.cff` uses PubMed's full 11-author list. Volumes and pages are PubMed's (print).
