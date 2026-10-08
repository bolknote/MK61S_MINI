#!/usr/bin/env python3
"""Real ARM compiler/VM/INPUT flow, poisoning each evicted APP image.

The native loader is a fixture here. Its actual generic flow algorithm is
covered by run_app_flow_tests.sh; this gate covers ARM packing and APP policy.
"""
import argparse
import json
import math
import struct
import tempfile
from pathlib import Path

from run_language_vm_arm_tests import package
from run_language_vm_overlay_arm_tests import OverlayMachine
from run_portable_system_arm_tests import Elf, ROOT, run

FLOW_INFO, FLOW_STEP, FLOW_MAGIC = 3, 4, 0x31574C46
COMPILER_CONTEXT_SIZE = 240
REQUEST_VERSION = 5
LANGUAGE_FLOW_MAGIC = 0x32564C46

class FlowMachine(OverlayMachine):
    def load(self, packed):
        if packed[0] != "application": return super().load(packed)
        self.kind, variants, self.image_size, self.entry, self.crc = packed
        self.base, self.image = variants[self.address_index]
        self.uc.mem_write(self.pool_begin, b"\xCD" * (self.pool_end - self.pool_begin))
        self.uc.mem_write(self.base, self.image)
        self.uc.ctl_remove_cache(self.pool_begin, self.pool_end)
        assert self.call(0, self.api, self.crc, 4) == 0


def user_calls(m, packed):
    context, step = m.input + 768, m.input + 1024
    m.uc.mem_write(context, bytes(64))
    for inode, phase, result in ((42, 0, 0), (43, 2, 0), (42, 1, 42)):
        m.load(packed)
        assert m.call(FLOW_INFO) == FLOW_MAGIC
        m.uc.mem_write(step, bytes(48)); m.put(step, 48, 1, context, 64)
        m.uc.mem_write(step + 16, struct.pack("<HBBI", inode, 4, 0, phase))
        m.put(step + 40, result, 0)
        assert m.call(FLOW_STEP, step) == 1
        action, resume, result, status = m.words(step + 32, 4)
        assert not status
        if inode == 43: assert action == 3 and result == 42
        elif phase == 0:
            assert action == 2 and resume == 1
            assert struct.unpack("<HBBI", m.uc.mem_read(step + 24, 8)) == (43, 4, 0, 2)
        else: assert action == 4 and result == 42


def reject_other_language(m, packed, kind, other_language):
    assert COMPILER_CONTEXT_SIZE == 240
    context, step, values = m.input + 768, m.input + 1120, m.workspace + 4688
    m.partitioned = True
    m.load(packed)
    m.uc.mem_write(values, bytes(3504))
    m.uc.mem_write(context, bytes(240)); m.put(context, LANGUAGE_FLOW_MAGIC, 0)
    m.put(context + 76, values)
    m.uc.mem_write(context + 234, bytes((other_language,)))
    m.uc.mem_write(step, bytes(48)); m.put(step, 48, 1, context, 240)
    m.uc.mem_write(step + 16, struct.pack("<HBBI", 0xFFFF, kind, 0, 0x100))
    trace_size = len(m.trace)
    assert m.call(FLOW_STEP, step) == 0, "compiler accepted the opposite-language context"
    assert len(m.trace) == trace_size, "wrong-language context reached a resident service"
    m.uc.mem_write(context+234,bytes((1 if kind==2 else 2,)))
    m.put(context,0x31564C46)
    assert m.call(FLOW_STEP,step)==0,"compiler accepted a legacy same-sized context"
    assert len(m.trace)==trace_size,"legacy context reached a resident service"


