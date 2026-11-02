# Thin convenience wrapper. The authoritative build logic is tools/build.py
# so the same commands work on hosts without GNU Make (including this
# project's Windows reference environment).

PYTHON ?= python3

.PHONY: all build verify platform run repro acceptance clean info disasm

all: build

build:
	$(PYTHON) tools/build.py build

verify:
	$(PYTHON) tools/build.py verify

platform:
	$(PYTHON) tools/verify_platform.py

run:
	$(PYTHON) tools/run_qemu.py

repro:
	$(PYTHON) tools/build.py repro

acceptance:
	$(PYTHON) tools/acceptance.py --evidence

clean:
	$(PYTHON) tools/build.py clean

info:
	$(PYTHON) tools/build.py info

disasm:
	$(PYTHON) tools/build.py disasm
