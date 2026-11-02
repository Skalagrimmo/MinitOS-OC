#!/usr/bin/env python3
"""Structural checker for the MinitOS K1 ELF image.

This script parses ELF32 directly with the Python standard library. It does
not shell out to readelf, so the checks are stable across host toolchains and
can run anywhere Python 3 is available.

Checks include:
  - ELF32 / little-endian / EM_ARM / EABI5 / soft-float flags
  - entry point and vector table (first instruction branches to reset_handler)
  - loadable segments, physical addresses and RAM bounds
  - required linker symbols and section layout
  - BSS / stack sizes, 8-byte stack alignment and image budget
  - absence of undefined symbols (no accidental libc/libgcc dependency)
  - the literal "MINITOS KERNEL STARTED" is present in .rodata
  - optional flat binary matches the allocated ELF image byte-for-byte
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

EXPECTED_IMAGE_BASE = 0x00010000
EXPECTED_STACK_SIZE = 16 * 1024
EXPECTED_RAM_BASE = 0x00000000
EXPECTED_RAM_SIZE = 128 * 1024 * 1024
IMAGE_BUDGET = 64 * 1024
EXPECTED_MESSAGE = b"MINITOS KERNEL STARTED\x00"

EM_ARM = 40
ET_EXEC = 2
PT_LOAD = 1
PT_DYNAMIC = 2
PT_INTERP = 3
SHT_SYMTAB = 2
SHT_NOBITS = 8
SHN_UNDEF = 0
SHF_ALLOC = 0x2
SHF_EXECINSTR = 0x4
EF_ARM_EABI_MASK = 0xFF000000
EF_ARM_EABI_VER5 = 0x05000000
EF_ARM_ABI_FLOAT_HARD = 0x00000400

ELF_HEADER = struct.Struct("<HHIIIIIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIIIIIII")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
SYMBOL = struct.Struct("<IIIBBH")


class CheckFailure(RuntimeError):
    pass


class Section:
    def __init__(self, data: bytes, index: int, shstrtab: bytes, header) -> None:
        (self.name_offset, self.sh_type, self.sh_flags, self.sh_addr,
         self.sh_offset, self.sh_size, self.sh_link, self.sh_info,
         self.sh_addralign, self.sh_entsize) = header
        self.index = index
        self.name = c_string(shstrtab, self.name_offset)

    def bytes(self, data: bytes) -> bytes:
        if self.sh_type == SHT_NOBITS:
            return b""
        return data[self.sh_offset:self.sh_offset + self.sh_size]


class Symbol:
    def __init__(self, st_name, st_value, st_size, st_info, st_other, st_shndx,
                 name: str) -> None:
        self.st_name = st_name
        self.st_value = st_value
        self.st_size = st_size
        self.st_info = st_info
        self.st_other = st_other
        self.st_shndx = st_shndx
        self.name = name

    @property
    def bind(self) -> int:
        return self.st_info >> 4

    @property
    def type(self) -> int:
        return self.st_info & 0x0F


def c_string(blob: bytes, offset: int) -> str:
    if offset >= len(blob):
        return ""
    end = blob.find(b"\x00", offset)
    if end < 0:
        end = len(blob)
    return blob[offset:end].decode("utf-8", errors="replace")


class Checker:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        self.checks: list[tuple[str, bool, str]] = []
        self.sections: dict[str, Section] = {}
        self.program_headers: list[tuple[int, ...]] = []
        self.symbols: dict[str, Symbol] = {}
        self.entry = 0
        self.e_flags = 0
        self.header = None
        self._parse()

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        self.checks.append((name, bool(condition), detail))
        return bool(condition)

    def _parse(self) -> None:
        if len(self.data) < 52:
            raise CheckFailure("file is too small to be an ELF32 image")
        if self.data[:4] != b"\x7fELF":
            raise CheckFailure("missing ELF magic")

        self.header = ELF_HEADER.unpack_from(self.data, 16)
        (self.e_type, self.e_machine, self.e_version, self.entry,
         e_phoff, e_shoff, self.e_flags, e_ehsize, e_phentsize,
         e_phnum, e_shentsize, e_shnum, e_shstrndx) = self.header

        if e_phoff + e_phnum * e_phentsize > len(self.data):
            raise CheckFailure("program header table is outside the file")
        for index in range(e_phnum):
            offset = e_phoff + index * e_phentsize
            self.program_headers.append(PROGRAM_HEADER.unpack_from(self.data, offset))

        if e_shoff + e_shnum * e_shentsize > len(self.data):
            raise CheckFailure("section header table is outside the file")

        raw_sections = []
        for index in range(e_shnum):
            offset = e_shoff + index * e_shentsize
            raw_sections.append(SECTION_HEADER.unpack_from(self.data, offset))

        if e_shstrndx >= len(raw_sections):
            raise CheckFailure("invalid section-name string table index")
        shstr_header = raw_sections[e_shstrndx]
        shstr = self.data[shstr_header[4]:shstr_header[4] + shstr_header[5]]

        for index, header in enumerate(raw_sections):
            section = Section(self.data, index, shstr, header)
            if section.name:
                self.sections[section.name] = section

        symtab = self.sections.get(".symtab")
        if symtab is None:
            raise CheckFailure("no .symtab; the kernel image must not be stripped")
        if symtab.sh_link >= len(raw_sections):
            raise CheckFailure("invalid .symtab string table link")
        strtab_header = raw_sections[symtab.sh_link]
        strtab = self.data[strtab_header[4]:strtab_header[4] + strtab_header[5]]

        entsize = symtab.sh_entsize or SYMBOL.size
        for index in range(symtab.sh_size // entsize):
            offset = symtab.sh_offset + index * entsize
            st_name, st_value, st_size, st_info, st_other, st_shndx = \
                SYMBOL.unpack_from(self.data, offset)
            name = c_string(strtab, st_name)
            if name:
                self.symbols[name] = Symbol(st_name, st_value, st_size,
                                            st_info, st_other, st_shndx, name)

    def section(self, name: str) -> Section:
        section = self.sections.get(name)
        if section is None:
            raise CheckFailure(f"missing required section {name}")
        return section

    def symbol(self, name: str) -> Symbol:
        symbol = self.symbols.get(name)
        if symbol is None:
            raise CheckFailure(f"missing required symbol {name}")
        return symbol

    def check_all(self) -> None:
        section = self.section
        symbol = self.symbol

        # --- ELF identity -------------------------------------------------
        self.check("ELF magic", self.data[:4] == b"\x7fELF")
        self.check("ELF class is 32-bit", self.data[4] == 1,
                   f"EI_CLASS={self.data[4]}")
        self.check("ELF data is little-endian", self.data[5] == 1,
                   f"EI_DATA={self.data[5]}")
        self.check("ELF version is 1", self.data[6] == 1)
        self.check("ELF type is ET_EXEC", self.e_type == ET_EXEC,
                   f"e_type={self.e_type}")
        self.check("ELF machine is EM_ARM", self.e_machine == EM_ARM,
                   f"e_machine={self.e_machine}")
        self.check("EABI version is 5",
                   (self.e_flags & EF_ARM_EABI_MASK) == EF_ARM_EABI_VER5,
                   f"e_flags=0x{self.e_flags:08x}")
        self.check("soft-float ABI (no hard-float flag)",
                   (self.e_flags & EF_ARM_ABI_FLOAT_HARD) == 0,
                   f"e_flags=0x{self.e_flags:08x}")
        self.check("header sizes are ELF32",
                   self.header[7] == 52 and self.header[8] == 32
                   and self.header[10] == 40,
                   f"ehsize={self.header[7]} phentsize={self.header[8]} "
                   f"shentsize={self.header[10]}")

        # --- entry point and vectors --------------------------------------
        self.check("entry point is 0x00010000", self.entry == EXPECTED_IMAGE_BASE,
                   f"e_entry=0x{self.entry:08x}")

        start = symbol("_start")
        reset = symbol("reset_handler")
        kernel = symbol("kernel_main")
        self.check("_start is at image base", start.st_value == EXPECTED_IMAGE_BASE,
                   f"_start=0x{start.st_value:08x}")
        self.check("_start is a global function", start.type == 2 and start.bind == 1,
                   f"type={start.type} bind={start.bind}")
        self.check("_start covers the 8-word vector table", start.st_size == 32,
                   f"size={start.st_size}")
        self.check("reset_handler is a function", reset.type == 2)
        self.check("kernel_main is a function", kernel.type == 2)

        vectors = section(".vectors")
        text = section(".text")
        self.check(".vectors is at image base", vectors.sh_addr == EXPECTED_IMAGE_BASE,
                   f"addr=0x{vectors.sh_addr:08x}")
        self.check(".vectors is executable and allocated",
                   (vectors.sh_flags & (SHF_ALLOC | SHF_EXECINSTR))
                   == (SHF_ALLOC | SHF_EXECINSTR),
                   f"flags=0x{vectors.sh_flags:x}")
        self.check(".vectors is exactly 32 bytes", vectors.sh_size == 32,
                   f"size={vectors.sh_size}")
        self.check("reset_handler lives in .text",
                   text.sh_addr <= reset.st_value < text.sh_addr + text.sh_size)
        self.check("kernel_main lives in .text",
                   text.sh_addr <= kernel.st_value < text.sh_addr + text.sh_size)

        vector_data = vectors.bytes(self.data)
        if len(vector_data) == 32:
            words = struct.unpack("<8I", vector_data)
            target = arm_branch_target(words[0], vectors.sh_addr)
            self.check("reset vector branches to reset_handler",
                       target == reset.st_value,
                       f"vector target=0x{target:08x} "
                       f"reset_handler=0x{reset.st_value:08x}")
            for index in range(1, 8):
                address = vectors.sh_addr + index * 4
                target = arm_branch_target(words[index], address)
                self.check(f"vector {index} is a self-loop trap",
                           target == address,
                           f"vector target=0x{target:08x} address=0x{address:08x}")
        else:
            self.check("vector table is readable", False,
                       f"got {len(vector_data)} bytes")

        # --- section layout ------------------------------------------------
        rodata = section(".rodata")
        # A kernel with no mutable initialised data legitimately has no .data
        # output section. Treat it as an empty range at the end of .rodata.
        data_section = self.sections.get(".data")
        data_addr = (rodata.sh_addr + rodata.sh_size
                     if data_section is None else data_section.sh_addr)
        data_size = 0 if data_section is None else data_section.sh_size
        bss = section(".bss")
        stack = section(".stack")

        self.check(".text is executable and non-empty",
                   text.sh_size > 0
                   and (text.sh_flags & (SHF_ALLOC | SHF_EXECINSTR))
                   == (SHF_ALLOC | SHF_EXECINSTR))
        self.check(".rodata contains the K1 banner",
                   EXPECTED_MESSAGE in rodata.bytes(self.data))
        self.check(".bss is NOBITS", bss.sh_type == SHT_NOBITS,
                   f"sh_type={bss.sh_type}")
        self.check(".stack is NOBITS", stack.sh_type == SHT_NOBITS,
                   f"sh_type={stack.sh_type}")

        self.check(".text follows .vectors",
                   text.sh_addr >= vectors.sh_addr + vectors.sh_size)
        self.check(".rodata follows .text",
                   rodata.sh_addr >= text.sh_addr + text.sh_size)
        self.check(".data is absent or follows .rodata",
                   data_addr >= rodata.sh_addr + rodata.sh_size,
                   f".data addr=0x{data_addr:08x}")
        self.check(".bss follows .data",
                   bss.sh_addr >= data_addr + data_size)
        self.check(".stack follows .bss",
                   stack.sh_addr >= bss.sh_addr + bss.sh_size)

        bss_start = symbol("__bss_start__")
        bss_end = symbol("__bss_end__")
        stack_bottom = symbol("__stack_bottom__")
        stack_top = symbol("__stack_top__")
        image_start = symbol("__image_start__")
        image_end = symbol("__image_end__")

        self.check("__bss_start__ matches .bss",
                   bss_start.st_value == bss.sh_addr,
                   f"symbol=0x{bss_start.st_value:08x} "
                   f"section=0x{bss.sh_addr:08x}")
        self.check("__bss_end__ matches .bss end",
                   bss_end.st_value == bss.sh_addr + bss.sh_size,
                   f"symbol=0x{bss_end.st_value:08x} "
                   f"section end=0x{bss.sh_addr + bss.sh_size:08x}")
        self.check("BSS size is positive and 8-byte aligned",
                   bss.sh_size > 0 and bss.sh_size % 8 == 0,
                   f"size={bss.sh_size}")
        self.check("__stack_bottom__ matches .stack",
                   stack_bottom.st_value == stack.sh_addr,
                   f"symbol=0x{stack_bottom.st_value:08x} "
                   f"section=0x{stack.sh_addr:08x}")
        self.check("__stack_top__ matches .stack end",
                   stack_top.st_value == stack.sh_addr + stack.sh_size,
                   f"symbol=0x{stack_top.st_value:08x} "
                   f"section end=0x{stack.sh_addr + stack.sh_size:08x}")
        self.check("stack is 16 KiB", stack.sh_size == EXPECTED_STACK_SIZE,
                   f"size={stack.sh_size}")
        self.check("stack top is 8-byte aligned", stack_top.st_value % 8 == 0,
                   f"top=0x{stack_top.st_value:08x}")
        self.check("__image_start__ is image base",
                   image_start.st_value == EXPECTED_IMAGE_BASE,
                   f"0x{image_start.st_value:08x}")
        self.check("__image_end__ is end of .stack",
                   image_end.st_value == stack.sh_addr + stack.sh_size,
                   f"0x{image_end.st_value:08x}")
        self.check("image fits the 64 KiB K1 budget",
                   image_end.st_value - image_start.st_value <= IMAGE_BUDGET,
                   f"size={image_end.st_value - image_start.st_value} bytes")
        self.check("image fits emulated RAM",
                   image_end.st_value <= EXPECTED_RAM_BASE + EXPECTED_RAM_SIZE,
                   f"end=0x{image_end.st_value:08x}")

        # --- program headers ----------------------------------------------
        loads = [ph for ph in self.program_headers if ph[0] == PT_LOAD]
        self.check("at least two PT_LOAD segments", len(loads) >= 2,
                   f"count={len(loads)}")
        self.check("no PT_DYNAMIC / PT_INTERP",
                   all(ph[0] not in (PT_DYNAMIC, PT_INTERP)
                       for ph in self.program_headers))
        if loads:
            self.check("first PT_LOAD starts at image base",
                       loads[0][3] == EXPECTED_IMAGE_BASE,
                       f"p_paddr=0x{loads[0][3]:08x}")
            self.check("first PT_LOAD is executable",
                       (loads[0][6] & 1) != 0, f"p_flags=0x{loads[0][6]}")
            self.check("all segments have p_vaddr == p_paddr",
                       all(ph[2] == ph[3] for ph in loads))
            self.check("all segments have p_memsz >= p_filesz",
                       all(ph[5] >= ph[4] for ph in loads))
            self.check("all segments fit emulated RAM",
                       all(ph[3] + ph[5] <= EXPECTED_RAM_BASE + EXPECTED_RAM_SIZE
                           for ph in loads))
            self.check("entry point is inside a loaded segment",
                       any(ph[2] <= self.entry < ph[2] + ph[5] for ph in loads))
            self.check("some PT_LOAD is writable",
                       any((ph[6] & 2) != 0 for ph in loads))

        # --- symbol hygiene ------------------------------------------------
        undefined = [name for name, sym in self.symbols.items()
                     if sym.st_shndx == SHN_UNDEF]
        self.check("no undefined symbols", not undefined,
                   ", ".join(sorted(undefined)))
        helpers = [name for name in undefined
                   if name.startswith("__aeabi_") or name in
                   ("memcpy", "memset", "memmove", "memcmp", "strlen")]
        self.check("no implicit libc/libgcc helpers", not helpers,
                   ", ".join(sorted(helpers)))
        self.check(".comment was discarded", ".comment" not in self.sections)

    def check_binary(self, bin_path: Path) -> None:
        loadable = [sec for sec in self.sections.values()
                    if (sec.sh_flags & SHF_ALLOC) and sec.sh_type != SHT_NOBITS
                    and sec.sh_size > 0]
        if not loadable:
            self.check("flat binary source sections", False, "no loadable sections")
            return
        start = min(sec.sh_addr for sec in loadable)
        end = max(sec.sh_addr + sec.sh_size for sec in loadable)
        expected = bytearray(end - start)
        for sec in loadable:
            offset = sec.sh_addr - start
            expected[offset:offset + sec.sh_size] = sec.bytes(self.data)

        actual = bin_path.read_bytes()
        self.check("flat binary starts at image base", start == EXPECTED_IMAGE_BASE,
                   f"start=0x{start:08x}")
        self.check("flat binary size matches allocated sections",
                   len(actual) == len(expected),
                   f"actual={len(actual)} expected={len(expected)}")
        if actual == bytes(expected):
            self.check("flat binary content matches ELF load image", True)
        else:
            mismatch = next((index for index, (a, b) in
                             enumerate(zip(actual, expected)) if a != b),
                            min(len(actual), len(expected)))
            self.check("flat binary content matches ELF load image", False,
                       f"first difference at offset 0x{mismatch:x}")

    def report(self) -> int:
        failed = 0
        for name, ok, detail in self.checks:
            if ok:
                print(f"[PASS] {name}")
            else:
                failed += 1
                suffix = f": {detail}" if detail else ""
                print(f"[FAIL] {name}{suffix}")

        print()
        if failed:
            print(f"ELF CHECK: FAIL ({failed} failed / {len(self.checks)} checks)")
            return 1
        print(f"ELF CHECK: PASS ({len(self.checks)} checks)")
        return 0


def arm_branch_target(word: int, address: int) -> int:
    """Decode an ARM B/BL immediate branch target, or return -1."""
    if (word >> 24) != 0xEA:
        return -1
    immediate = word & 0x00FFFFFF
    if immediate & 0x00800000:
        immediate -= 0x01000000
    return (address + 8 + immediate * 4) & 0xFFFFFFFF


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: elfcheck.py <kernel.elf> [--bin <kernel.bin>]",
              file=sys.stderr)
        return 2

    elf_path = Path(args[0])
    bin_path = None
    if "--bin" in args:
        index = args.index("--bin")
        if index + 1 >= len(args):
            print("--bin requires a path", file=sys.stderr)
            return 2
        bin_path = Path(args[index + 1])

    if not elf_path.is_file():
        print(f"ELF CHECK: FAIL: missing {elf_path}", file=sys.stderr)
        return 2
    if bin_path is not None and not bin_path.is_file():
        print(f"ELF CHECK: FAIL: missing {bin_path}", file=sys.stderr)
        return 2

    try:
        checker = Checker(elf_path)
        checker.check_all()
        if bin_path is not None:
            checker.check_binary(bin_path)
    except (CheckFailure, struct.error) as exc:
        print(f"ELF CHECK: FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"ELF file: {elf_path}")
    return checker.report()


if __name__ == "__main__":
    raise SystemExit(main())
