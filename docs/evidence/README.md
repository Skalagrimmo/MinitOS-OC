# Evidence provenance

These files are captured artifacts, not hand-written documentation. They were
produced by the acceptance run recorded below and copied here by
`python tools/acceptance.py --evidence`.

| Item | Value |
|---|---|
| Captured (local time) | 2026-11-02T10:43:47+02:00 |
| Host | Windows 10 Pro, build 19045 |
| Toolchain | xPack GNU Arm Embedded GCC 15.2.1 20251203 |
| QEMU | 11.1.0, `integratorcp` / `arm1136`, 128 MiB RAM |
| Kernel ELF SHA-256 | `5f516ed5fc18cc460f1308fb0256d9b7aa40e78d153c3c2b260788da8d4d5bd1` |
| Flat BIN SHA-256 | `07c98c313a9ced3b0c4e291c9b1185597e60e27dd271016ea7f2b387d17ceb30` |

## File map

| File | Source | Contents |
|---|---|---|
| `acceptance-run.txt` | `build/acceptance.txt` | full console log of the 5-step acceptance sequence |
| `qemu-serial.txt` | `build/serial.log` | raw PL011 UART capture (CRLF line endings) |
| `runtime-evidence.txt` | `build/runtime-evidence.txt` | runtime command, assertions and serial output |
| `qemu-mtree.txt` | `build/qemu-mtree.txt` | live QMP `info mtree` memory map |
| `qemu-platform.txt` | `build/qemu-platform.txt` | machine/CPU/memory-map check log |
| `sha256sums.txt` | `build/SHA256SUMS.txt` | ELF and BIN hashes |
| `repro.txt` | `build/repro.txt` | two clean builds compared byte-for-byte |
| `toolchain.txt` | `build/toolchain.txt` | compiler, linker, Python and host versions |
| `sizes.txt` | `build/sizes.txt` | section size report |
| `readelf-*.txt` | `build/readelf-*.txt` | ELF header, program headers, sections, symbols, attributes |

## Regenerating

From the repository root, with the toolchain and QEMU available:

```sh
python tools/acceptance.py --evidence
```

This rebuilds the kernel, reruns every check, and overwrites these files. The
checked-in copies are a snapshot of one successful run; they are not inputs to
the build.

## Scope

The evidence proves behaviour on the recorded host with QEMU's `integratorcp`
machine. It does not prove execution on a Samsung Galaxy Gio GT-S5660 or any
physical board, real UART timing/baud accuracy, or cross-host reproducibility.
See `../ASSUMPTIONS_AND_LIMITATIONS.md`.
