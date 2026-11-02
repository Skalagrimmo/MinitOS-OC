# Thin convenience wrapper. The authoritative build logic is tools/build.py
# so the same commands work on hosts without GNU Make (including this
# project's Windows reference environment).
#
# PROFILE may be normal, undef, data-abort, or all (the default).

PYTHON ?= python3
PROFILE ?= all

.PHONY: all build verify platform run repro acceptance clean info disasm

all: build

build:
	$(PYTHON) tools/build.py build --profile $(PROFILE)

verify:
	$(PYTHON) tools/build.py verify --profile $(PROFILE)

platform:
	$(PYTHON) tools/verify_platform.py

run:
	$(PYTHON) tools/run_qemu.py --profile $(PROFILE)

repro:
	$(PYTHON) tools/build.py repro --profile $(PROFILE)

acceptance:
	$(PYTHON) tools/acceptance.py --evidence

clean:
	$(PYTHON) tools/build.py clean

info:
	$(PYTHON) tools/build.py info

disasm:
	$(PYTHON) tools/build.py disasm
