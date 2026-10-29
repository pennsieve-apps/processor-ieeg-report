.PHONY: help test fixture run run-demo run-demo-atlas upstream clean

SERVICE_NAME ?= processor-ieeg-report
PYTHON ?= python3
IMAGE ?= processor-ieeg-report:dev
WORK ?= ../workflow-epilepsy-ieeg/data/work
UPSTREAM ?= data/upstream

.DEFAULT: help

help:
	@echo "Make Help for $(SERVICE_NAME)"
	@echo ""
	@echo "make test           - pytest: synthetic upstream outputs of every step through the processor (no Docker)"
	@echo "make fixture        - write the synthetic fixture to data/fixture/{linked,flat}/"
	@echo "make run            - build the image and run it in Docker over data/fixture/linked/, writing to data/output/"
	@echo "make upstream       - re-create the upstream outputs not in WORK (atlas subjects; spikes/hfo/normative of the clips) in UPSTREAM"
	@echo "make run-demo       - both workflows on the 24 demo seizure clips (WORK + UPSTREAM/clips) into data/output-demo/"
	@echo "make run-demo-atlas - Interictal Biomarker Mapping on 5 HUP atlas patients (UPSTREAM/atlas) into data/output-atlas/"
	@echo "make clean          - remove data/output*/ and data/fixture/"
	@echo ""
	@echo "PYTHON=$(PYTHON) (set PYTHON=.venv/bin/python after pip install -r requirements-dev.txt)"

test:
	$(PYTHON) -m pytest -q tests

fixture:
	$(PYTHON) -m tests.make_fixture data/fixture --layout both

run: clean fixture
	mkdir -p data/output
	docker compose -f docker-compose.yml down --remove-orphans
	docker compose -f docker-compose.yml build
	docker compose -f docker-compose.yml up --exit-code-from processor
	docker compose -f docker-compose.yml down --remove-orphans
	@echo "--- outputs:"
	@find data/output -type f | sort

upstream:
	./scripts/run-upstream.sh all

# Each port mounted on its own: INPUT_DIR/<port>/ as a workflow delivers it.
run-demo:
	docker build --platform linux/amd64 -t $(IMAGE) .
	rm -rf data/output-demo && mkdir -p data/output-demo
	docker run --rm --platform linux/amd64 --memory 1g --env-file dev.env \
		-v "$(abspath $(WORK))/prep/ieeg":/data/input/ieeg:ro -v "$(abspath $(WORK))/prep/qc":/data/input/qc:ro \
		-v "$(abspath $(UPSTREAM))/clips/spikes":/data/input/spikes:ro -v "$(abspath $(UPSTREAM))/clips/hfo":/data/input/hfo:ro \
		-v "$(abspath $(WORK))/bandpower":/data/input/bandpower:ro -v "$(abspath $(UPSTREAM))/clips/abnormality":/data/input/abnormality:ro \
		-v "$(abspath $(WORK))/dynasd":/data/input/methods/dynasd:ro \
		-v "$(abspath $(WORK))/ei":/data/input/methods/ei:ro -v "$(abspath $(WORK))/fragility":/data/input/methods/fragility:ro \
		-v "$(abspath $(WORK))/consensus":/data/input/onset-zone:ro \
		-v "$(CURDIR)/data/output-demo":/data/output $(IMAGE)

run-demo-atlas:
	docker build --platform linux/amd64 -t $(IMAGE) .
	rm -rf data/output-atlas && mkdir -p data/output-atlas
	docker run --rm --platform linux/amd64 --memory 1g --env-file dev.env \
		-v "$(abspath $(UPSTREAM))/atlas/ieeg":/data/input/ieeg:ro -v "$(abspath $(UPSTREAM))/atlas/qc":/data/input/qc:ro \
		-v "$(abspath $(UPSTREAM))/atlas/spikes":/data/input/spikes:ro -v "$(abspath $(UPSTREAM))/atlas/hfo":/data/input/hfo:ro \
		-v "$(abspath $(UPSTREAM))/atlas/bandpower":/data/input/bandpower:ro \
		-v "$(abspath $(UPSTREAM))/atlas/abnormality":/data/input/abnormality:ro \
		-v "$(CURDIR)/data/output-atlas":/data/output $(IMAGE)

clean:
	rm -rf data/output data/output-demo data/output-atlas data/fixture
