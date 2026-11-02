#!/usr/bin/env python3
"""Structural checker for the MinitOS K2 ELF image.

This script parses ELF32 directly with the Python standard library. It does
not shell out to readelf, so the checks are stable across host toolchains and
can run anywhere Python 3 is available.

K2-specific checks include:
  - a 32-byte low vector table at physical/virtual address 0, in its own
    executable PT_LOAD segment;
  - ELF entry point and reset_handler at 0x00010000, separate from the table;
  - all eight vector slots branch to defined entry symbols;
  - SVC/UND/ABT/IRQ/FIQ stack symbols with fixed sizes and 8-byte alignment;
  - the compiled exception-frame size/alignment;
  - real UDF and unaligned-LDR instruction sequences in the fault profiles;
  - absence of undefined symbols and accidental libc/libgcc helpers;
  - a flat binary matching the allocated ELF load image.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

EXPECTED_VECTOR_BASE = 0x00000000
EXPECTED_VECTOR_SIZE = 32
EXPECTED_IMAGE_BASE = 0x00010000
EXPECTED_RAM_BASE = 0x00000000
EXPECTED_RAM_SIZE = 128 * 1024 * 1024
IMAGE_BUDGET = 64 * 1024

EXPECTED_STACK_SIZES = {
    "svc": 16 * 1024,
    "und": 4 * 1024,
    "abt": 4 * 1024,
    "irq": 2 * 1024,
    "fiq": 1 * 1024,
}

EXPECTED_VECTORS = [
    ("reset_handler", 0x00),
    ("undef_entry", 0x04),
    ("svc_entry", 0x08),
    ("prefetch_entry", 0x0C),
    ("data_abort_entry", 0x10),
    ("reserved_entry", 0x14),
    ("irq_entry", 0x18),
    ("fiq_entry", 0x1C),
]

REQUIRED_MESSAGES = [
    b"MINITOS KERNEL STARTED\x00",
    b"K2 EXCEPTION CAPTURED\x00",
    b"EXCEPTION: UNDEFINED INSTRUCTION\x00",
    b"EXCEPTION: DATA ABORT\x00",
]

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
SHF_WRITE = 0x1
EF_ARM_EABI_MASK = 0xFF000000
EF_ARM_EABI_VER5 = 0x05000000
EF_ARM_ABI_FLOAT_HARD = 0x00000400

ELF_HEADER = struct.Struct("<HHIIIIIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIIIIIII")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
SYMBOL = struct.Struct("<IIIBBH")

UDF_WORD = 0xE7F000F0
ADD_R0_R0_1 = 0xE2800001
LDR_R1_R0 = 0xE5901000


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
    def __init__(self, path: Path, profile: str) -> None:
        self.path = path
        self.profile = profile
        self.data = path.read_bytes()
        self.checks: list[tuple[str, bool, str]] = []
        self.sections: dict[str, Section] = {}
        self.raw_sections: list[Section] = []
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
            self.raw_sections.append(section)
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

    def section_containing(self, address: int) -> Section | None:
        for sec in self.raw_sections:
            if (sec.sh_flags & SHF_ALLOC) and sec.sh_size > 0:
                if sec.sh_addr <= address < sec.sh_addr + sec.sh_size:
                    return sec
        return None

    def symbol_bytes(self, name: str) -> bytes:
        sym = self.symbol(name)
        sec = self.section_containing(sym.st_value)
        if sec is None:
            raise CheckFailure(f"symbol {name} is not inside an allocated section")
        offset = sym.st_value - sec.sh_addr
        return sec.bytes(self.data)[offset:offset + sym.st_size]

    def symbol_u32(self, name: str) -> int:
        raw = self.symbol_bytes(name)
        if len(raw) < 4:
            raise CheckFailure(f"symbol {name} is smaller than 32 bits")
        return struct.unpack_from("<I", raw, 0)[0]

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

        # --- entry point and low vector table -----------------------------
        self.check("entry point is 0x00010000",
                   self.entry == EXPECTED_IMAGE_BASE,
                   f"e_entry=0x{self.entry:08x}")

        vectors = section(".vectors")
        text = section(".text")
        start = symbol("_start")
        reset = symbol("reset_handler")
        kernel = symbol("kernel_main")

        self.check("_start is at 0x00010000",
                   start.st_value == EXPECTED_IMAGE_BASE,
                   f"_start=0x{start.st_value:08x}")
        self.check("_start is a global function",
                   start.type == 2 and start.bind == 1,
                   f"type={start.type} bind={start.bind}")
        self.check("reset_handler is at _start",
                   reset.st_value == start.st_value,
                   f"reset_handler=0x{reset.st_value:08x}")
        self.check("reset_handler is a function", reset.type == 2)
        self.check("kernel_main is a function", kernel.type == 2)

        self.check(".vectors is at address 0", vectors.sh_addr == EXPECTED_VECTOR_BASE,
                   f"addr=0x{vectors.sh_addr:08x}")
        self.check(".vectors is executable and allocated",
                   (vectors.sh_flags & (SHF_ALLOC | SHF_EXECINSTR))
                   == (SHF_ALLOC | SHF_EXECINSTR),
                   f"flags=0x{vectors.sh_flags:x}")
        self.check(".vectors is exactly 32 bytes",
                   vectors.sh_size == EXPECTED_VECTOR_SIZE,
                   f"size={vectors.sh_size}")
        self.check(".text starts at the image base",
                   text.sh_addr == EXPECTED_IMAGE_BASE,
                   f"addr=0x{text.sh_addr:08x}")
        self.check("_start and reset_handler live in .text",
                   text.sh_addr <= start.st_value < text.sh_addr + text.sh_size)
        self.check("kernel_main lives in .text",
                   text.sh_addr <= kernel.st_value < text.sh_addr + text.sh_size)

        vector_data = vectors.bytes(self.data)
        if len(vector_data) == EXPECTED_VECTOR_SIZE:
            words = struct.unpack("<8I", vector_data)
            for index, (name, offset) in enumerate(EXPECTED_VECTORS):
                address = vectors.sh_addr + offset
                target = arm_branch_target(words[index], address)
                expected = symbol(name).st_value
                self.check(f"vector {offset:#04x} branches to {name}",
                           target == expected,
                           f"target=0x{target:08x} expected=0x{expected:08x}")
                self.check(f"vector {offset:#04x} has a defined target",
                           target >= 0)
        else:
            self.check("vector table is readable", False,
                       f"got {len(vector_data)} bytes")

        # --- section layout ------------------------------------------------
        rodata = section(".rodata")
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
        for message in REQUIRED_MESSAGES:
            self.check(f".rodata contains {message[:-1].decode()!r}",
                       message in rodata.bytes(self.data))
        self.check(".bss is NOBITS", bss.sh_type == SHT_NOBITS,
                   f"sh_type={bss.sh_type}")
        self.check(".stack is NOBITS", stack.sh_type == SHT_NOBITS,
                   f"sh_type={stack.sh_type}")

        self.check(".text follows the vector table",
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

        # Nothing allocated may hide in the reserved 0x20..0xFFFF gap.
        hidden = [sec.name for sec in self.raw_sections
                  if (sec.sh_flags & SHF_ALLOC) and sec.sh_size > 0
                  and sec.name != ".vectors"
                  and sec.sh_addr < EXPECTED_IMAGE_BASE]
        self.check("reserved low memory contains no other allocated section",
                   not hidden, ", ".join(hidden))

        # --- linker symbols and stacks -------------------------------------
        bss_start = symbol("__bss_start__")
        bss_end = symbol("__bss_end__")
        image_start = symbol("__image_start__")
        image_end = symbol("__image_end__")
        vectors_start = symbol("__vectors_start__")
        vectors_end = symbol("__vectors_end__")

        self.check("__vectors_start__ is 0",
                   vectors_start.st_value == EXPECTED_VECTOR_BASE,
                   f"0x{vectors_start.st_value:08x}")
        self.check("__vectors_end__ is 32",
                   vectors_end.st_value == EXPECTED_VECTOR_SIZE,
                   f"0x{vectors_end.st_value:08x}")
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
        self.check("__image_start__ is 0x00010000",
                   image_start.st_value == EXPECTED_IMAGE_BASE,
                   f"0x{image_start.st_value:08x}")
        self.check("__image_start__ is the start of .text",
                   image_start.st_value == text.sh_addr,
                   f"0x{image_start.st_value:08x}")
        self.check("__image_end__ is the end of .stack",
                   image_end.st_value == stack.sh_addr + stack.sh_size,
                   f"0x{image_end.st_value:08x}")
        self.check("image fits the 64 KiB K2 budget",
                   image_end.st_value - image_start.st_value <= IMAGE_BUDGET,
                   f"size={image_end.st_value - image_start.st_value} bytes")
        self.check("image fits emulated RAM",
                   image_end.st_value <= EXPECTED_RAM_BASE + EXPECTED_RAM_SIZE,
                   f"end=0x{image_end.st_value:08x}")

        expected_stack_top = None
        for mode, size in EXPECTED_STACK_SIZES.items():
            bottom = symbol(f"__{mode}_stack_bottom__")
            top = symbol(f"__{mode}_stack_top__")
            self.check(f"{mode.upper()} stack has the expected size",
                       top.st_value - bottom.st_value == size,
                       f"size={top.st_value - bottom.st_value} expected={size}")
            self.check(f"{mode.upper()} stack bottom is 8-byte aligned",
                       bottom.st_value % 8 == 0,
                       f"0x{bottom.st_value:08x}")
            self.check(f"{mode.upper()} stack top is 8-byte aligned",
                       top.st_value % 8 == 0,
                       f"0x{top.st_value:08x}")
            if mode == "svc":
                self.check("__stack_bottom__ aliases the SVC stack",
                           symbol("__stack_bottom__").st_value == bottom.st_value)
                self.check("__stack_top__ aliases the SVC stack",
                           symbol("__stack_top__").st_value == top.st_value)
                self.check("__stack_size__ is 16 KiB",
                           symbol("__stack_size__").st_value ==
                           EXPECTED_STACK_SIZES["svc"])
            expected_stack_top = top.st_value

        self.check("stack regions are contiguous and ordered",
                   self.symbol("__svc_stack_top__").st_value ==
                   self.symbol("__und_stack_bottom__").st_value
                   and self.symbol("__und_stack_top__").st_value ==
                   self.symbol("__abt_stack_bottom__").st_value
                   and self.symbol("__abt_stack_top__").st_value ==
                   self.symbol("__irq_stack_bottom__").st_value
                   and self.symbol("__irq_stack_top__").st_value ==
                   self.symbol("__fiq_stack_bottom__").st_value)
        self.check("image ends at the top of the last stack",
                   expected_stack_top == image_end.st_value,
                   f"stack top=0x{expected_stack_top:08x} "
                   f"image end=0x{image_end.st_value:08x}")
        self.check("__k2_sctlr_boot is in .bss",
                   self.symbol("__k2_sctlr_boot").st_shndx == bss.index)

        # --- compiled exception frame ABI ----------------------------------
        frame_size = self.symbol_u32("k2_exception_frame_size")
        frame_align = self.symbol_u32("k2_exception_frame_align")
        self.check("compiled exception frame is 72 bytes",
                   frame_size == 72, f"value={frame_size}")
        self.check("compiled exception frame is 8-byte aligned",
                   frame_align == 8, f"value={frame_align}")

        # --- program headers ----------------------------------------------
        loads = [ph for ph in self.program_headers if ph[0] == PT_LOAD]
        self.check("at least three PT_LOAD segments", len(loads) >= 3,
                   f"count={len(loads)}")
        self.check("no PT_DYNAMIC / PT_INTERP",
                   all(ph[0] not in (PT_DYNAMIC, PT_INTERP)
                       for ph in self.program_headers))

        vector_loads = [ph for ph in loads
                        if ph[2] == EXPECTED_VECTOR_BASE
                        and ph[3] == EXPECTED_VECTOR_BASE]
        text_loads = [ph for ph in loads if ph[3] == EXPECTED_IMAGE_BASE]
        self.check("vector table has its own PT_LOAD at address 0",
                   len(vector_loads) == 1, f"count={len(vector_loads)}")
        if vector_loads:
            ph = vector_loads[0]
            self.check("vector segment is exactly 32 bytes on disk",
                       ph[4] == EXPECTED_VECTOR_SIZE,
                       f"p_filesz={ph[4]}")
            self.check("vector segment is exactly 32 bytes in memory",
                       ph[5] == EXPECTED_VECTOR_SIZE,
                       f"p_memsz={ph[5]}")
            self.check("vector segment is executable",
                       (ph[6] & 1) != 0, f"p_flags=0x{ph[6]}")
        self.check("kernel text has a PT_LOAD at 0x00010000",
                   len(text_loads) >= 1, f"count={len(text_loads)}")

        if loads:
            self.check("first PT_LOAD starts at address 0",
                       loads[0][3] == EXPECTED_VECTOR_BASE,
                       f"p_paddr=0x{loads[0][3]:08x}")
            self.check("all segments have p_vaddr == p_paddr",
                       all(ph[2] == ph[3] for ph in loads))
            self.check("all segments have p_memsz >= p_filesz",
                       all(ph[5] >= ph[4] for ph in loads))
            self.check("all segments fit emulated RAM",
                       all(ph[3] + ph[5] <= EXPECTED_RAM_BASE + EXPECTED_RAM_SIZE
                           for ph in loads))
            self.check("no PT_LOAD segments overlap",
                       all(a[3] + a[5] <= b[3] or b[3] + b[5] <= a[3]
                           for i, a in enumerate(loads)
                           for b in loads[i + 1:]))
            self.check("entry point is inside a loaded segment",
                       any(ph[2] <= self.entry < ph[2] + ph[5] for ph in loads))
            self.check("some PT_LOAD is writable",
                       any((ph[6] & 2) != 0 for ph in loads))

        # --- profile-specific fault generators -----------------------------
        if self.profile == "normal":
            self.check("normal profile contains the K2 IDLE marker",
                       b"K2 IDLE\x00" in rodata.bytes(self.data))
            self.check("normal profile does not contain a fault test selector",
                       b"K2 test: undefined\x00" not in rodata.bytes(self.data)
                       and b"K2 test: data-abort\x00" not in rodata.bytes(self.data))
        elif self.profile == "undef":
            self.check("undef profile contains the test selector",
                       b"K2 test: undefined\x00" in rodata.bytes(self.data))
            raw = self.symbol_bytes("k2_trigger_undef")
            words = [struct.unpack_from("<I", raw, offset)[0]
                     for offset in range(0, len(raw) - 3, 4)]
            self.check("k2_trigger_undef contains a real UDF instruction",
                       UDF_WORD in words,
                       f"words={[f'0x{w:08x}' for w in words]}")
        elif self.profile == "data-abort":
            self.check("data-abort profile contains the test selector",
                       b"K2 test: data-abort\x00" in rodata.bytes(self.data))
            raw = self.symbol_bytes("k2_trigger_data_abort")
            words = [struct.unpack_from("<I", raw, offset)[0]
                     for offset in range(0, len(raw) - 3, 4)]
            pair = any(words[index] == ADD_R0_R0_1
                       and words[index + 1] == LDR_R1_R0
                       for index in range(len(words) - 1))
            self.check("k2_trigger_data_abort does add #1 then LDR [r0]",
                       pair, f"words={[f'0x{w:08x}' for w in words]}")
            probe = symbol("k2_alignment_probe")
            self.check("alignment probe is 16-byte aligned",
                       probe.st_value % 16 == 0,
                       f"0x{probe.st_value:08x}")
            self.check("alignment probe is four words",
                       probe.st_size == 16, f"size={probe.st_size}")

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
        self.check("flat binary starts at the vector base",
                   start == EXPECTED_VECTOR_BASE, f"start=0x{start:08x}")
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
            print(f"ELF CHECK [{self.profile}]: FAIL "
                  f"({failed} failed / {len(self.checks)} checks)")
            return 1
        print(f"ELF CHECK [{self.profile}]: PASS ({len(self.checks)} checks)")
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
    parser = argparse.ArgumentParser(description="MinitOS K2 ELF checker")
    parser.add_argument("elf", help="kernel ELF")
    parser.add_argument("--bin", help="flat binary")
    parser.add_argument("--profile", default="normal",
                        choices=["normal", "undef", "data-abort"])
    args = parser.parse_args(argv)

    elf_path = Path(args.elf)
    bin_path = Path(args.bin) if args.bin else None

    if not elf_path.is_file():
        print(f"ELF CHECK: FAIL: missing {elf_path}", file=sys.stderr)
        return 2
    if bin_path is not None and not bin_path.is_file():
        print(f"ELF CHECK: FAIL: missing {bin_path}", file=sys.stderr)
        return 2

    try:
        checker = Checker(elf_path, args.profile)
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