def execute(m, packages, language, source, answers, cancelled=False, mode=1, compiler_flow=True):
    compiler = "tinybasic" if language == 1 else "focal"
    variables, compile_request, execution, context, step, output = [
        m.input + offset for offset in (128, 512, 640, 768, 1120, 1280)]
    state, array, bytecode = m.workspace, m.workspace + 5112, m.workspace + 1520
    m.partitioned = True
    m.uc.mem_write(m.workspace + 4688, b"\x5A" * 3504)
    m.files[42] = (3 if language == 1 else 2, "FLOWTEST", source)
    command = 0x20A if language == 1 else 0x106  # BASIC status takes its mode from arg1.
    if compiler_flow:
        context_size = COMPILER_CONTEXT_SIZE
        values = m.workspace + 4688
        variables, array = values + 8 + (language - 1)*208, values + 424
        compact = context_size == 240
        compile_request, execution = context + (8 if compact else 184), context + (184 if compact else 216)
        plan = context + (48 if compact else 264)
        m.uc.mem_write(values, bytes(3504)); m.uc.mem_write(values + 4, b"\xFF"*4)
        m.uc.mem_write(context, bytes(context_size)); m.put(context, LANGUAGE_FLOW_MAGIC, command)
        m.put(context + (76 if compact else 292), values, command, 42, mode if language == 1 else 0)
        m.uc.mem_write(context + (234 if compact else 308), bytes((language,)))
        current = (2 if language == 1 else 1, 0x100)
        image, length = None, 0
    else:
        context_size = 184
        m.load(packages[compiler])
        m.uc.mem_write(compile_request, bytes(40)); m.put(compile_request, 40, REQUEST_VERSION, 0, 6144)
        m.uc.mem_write(compile_request + 32, b"\x01")  # same owned-resource policy as APP flow
        assert m.call(command, 42, mode if language == 1 else 0, compile_request) == (1 if language == 1 else 0)
        wire = bytes(m.uc.mem_read(compile_request, 40))
        assert wire[16] == 0 and wire[30] == 1
        length = struct.unpack_from("<H", wire, 18)[0]; assert length <= 768
        m.put(compile_request + 8, output, length)
        assert m.call(0x704, 0, 0, compile_request) == 1
        image = bytes(m.uc.mem_read(output, length)); m.uc.mem_write(bytecode, image)
        m.uc.mem_write(variables, bytes(208)); m.uc.mem_write(array, bytes(3080))
        m.uc.mem_write(state, bytes(1520)); m.uc.mem_write(state + 1506, bytes((language,)))
        m.uc.mem_write(execution, bytes(48))
        m.put(execution, 48, REQUEST_VERSION, bytecode, length, variables, array, 385 if language == 1 else 0)
        m.uc.mem_write(execution + 28, bytes((mode, 0, 0, 0)))
        m.uc.mem_write(context, bytes(context_size)); m.put(context, LANGUAGE_FLOW_MAGIC, command)
        m.put(context + 8, 24, REQUEST_VERSION, execution, state, context + 32, 0)
        current = (11, 0)
    parents, loaded_kind = [], None
    previous_result = previous_status = consumed = 0
    for transfer in range(100):
        kind, phase = current
        m.stage = f"flow-{kind}-{phase}"
        if kind:
            # HOST reserve leaves the compiler/source in place. A real loader
            # cache hit must not initialize it again before EMIT.
            if kind != loaded_kind:
                m.load(packages[{1:"focal", 2:"tinybasic", 10:"language-vm", 11:"language-input"}[kind]])
                loaded_kind = kind
            assert m.call(FLOW_INFO) == FLOW_MAGIC
        retry_input = phase == 4 and m.uc.mem_read(context + 48 + 36, 1)[0] != 0
        if kind == 11 and (phase == 3 or retry_input):
            if cancelled: m.keys = [m.mapping[39]]
            else:
                assert consumed < len(answers)
                m.input_keys(answers[consumed]); consumed += 1
        if kind == 11 and phase == 6: m.keys = [m.mapping[39]]
        m.uc.mem_write(step, bytes(48))
        m.put(step, 48, 1, context, context_size)
        m.uc.mem_write(step + 16, struct.pack("<HBBI", 0xFFFF, kind, 0, phase))
        m.put(step + 40, previous_result, previous_status)
        if kind:
            resource_reads = sum(x and x[0] == "file_read" for x in m.trace)
            assert m.call(FLOW_STEP, step) == 1
            if kind in (10, 11):
                assert sum(x and x[0] == "file_read" for x in m.trace) == resource_reads, "runtime read its source"
        elif phase == 0x100:  # Generic reserve fixture, exact measured size.
            length, prefix = m.words(plan, 2)
            assert 0 < length <= 768 and prefix == 1520
            m.put(plan + 8, output)
            m.put(step + 32, 3, 0, 1, 0)
        else:  # Generic commit fixture; tail-transfer directly to cold APP.
            assert phase == 0x101 and m.words(plan + 8, 1)[0] == output
            image = bytes(m.uc.mem_read(output, length))
            m.uc.mem_write(bytecode, image)
            m.put(plan + 8, bytecode, m.workspace, 4688)
            m.uc.mem_write(step + 24, bytes(m.uc.mem_read(plan + 20, 8)))
            m.put(step + 32, 1, 0, 0, 0)
        assert m.words(step, 4) == (48, 1, context, context_size)
        action, resume, result, status = m.words(step + 32, 4)
        if action in (1, 2):
            file_id, next_kind, flags, next_phase = struct.unpack("<HBBI", m.uc.mem_read(step + 24, 8))
            assert file_id == 0xFFFF and not flags and next_kind in (0, 1, 2, 10, 11)
            if action == 2:
                assert len(parents) < 4
                parents.append((kind, resume))
            current = (next_kind, next_phase)
            previous_result = previous_status = 0
        elif action == 3 and parents:
            current = parents.pop(); previous_result, previous_status = result, status
        elif action in (3, 4):
            assert not status, (current, status)
            assert image is not None
            assert bytes(m.uc.mem_read(bytecode, length)) == image
            m.last_bytecode = image
            low, high = struct.unpack("<II", m.uc.mem_read(variables, 8))
            number = struct.unpack("<i", struct.pack("<I", low))[0] if high == 0x7FFC0001 else struct.unpack("<d", m.uc.mem_read(variables, 8))[0]
            return number, m.uc.mem_read(execution + 36, 1)[0], consumed, transfer + 1
        else: raise AssertionError((current, action))
    raise AssertionError("endless flow")


