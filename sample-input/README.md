# sample-input

This app reads the *outputs* of the other epilepsy iEEG steps (ieeg-prep, ieeg-spikes, ieeg-hfo,
ieeg-bandpower, ieeg-normative, seizure-dynasd, seizure-ei, seizure-fragility, seizure-consensus),
so there is no public file to download for it directly.

Synthetic fixture (two subjects, every port, every table):

```sh
make fixture      # data/fixture/linked/ and data/fixture/flat/ (gitignored)
make run          # the Docker image over data/fixture/linked/ -> data/output/
```

Real data: fetch the demo data with `workflow-epilepsy-ieeg/scripts/fetch-sample-data.sh`
(Multi-Expert Seizure Annotation, Pennsieve Discover 530, doi:10.26275/dely-fzwx, CC BY 4.0; HUP
Interictal iEEG Atlas, Discover 179, doi:10.26275/lzhy-ox20, ODC-By), run the upstream apps into
`workflow-epilepsy-ieeg/data/work/<step>/` (each repo's `make run-demo`), then

```sh
make upstream        # spikes/hfo/normative of the 24 clips, and the 5 atlas patients through
                     # spikes/hfo/bandpower/normative (atlas prep from processor-ieeg-prep/data/atlas-out,
                     # copied to data/upstream/atlas/ieeg and qc), with the upstream :dev images
make run-demo        # both workflows on the 24 clips  -> data/output-demo/
make run-demo-atlas  # Interictal Biomarker Mapping on the 5 atlas patients -> data/output-atlas/
```

Ports as a workflow delivers them, one folder each:

```
input/ieeg        <- ieeg-prep ieeg        input/qc          <- ieeg-prep qc
input/spikes      <- ieeg-spikes           input/hfo         <- ieeg-hfo
input/bandpower   <- ieeg-bandpower        input/abnormality <- ieeg-normative
input/onsets      <- seizure-dynasd (or put it under methods/)
input/methods/{dynasd,ei,fragility}  <- the seizure method apps (fan-in)
input/onset-zone  <- seizure-consensus
```
