# Third-party components

Our code (`processor/`, `tests/`) is Apache-2.0 (`LICENSE`). The Docker image bundles:

| Component | Version | Licence |
|---|---|---|
| Debian (bookworm, via `python:3.12.11-slim-bookworm`) | 12 | various free licences (per package, `/usr/share/doc/*/copyright`) |
| CPython | 3.12.11 | PSF License |
| pandas | 2.2.3 | BSD-3-Clause |
| NumPy | 2.2.6 | BSD-3-Clause (bundled OpenBLAS: BSD-3-Clause) |
| Matplotlib | 3.10.3 | Matplotlib License (PSF-based, BSD-compatible); bundles DejaVu fonts (Bitstream Vera / public domain) |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| contourpy | 1.4.0 | BSD-3-Clause |
| cycler | 0.12.1 | BSD-3-Clause |
| fonttools | 4.68.0 | MIT |
| kiwisolver | 1.5.1 | BSD-3-Clause |
| packaging | 26.3 | Apache-2.0 or BSD-2-Clause |
| Pillow | 13.0.0 | MIT-CMU (HPND) |
| pyparsing | 3.3.3 | MIT |
| python-dateutil | 3.0.0 | Apache-2.0 or BSD-3-Clause |
| pytz | 2026.5 | MIT |
| six | 1.17.0 | MIT |
| tzdata | 2026.6 | Apache-2.0 |
| awslambdaric | 2.2.1 | Apache-2.0 |
| simplejson (awslambdaric dependency) | 4.2.0 | MIT or AFL-2.1 |

No GPL code is linked. The report copies the QC figures of ieeg-prep into its output;
those are data, under the licence of the dataset they show.
