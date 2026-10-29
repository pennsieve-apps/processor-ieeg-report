#!/usr/bin/env bash
# Re-creates the upstream outputs the report is developed against, with the
# upstream apps' :dev images (build them with each repo's `make run-demo` first).
# Writes under data/upstream/{clips,atlas}/<port>/. Sequential, --memory limited.
# The seizure methods and their consensus are read from WORK (dynasd, ei, fragility, consensus).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
APPS="$(cd "$HERE/.." && pwd)"
WORK="${WORK:-$APPS/workflow-epilepsy-ieeg/data/work}"
ATLAS_MAT="${ATLAS_MAT:-$APPS/workflow-epilepsy-ieeg/data/atlas/HUP_atlas_final.mat}"
UP="$HERE/data/upstream"
run() { # name image outdir envfile extra-docker-args...
  local name=$1 image=$2 out=$3 envf=$4; shift 4
  rm -rf "$out"; mkdir -p "$out"
  local t0=$(date +%s)
  docker run --rm --platform linux/amd64 --memory 3g --env-file "$envf" "$@" -v "$out":/data/output "$image" > "$out.log" 2>&1 || echo "FAILED $name"
  echo "$name: $(( $(date +%s) - t0 )) s"
}
target=${1:-all}
if [[ $target == all || $target == atlas ]]; then
  A="$UP/atlas"
  # The atlas patients as an ieeg-prep derivative: workflow-epilepsy-ieeg/scripts/atlas-to-bids.py,
  # then ieeg-prep (its builder's run is in processor-ieeg-prep/data/atlas-out).
  ATLAS_PREP="${ATLAS_PREP:-$APPS/processor-ieeg-prep/data/atlas-out}"
  if [[ ! -d "$A/ieeg" ]]; then
    mkdir -p "$A" && cp -R "$ATLAS_PREP/ieeg" "$ATLAS_PREP/qc" "$A/"
  fi
  run atlas-spikes processor-ieeg-spikes:dev "$A/spikes" "$APPS/processor-ieeg-spikes/dev.env" -e THREADS=2 -v "$A/ieeg":/data/input:ro
  run atlas-hfo processor-ieeg-hfo:dev "$A/hfo" "$APPS/processor-ieeg-hfo/dev.env" -v "$A/ieeg":/data/input:ro
  run atlas-bandpower processor-ieeg-bandpower:dev "$A/bandpower" "$APPS/processor-ieeg-bandpower/dev.env" -v "$A/ieeg":/data/input:ro
  run atlas-normative processor-ieeg-normative:dev "$A/abnormality" "$APPS/processor-ieeg-normative/dev.env" \
    -v "$A/bandpower":/data/input/features:ro -v "$A/ieeg":/data/input/ieeg:ro -v "$ATLAS_MAT":/data/input/reference/HUP_atlas_final.mat:ro
fi
if [[ $target == all || $target == clips ]]; then
  C="$UP/clips"
  run clips-spikes processor-ieeg-spikes:dev "$C/spikes" "$APPS/processor-ieeg-spikes/dev.env" -e THREADS=2 -v "$WORK/prep/ieeg":/data/input:ro
  run clips-normative processor-ieeg-normative:dev "$C/abnormality" "$APPS/processor-ieeg-normative/dev.env" \
    -v "$WORK/bandpower":/data/input/features:ro -v "$WORK/prep/ieeg":/data/input/ieeg:ro -v "$ATLAS_MAT":/data/input/reference/HUP_atlas_final.mat:ro
  run clips-hfo processor-ieeg-hfo:dev "$C/hfo" "$APPS/processor-ieeg-hfo/dev.env" -e SEGMENT=baseline -e THREADS=2 -v "$WORK/prep/ieeg":/data/input:ro
fi
