# Evidence provenance — K2

These files are captured K2 artifacts, not hand-written documentation. They
were produced by the acceptance run recorded below and copied here by
`python tools/acceptance.py --evidence`.

| Item | Value |
|---|---|
| Captured (local time) | 2026-11-02T11:28:16+02:00 |
| Host | Windows 10 Pro, build 19045 |
| Toolchain | xPack GNU Arm Embedded GCC 15.2.1 20251203 |
| QEMU | 11.1.0, `integratorcp` / `arm1136`, 128 MiB RAM |
| Profiles | `normal`, `undef`, `data-abort` |

Artifact hashes:

| Profile | ELF SHA-256 | BIN SHA-256 |
|---|---|---|
| `normal` | `176d1acc5b21432d9cc8f227f1572576c63b9e1038a4f0575a7ee35d863ea63c` | `4ab2ca63f5c5a8e923d293209da93ae39a1d53b7b4df5add27ba248676bcd2db` |
| `undef` | `23e8aafa191e731f17bf227d7af1fcd9ad77940e9eb2602ca12d75e898dc2273` | `ad23fd42f4cbd5bffa1fdf7eadfe3362f302913251eebec35232c62d89122e2b` |
| `data-abort` | `306bf5bc6509cbdcc856bbe353e115cc93d1330f0e67135d381e6c9e35b9330a` | `792e6e91e7287e220b83200849ed1c09d09ce6350a27c4aae5a13614e1a47ba7` |

## File map

| File | Source | Contents |
|---|---|---|
| `acceptance-run.txt` | `build/acceptance.txt` | full console log of the 5-step acceptance sequence |
| `normal-uart.log` | `build/run/normal/serial.log` | raw PL011 UART capture, normal profile |
| `undef-uart.log` | `build/run/undef/serial.log` | raw PL011 UART capture, Undefined Instruction |
| `data-abort-uart.log` | `build/run/data-abort/serial.log` | raw PL011 UART capture, Data Abort |
| `normal-runtime.txt` | `build/run/normal/runtime-evidence.txt` | runtime command, checks and serial output |
| `undef-runtime.txt` | `build/run/undef/runtime-evidence.txt` | runtime command, checks and serial output |
| `data-abort-runtime.txt` | `build/run/data-abort/runtime-evidence.txt` | runtime command, checks and serial output |
| `elf-check.log` | `build/elf-check.txt` | all per-profile ELF structural checks |
| `qemu-platform.log` | `build/qemu-platform.txt` | machine/CPU/memory-map check log |
| `qemu-mtree.txt` | `build/qemu-mtree.txt` | live QMP `info mtree` memory map |
| `disassembly-vectors.txt` | `build/normal/disassembly-vectors.txt` | 32-byte low vector table |
| `disassembly-startup.txt` | `build/normal/disassembly-startup.txt` | `_start` / `reset_handler` |
| `disassembly-handlers.txt` | `build/normal/disassembly-handlers.txt` | exception entry stubs and C handlers |
| `disassembly-tests-undef.txt` | `build/undef/disassembly-tests.txt` | real `udf #0` plus test driver |
| `disassembly-tests-data-abort.txt` | `build/data-abort/disassembly-tests.txt` | `add #1; ldr` pair plus test driver |
| `disassembly-full.txt` | `build/normal/disassembly.txt` | full normal-profile disassembly |
| `linker-map.txt` | `build/normal/minitos-k2.map` | linker map |
| `symbols.txt` | `build/normal/symbols.txt` | symbol table |
| `memory-usage.txt` | `build/normal/memory-usage.txt` | linker memory-region usage |
| `sha256sums.txt` | `build/SHA256SUMS.txt` | per-profile ELF and BIN hashes |
| `repro-hashes.txt` | `build/repro.txt` | two clean builds compared byte-for-byte |
| `toolchain.txt` | `build/toolchain.txt` | compiler, linker, Python and host versions |
| `sizes.txt` | `build/sizes-all.txt` | section size report |
| `readelf-*.txt` | `build/normal/readelf-*.txt` | ELF header, program headers, sections, symbols, attributes |

## Archived K1 evidence

`k1/` contains the original K1 evidence restored from Git tag `k1-baseline`
(commit `6964e66`). It is kept separate so a K2 acceptance run cannot
overwrite it. K1 did not implement active exception handling, per-mode stacks
or the low vector table; those results belong to K2.

## Regenerating

From the repository root, with the toolchain and QEMU available:

```sh
python tools/acceptance.py --evidence
```

This rebuilds every profile, reruns every check, and overwrites the K2 files in
this directory. The checked-in copies are a snapshot of one successful run;
they are not inputs to the build. The `k1/` subdirectory is not touched.

## Scope

The evidence proves behaviour on the recorded host with QEMU's `integratorcp`
machine. It does not prove execution on a Samsung Galaxy Gio GT-S5660 or any
physical board, real UART timing/baud accuracy, real-silicon exception
behaviour, or cross-host reproducibility. See
`../ASSUMPTIONS_AND_LIMITATIONS.md`.
