"""
The papers behind each step, keyed by app name. Every DOI was checked against
Crossref (articles) or DataCite (datasets) and every PMID against PubMed
E-utilities (title, authors, year, journal, volume, pages); see the README's
Citations section. CITATION.cff lists the same works with their full author
lists.

The methods section lists, for every app whose provenance.json is among the
inputs, its version, parameters and these citations.
"""
from __future__ import annotations

from typing import Any

P: dict[str, dict[str, str]] = {
    "mne": dict(authors="Gramfort A, Luessi M, Larson E, et al.", title="MEG and EEG data analysis with MNE-Python", journal="Front Neurosci", year="2013", where="7:267", doi="10.3389/fnins.2013.00267", pmid="24431986"),
    "mne_bids": dict(authors="Appelhoff S, Sanderson M, Brooks TL, et al.", title="MNE-BIDS: Organizing electrophysiological data into the BIDS format and facilitating their analysis", journal="J Open Source Softw", year="2019", where="4(44):1896", doi="10.21105/joss.01896", pmid="35990374"),
    "ieeg_bids": dict(authors="Holdgraf C, Appelhoff S, Bickel S, et al.", title="iEEG-BIDS, extending the Brain Imaging Data Structure specification to human intracranial electrophysiology", journal="Sci Data", year="2019", where="6(1):102", doi="10.1038/s41597-019-0105-7", pmid="31239438"),
    "janca": dict(authors="Janca R, Jezdik P, Cmejla R, et al.", title="Detection of interictal epileptiform discharges using signal envelope distribution modelling: application to epileptic and non-epileptic intracranial recordings", journal="Brain Topogr", year="2015", where="28(1):172-183", doi="10.1007/s10548-014-0379-1", pmid="24970691"),
    "barkmeier": dict(authors="Barkmeier DT, Shah AK, Flanagan D, et al.", title="High inter-reviewer variability of spike detection on intracranial EEG addressed by an automated multi-channel algorithm", journal="Clin Neurophysiol", year="2012", where="123(6):1088-1095", doi="10.1016/j.clinph.2011.09.023", pmid="22033028"),
    "staba": dict(authors="Staba RJ, Wilson CL, Bragin A, Fried I, Engel J Jr", title="Quantitative analysis of high-frequency oscillations (80-500 Hz) recorded in human epileptic hippocampus and entorhinal cortex", journal="J Neurophysiol", year="2002", where="88(4):1743-1752", doi="10.1152/jn.2002.88.4.1743", pmid="12364503"),
    "gardner": dict(authors="Gardner AB, Worrell GA, Marsh E, Dlugos D, Litt B", title="Human and automated detection of high-frequency oscillations in clinical intracranial EEG recordings", journal="Clin Neurophysiol", year="2007", where="118(5):1134-1143", doi="10.1016/j.clinph.2006.12.019", pmid="17382583"),
    "cimbalnik": dict(authors="Cimbálník J, Hewitt A, Worrell G, Stead M", title="The CS algorithm: A novel method for high frequency oscillation detection in EEG", journal="J Neurosci Methods", year="2018", where="293:6-16", doi="10.1016/j.jneumeth.2017.08.023", pmid="28860077"),
    "zelmann": dict(authors="Zelmann R, Mari F, Jacobs J, Zijlmans M, Dubeau F, Gotman J", title="A comparison between detectors of high frequency oscillations", journal="Clin Neurophysiol", year="2012", where="123(1):106-116", doi="10.1016/j.clinph.2011.06.006", pmid="21763191"),
    "welch": dict(authors="Welch P", title="The use of fast Fourier transform for the estimation of power spectra: A method based on time averaging over short, modified periodograms", journal="IEEE Trans Audio Electroacoust", year="1967", where="15(2):70-73", doi="10.1109/TAU.1967.1161901", pmid=""),
    "bernabei": dict(authors="Bernabei JM, Sinha N, Arnold TC, et al.", title="Normative intracranial EEG maps epileptogenic tissues in focal epilepsy", journal="Brain", year="2022", where="145(6):1949-1961", doi="10.1093/brain/awab480", pmid="35640886"),
    "taylor": dict(authors="Taylor PN, Papasavvas CA, Owen TW, et al.", title="Normative brain mapping of interictal intracranial EEG to localize epileptogenic tissue", journal="Brain", year="2022", where="145(3):939-949", doi="10.1093/brain/awab380", pmid="35075485"),
    "wang2023": dict(authors="Wang Y, Schroeder GM, Horsley JJ, et al.", title="Temporal stability of intracranial electroencephalographic abnormality maps for localizing epileptogenic tissue", journal="Epilepsia", year="2023", where="64(8):2070-2080", doi="10.1111/epi.17663", pmid="37226553"),
    "ojemann": dict(authors="Ojemann WKS, Xu Z, Shi H, et al.", title="Unsupervised seizure annotation and detection with neural dynamic divergence", journal="medRxiv (preprint)", year="2026", where="", doi="10.64898/2026.02.15.26346325", pmid=""),
    "bartolomei": dict(authors="Bartolomei F, Chauvel P, Wendling F", title="Epileptogenicity of brain structures in human temporal lobe epilepsy: a quantified study from intracerebral EEG", journal="Brain", year="2008", where="131(Pt 7):1818-1830", doi="10.1093/brain/awn111", pmid="18556663"),
    "li2021": dict(authors="Li A, Huynh C, Fitzgerald Z, et al.", title="Neural fragility as an EEG marker of the seizure onset zone", journal="Nat Neurosci", year="2021", where="24(10):1465-1474", doi="10.1038/s41593-021-00901-w", pmid="34354282"),
    "ezfragility": dict(authors="Wang J, Karas P, Lesage AC, et al.", title="EZFragility: Compute Neural Fragility for Ictal iEEG Time Series (R package)", journal="CRAN", year="2025", where="", doi="10.32614/CRAN.package.EZFragility", pmid=""),
    "wang2026": dict(authors="Wang J, Lesage AC, Zhou O, et al.", title="Building an Ecosystem of Seizure Localization Methods: Neural Fragility as the First Step", journal="eNeuro", year="2026", where="13(3)", doi="10.1523/ENEURO.0340-25.2026", pmid="41760551"),
    "szcore": dict(authors="Dan J, Pale U, Amirshahi A, et al.", title="SzCORE: Seizure Community Open-Source Research Evaluation framework for the validation of electroencephalography-based automated seizure detection algorithms", journal="Epilepsia", year="2025", where="66(Suppl 3):14-24 (online 2024)", doi="10.1111/epi.18113", pmid="39292446"),
    "hanley": dict(authors="Hanley JA, McNeil BJ", title="The meaning and use of the area under a receiver operating characteristic (ROC) curve", journal="Radiology", year="1982", where="143(1):29-36", doi="10.1148/radiology.143.1.7063747", pmid="7063747"),
    "conrad2023": dict(authors="Conrad EC, Revell AY, Greenblatt AS, et al.", title="Spike patterns surrounding sleep and seizures localize the seizure-onset zone in focal epilepsy", journal="Epilepsia", year="2023", where="64(3):754-768", doi="10.1111/epi.17482", pmid="36484572"),
    "matplotlib": dict(authors="Hunter JD", title="Matplotlib: A 2D Graphics Environment", journal="Comput Sci Eng", year="2007", where="9(3):90-95", doi="10.1109/MCSE.2007.55", pmid=""),
}