def main():
    global COMPILER_CONTEXT_SIZE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-elf", type=Path, required=True)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--report-file", type=Path)
    parser.add_argument("--user-app", type=Path)
    parser.add_argument("--legacy-app", type=Path)
    parser.add_argument("--vm-profile", choices=("core", "local", "libm"), default="core")
    parser.add_argument("--compiler-context", choices=(240, 312), type=int, default=240)
    parser.add_argument("--specialized", action="store_true")
    args = parser.parse_args()
    COMPILER_CONTEXT_SIZE = args.compiler_context
    elf = Elf(args.resident_elf)
    if args.vm_profile == "libm":
        elf.require_libm_math(args.resident_elf)
    with tempfile.TemporaryDirectory(prefix="mk61-flow-arm-") as directory:
        work = Path(directory); reader = work / "reader"
        run(["c++", "-std=c++17", "-O2", "-I" + str(ROOT / "code"),
             ROOT / "tests/portable_app_format_self_test.cpp",
             ROOT / "code/loadable_module_format.cpp", ROOT / "code/zx0.cpp", "-o", reader])
        packages = {kind: package(reader, args.system / name, elf, work, kind)
                    for kind, name in (("tinybasic", "BASIC.APP"), ("focal", "FOCAL.APP"),
                                       ("language-vm", "LANGVM.APP"), ("language-input", "LANGIN.APP"))}
        user = package(reader, args.user_app, elf, work, "application") if args.user_app else None
        legacy = package(reader, args.legacy_app, elf, work, "application") if args.legacy_app else None
        traces = []
        for address in range(3):
            if args.specialized:
                reject_other_language(OverlayMachine(args.resident_elf, True, address), packages["tinybasic"], 2, 2)
                reject_other_language(OverlayMachine(args.resident_elf, True, address), packages["focal"], 1, 1)
            if user: user_calls(FlowMachine(args.resident_elf, True, address), user)
            if legacy:
                machine = FlowMachine(args.resident_elf, True, address); machine.load(legacy)
                assert machine.call(FLOW_INFO) == 0
            cases = [
                (1, b"10 S=0\n20 FOR I=1 TO 3\n30 GOSUB 100\n40 NEXT I\n50 A=S;END\n100 INPUT @(I)\n110 S=S+@(I);RETURN\n", ["10", "1/0", "20", "30"], 60),
                (2, b"1.10 D 2\n1.20 E\n2.10 F I=1,3; A X\n2.20 S A=X\n", ["10", "20", "30"], 30),
                (1, b"10 DATA 3,4\n20 READ B;INPUT C;READ D\n30 A=B+C+D\n", ["5"], 12),
                (1, b"10 A=.1+.2\n20 GOSUB 100;A=A+10;END\n100 A=A+1;RETURN\n", [], 11.3),
                (1, b"10 PRINT 'RAM STRING';'RAM STRING'\n20 INPUT 'RAM PROMPT',A\n30 A=A+2\n", ["5"], 7),
                (2, b"1.10 PRINT \"RAM FOCAL\"\n1.20 ASK A\n1.30 EXIT\n", ["7"], 7)]
            # The fixture does not model the calculator's CORE numeric CPU.
            # Ordinary double arithmetic is real ARM code; transcendental
            # probes require real resident LIBM or the APP's local float math.
            if args.vm_profile != "core":
                cases.append((2, b"1.10 S A=SQRT(2)\n1.20 E\n", [],
                              math.sqrt(2) if args.vm_profile == "libm" else
                              struct.unpack("<f", struct.pack("<f", math.sqrt(2)))[0]))
            for language, source, answers, expected in cases:
                machine = OverlayMachine(args.resident_elf, True, address)
                actual, error, consumed, transfers = execute(machine, packages, language, source, answers)
                assert math.isclose(actual, expected, rel_tol=1e-14) and not error, (actual, error, machine.trace[-20:])
                old_machine = OverlayMachine(args.resident_elf, True, address)
                old_actual, old_error, *_ = execute(old_machine, packages, language, source, answers, compiler_flow=False)
                assert math.isclose(old_actual, actual, rel_tol=1e-14) and not old_error
                assert old_machine.last_bytecode == machine.last_bytecode, "flow inflated/changed bytecode"
                traces.append({"address": address, "language": language, "transfers": transfers,
                               "inputs": consumed, "stack_peaks": machine.stage_peaks})
            for mode, expected in ((1, 13), (0, 0)):
                machine = OverlayMachine(args.resident_elf, True, address)
                assert execute(machine, packages, 1, b"10 INPUT A\n20 A=999\n", [], True, mode)[1] == expected
        machine = OverlayMachine(args.resident_elf, True, 0)
        assert execute(machine, packages, 1, b"10 A=42\n", [], compiler_flow=False)[:2] == (42, 0)
        report = {"status": "PASS", "vm_profile": args.vm_profile,
                  "compiler_context_bytes": COMPILER_CONTEXT_SIZE,
                  "specialized_language_guards": args.specialized, "runs": traces,
                  "legacy_language_contexts_rejected":args.specialized,
                  "note": "Real ARM APP policy and relocation; native loader/allocator remain fixtures."}
        if args.vm_profile == "core":
            report["note"] += " CORE transcendental CPU is not modeled; covered by run_mk_math_tests.sh, not this emulation."
        if args.report_file:
            args.report_file.parent.mkdir(parents=True, exist_ok=True)
            args.report_file.write_text(json.dumps(report, indent=2) + "\n")
        print("APP flow ARM: compiler sizing/reserve/emit/commit, unchanged bytecode, BASIC/FOCAL INPUT, retry, DATA, cancel, legacy runtime context, 3 addresses PASS")


if __name__ == "__main__": main()