DATASETS = {
    "10.26275/dely-fzwx": dict(citation="Ojemann WK, Zhou D, Armstrong C, Sinha N, Litt B, Conrad E. Multi-Expert Seizure Annotation (version 3) [dataset]. Pennsieve Discover; 2026.",
                               licence="CC BY 4.0", match=("Multi-Expert Seizure Annotation",)),
    "10.26275/lzhy-ox20": dict(citation="Bernabei J, Litt B. HUP Interictal iEEG Atlas (version 1) [dataset]. Pennsieve Discover; 2021.",
                               licence="ODC-By 1.0", match=("HUP Interictal iEEG Atlas", "HUP_atlas", "HUPatlas")),
}

# What each step is, in a few words, and the papers it rests on (most important first).
APPS: dict[str, dict[str, Any]] = {
    "processor-ieeg-prep": {"step": "Import, channel QC, montage and filters (BIDS-iEEG derivative)",
                            "cite": ["mne", "mne_bids", "ieeg_bids"]},
    "processor-ieeg-spikes": {"step": "Interictal spike detection", "cite": ["janca", "barkmeier"]},
    "processor-ieeg-hfo": {"step": "High-frequency oscillation detection (ripples, fast ripples)",
                           "cite": ["gardner", "staba", "cimbalnik", "zelmann"]},
    "processor-ieeg-bandpower": {"step": "Band power (Welch)", "cite": ["bernabei", "welch"]},
    "processor-ieeg-normative": {"step": "Band-power abnormality against the HUP normative atlas",
                                 "cite": ["bernabei", "taylor", "wang2023"]},
    "processor-seizure-dynasd": {"step": "Seizure onset and channel recruitment (DynaSD)", "cite": ["ojemann"]},
    "processor-seizure-ei": {"step": "Epileptogenicity Index", "cite": ["bartolomei"]},
    "processor-seizure-fragility": {"step": "Neural fragility", "cite": ["li2021", "ezfragility", "wang2026"]},
    "processor-seizure-consensus": {"step": "Consensus onset zone and scores against expert labels", "cite": ["szcore"]},
    "processor-ieeg-report": {"step": "This report (ROC AUC, rank agreement, figures)", "cite": ["hanley", "matplotlib"]},
}
ORDER = list(APPS)


def reference(key: str) -> dict[str, str]:
    ref = dict(P[key])
    ref["key"] = key
    ref["url"] = f"https://doi.org/{ref['doi']}"
    return ref
