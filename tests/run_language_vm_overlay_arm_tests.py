#!/usr/bin/env python3
"""Real hot/cold ARM APPs, with every previous native image poisoned.

The loader/keyboard/storage are fixtures; editor, parser, EABI, VM and math
execute real machine code. This is not a device latency or live-heap result.
"""
import argparse
import json
import math
import struct
import tempfile
from pathlib import Path

from run_language_vm_arm_tests import package
from run_portable_system_arm_tests import Machine, Elf, ROOT, run
from unicorn.arm_const import UC_ARM_REG_SP

STATE_SIZE = 1584
VM_INFO, VM_RUN, INPUT = 0x702, 0x700, 0x703
VALIDATE, FINISH = 0x705, 0x706
GENERATION = 14


def decode_number(data):
    low, high = struct.unpack('<II', data)
    return struct.unpack('<i',struct.pack('<I',low))[0] if high == 0x7FFC0001 else struct.unpack('<d',data)[0]


def encode_number(number):
    if number == int(number) and -2147483648 <= number <= 2147483647 and not (number == 0 and math.copysign(1,number) < 0):
        return struct.pack('<II',int(number)&0xFFFFFFFF,0x7FFC0001)
    return struct.pack('<d',number)


class OverlayMachine(Machine):
    def __init__(self, *args):
        super().__init__(*args)
        self.stage = "startup"
        self.stage_peaks = {}
        self.partitioned = False
        self.workspace_requests = []

    def hook(self, uc, address, size, ctx):
        sp = uc.reg_read(UC_ARM_REG_SP)
        self.stage_peaks[self.stage] = max(self.stage_peaks.get(self.stage, 0), self.stack_top-sp)
        return super().hook(uc, address, size, ctx)

    def system(self, op, a, b, c, p):
        if op == 13 and a == 0 and self.partitioned:
            # Model the v5 prefix service, not the native allocator. Old
            # full-workspace restores are forbidden during the transaction.
            if c > (4176 if GENERATION>=14 else 4688) or (self.depth and self.owner != b): return 0
            crc = self.words(p+44,1)[0]
            fresh = self.owner != b or self.stamps.get(b) != crc
            if fresh: self.uc.mem_write(self.workspace,bytes(c))
            self.owner = b; self.depth += 1; self.stamps[b] = crc
            self.leases[p] = (a,b); self.workspace_requests.append((b,c))
            self.put(p+32,self.workspace,c,fresh)
            return 1
        if op == 14 and self.partitioned and self.leases.get(p,(None,None))[0] == 0:
            self.leases.pop(p); self.put(p+32,0,0); self.depth-=1
            return 1
        if op == 1 and a == 17:  # DISPLAY_FLOW_TEXT; panel wrapping remains a fixture
            text, length, _, rows, flags = self.words(p, 5)
            self.lines.append(bytes(self.uc.mem_read(text, length)).decode("cp1251"))
            return min(rows, max(1 if flags & 2 else 0, (length+15)//16))
        return super().system(op, a, b, c, p)

    def load(self, package):
        self.kind, variants, self.image_size, self.entry, self.crc = package
        self.base, self.image = variants[self.address_index]
        self.uc.mem_write(self.pool_begin, b"\xCD" * (self.pool_end-self.pool_begin))
        self.uc.mem_write(self.base, self.image)
        self.uc.ctl_remove_cache(self.pool_begin, self.pool_end)
        kind = {"focal": 1, "tinybasic": 2, "language-vm": 10,
                "language-input": 11}[self.kind]
        assert self.call(0, self.api, self.crc, kind) == 0, self.trace[-12:]

    def input_keys(self, text):
        mapping = self.mapping
        # Actual resident default-key editor for digits and arithmetic keys.
        operators = {".": mapping[9], "+": mapping[6], "-": mapping[7],
                     "*": mapping[2], "/": mapping[3], "^": mapping[4]}
        self.keys = []
        for c in text:
            if c.isdigit(): self.keys.append(mapping[10+int(c)])
            elif c in "()": self.keys += [mapping[28], mapping[36 if c == "(" else 37]]
            else: self.keys.append(operators[c])
        self.keys.append(mapping[38])


def execute(m, packages, language, source, answers, cancelled=False, mode=1, edit_after_error=False):
    v14 = GENERATION >= 14
    v13 = GENERATION >= 13
    v12 = GENERATION >= 12
    v11 = GENERATION >= 11
    v10 = GENERATION >= 10
    v9 = GENERATION >= 9
    v8 = GENERATION >= 8
    version = 8 if v14 else 7 if v13 else 6 if v12 else 5 if v11 else 4 if v10 else 3 if v9 else 2 if v8 else 1
    state_size = 1584 if v14 else 1520 if v8 else 1504
    control_size = 688 if v14 else 624 if v8 else 616
    stack_offset = control_size
    output_offset = stack_offset+768
    input_value_offset = output_offset+96
    prompt_offset_field = input_value_offset+12
    language_offset = prompt_offset_field+6
    cancelled_offset = language_offset+(5 if v14 else 4 if v8 else 3)
    execution_size = 48 if v8 else 44
    result_offset = 36 if v8 else 32
    v4 = GENERATION >= 4
    v5 = GENERATION >= 5
    v6 = GENERATION >= 6
    vm_magic, input_magic = ((0x3B564D4C, 0x3B494D4C) if v13 else
                             (0x3A564D4C, 0x3A494D4C) if v12 else
                             (0x39564D4C, 0x39494D4C) if v11 else
                             (0x38564D4C, 0x38494D4C) if v10 else
                             (0x37564D4C, 0x37494D4C) if v9 else
                             (0x36564D4C, 0x36494D4C) if v6 else
                             (0x34564D4C, 0x34494D4C) if v4 else
                             (0x33564D4C, 0x33494D4C))
    compiler = "tinybasic" if language == 1 else "focal"
    variables = m.input + 128
    compile_request, execution, overlay, input_request = [m.input+x for x in (512, 640, 720, 768)]
    main_metadata, expression_metadata = m.input+900, m.input+928
    values_size = 4016 if v14 else 3504
    prefix_size = 8192-values_size
    state = m.workspace if v5 else m.workspace + values_size
    expression = state+stack_offset+512 if v6 else m.input+1024
    bytecode = state + state_size
    output = m.input+1280 if v5 else bytecode
    array = m.workspace+prefix_size+424+(3080 if language==2 and v14 else 0) if v5 else m.workspace
    m.partitioned = v5
    tail = bytes((0x5A,))*values_size
    if v5: m.uc.mem_write(m.workspace+prefix_size,tail)
    m.load(packages[compiler])
    m.files[42] = (3 if language == 1 else 2, "VMTEST", source)
    request_size = 40 if v11 else 32
    m.uc.mem_write(compile_request, bytes(request_size))
    m.put(compile_request, request_size, version, 0, 9728 if v11 else 6144)
    if v11: m.uc.mem_write(compile_request+32, b"\x01")
    assert m.call(0x206 if language == 1 else 0x106, 42, 0, compile_request) == (1 if language == 1 else 0)
    wire = bytes(m.uc.mem_read(compile_request, request_size))
    assert wire[16] == 0 and wire[30] == 1, wire.hex()
    length = struct.unpack_from("<H", wire, 18)[0]
    assert length <= 8192-values_size-state_size
    m.put(compile_request+8, output, length)
    reads = sum(x[0] == "file_read" for x in m.trace)
    assert m.call(0x704, 0, 0, compile_request) == 1
    assert sum(x[0] == "file_read" for x in m.trace) == reads
    emitted = bytes(m.uc.mem_read(compile_request, request_size))
    assert emitted[16] == 0 and struct.unpack_from("<H", emitted, 18)[0] == length
    image = bytes(m.uc.mem_read(output, length))
    if v5:
        assert length <= 768
        assert bytes(m.uc.mem_read(m.workspace+prefix_size,values_size)) == tail
        assert m.workspace_requests and max(size for _,size in m.workspace_requests) <= prefix_size
        m.uc.mem_write(bytecode,image)
    m.uc.mem_write(variables, bytes(208))
    m.uc.mem_write(array, bytes(512 if language==2 and v14 else 3080))
    m.uc.mem_write(state, bytes(state_size))
    m.uc.mem_write(state+language_offset, bytes((language,)))
    m.uc.mem_write(execution, bytes(execution_size))
    m.put(execution, execution_size, version, bytecode, length, variables, array, 385 if language == 1 else 64 if v14 else 0)
    m.uc.mem_write(execution+28, bytes((mode, 0, 0, 0)))
    m.uc.mem_write(overlay, bytes(24 if v4 else 20))
    m.put(overlay, 24 if v4 else 20, version, execution, state)
    action_offset = 20 if v4 else 16
    if v4:
        m.put(overlay+16, main_metadata)
        m.stage = "verification"
        m.load(packages["language-input"])
        assert m.call(VM_INFO) == input_magic
        assert m.call(VALIDATE, overlay) == 1 and m.uc.mem_read(execution+result_offset, 1)[0] == 0
    inputs = evaluations = retries = 0
    for _ in range(20):
        m.stage = "program"
        m.load(packages["language-vm"])
        assert m.call(VM_INFO) == vm_magic
        if mode == 0 and cancelled:
            m.keys = [m.mapping[39]]  # final interactive wait after ABORT
        assert m.call(VM_RUN, overlay) == 1
        error, pc = m.uc.mem_read(execution+result_offset, 1)[0], struct.unpack("<H", m.uc.mem_read(execution+result_offset+2, 2))[0]
        if error != 15:  # Error::YIELDED, appended without changing old errors
            if v4:
                m.stage = "finish"
                m.load(packages["language-input"])
                if mode == 0: m.keys = [m.mapping[38 if edit_after_error else 39]]
                assert m.call(FINISH, overlay) == 1
                error = m.uc.mem_read(execution+result_offset, 1)[0]
            assert bytes(m.uc.mem_read(bytecode, length)) == image
            return (decode_number(m.uc.mem_read(variables,8)) if v10 else struct.unpack("<d", m.uc.mem_read(variables,8))[0]), error, inputs, evaluations, retries
        assert image[pc] in (48, 89)  # READ_INPUT / INPUT_RESOURCE
        prompt_offset, prompt_length = struct.unpack("<HH", m.uc.mem_read(state+prompt_offset_field, 4))
        pooled_prompt = m.uc.mem_read(bytecode+pc, 1)[0] == 89
        resource_prompt = pooled_prompt and not (image[7]&8)
        if pooled_prompt:
            end = struct.unpack('<H', m.uc.mem_read(bytecode+30, 2))[0]
            handle = struct.unpack('<H', m.uc.mem_read(bytecode+pc+1, 2))[0]
            assert prompt_offset == end+handle+(2 if image[7]&8 else 0) and prompt_length <= 95
        else: assert prompt_offset == pc+3 and prompt_offset+prompt_length <= length
        invalid = False
        while True:
            before = bytes(m.uc.mem_read(state, state_size))
            m.stage = "input"
            m.load(packages["language-input"])
            assert m.call(VM_INFO) == input_magic
            if cancelled: m.keys = [m.mapping[39]]
            else: m.input_keys(answers.pop(0))
            m.uc.mem_write(input_request, bytes(40))
            m.uc.mem_write(input_request, bytes(40))
            m.put(input_request, 40, version, bytecode+prompt_offset, expression)
            if resource_prompt: m.put(input_request+36, bytecode)
            struct_data = struct.pack("<HHHBBB", prompt_length, 256 if v4 else 768, 0, language, 0, invalid)
            m.uc.mem_write(input_request+24, struct_data)
            assert m.call(INPUT, input_request) == 1
            result = m.uc.mem_read(input_request+31, 1)[0]
            # Only the unused upper 32 stack slots may change in v6. The
            # suspended values, control frames and partial PRINT are intact.
            after = bytes(m.uc.mem_read(state, state_size))
            if v6:
                assert after[:stack_offset+512] == before[:stack_offset+512] and after[output_offset:] == before[output_offset:]
                if language == 2 and not v14: assert after == before  # FOCAL parses a scalar only
            else:
                assert after == before, [i for i,(a,b) in enumerate(zip(before,after)) if a!=b][:16]
            if result == 3:
                m.uc.mem_write(state+cancelled_offset, b"\x01")  # cancelled
                m.uc.mem_write(state+cancelled_offset+1, bytes((language == 1 and mode == 0,)))
                action = 3; break
            if result == 1:
                m.uc.mem_write(state+input_value_offset, encode_number(struct.unpack("<d",m.uc.mem_read(input_request+16,8))[0]) if v10 else bytes(m.uc.mem_read(input_request+16,8)))
                action = 1; inputs += 1; break
            assert result == 2
            evaluations += 1
            expression_size = struct.unpack("<H", m.uc.mem_read(input_request+28, 2))[0]
            borrowed_image = bytes(m.uc.mem_read(expression,256)) if v6 else None
            temporary = m.input + 832
            m.uc.mem_write(temporary, bytes(m.uc.mem_read(execution, execution_size)))
            m.put(temporary+8, expression, expression_size)
            m.put(overlay+8, temporary)
            m.uc.mem_write(overlay+action_offset, b"\x02")
            control = bytes(m.uc.mem_read(state, control_size))
            sp = m.uc.mem_read(state+(678 if v14 else 614 if v8 else 610), 1)[0]
            prefix = bytes(m.uc.mem_read(state+stack_offset, sp*8))
            output = bytes(m.uc.mem_read(state+output_offset, 96))
            if v4:
                m.put(overlay+16, expression_metadata)
                m.stage = "verification"
                assert m.call(VALIDATE, overlay) == 1 and m.uc.mem_read(temporary+result_offset, 1)[0] == 0
            m.stage = "expression"
            m.load(packages["language-vm"])
            assert m.call(VM_RUN, overlay) == 1
            assert bytes(m.uc.mem_read(state, control_size)) == control
            assert bytes(m.uc.mem_read(state+stack_offset, sp*8)) == prefix
            assert bytes(m.uc.mem_read(state+output_offset, 96)) == output
            if v6: assert bytes(m.uc.mem_read(expression,256)) == borrowed_image
            expression_error = m.uc.mem_read(temporary+result_offset, 1)[0]
            m.put(overlay+8, execution)
            if v4: m.put(overlay+16, main_metadata)
            if expression_error == 0:
                inputs += 1; action = 1; break
            retries += 1; invalid = True
        m.uc.mem_write(overlay+action_offset, bytes((action,)))
    raise AssertionError("unexpected endless continuation")


def main():
    global GENERATION
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resident-elf", type=Path, required=True)
    p.add_argument("--apps-dir", type=Path, default=ROOT/"tmp/language-vm-screen")
    p.add_argument("--vm-profile", choices=("core", "local", "libm"), default="core")
    p.add_argument("--generation", type=int, choices=(3,4,5,6,7,8,9,10,11,12,13,14), default=14)
    p.add_argument("--system", type=Path, help="canonical System directory instead of historical experiment layout")
    p.add_argument("--report-file", type=Path)
    args = p.parse_args()
    GENERATION = args.generation
    peaks = {}
    stress_peaks = {}
    layouts = {}
    def record(m):
        for stage, size in m.stage_peaks.items(): peaks[stage] = max(peaks.get(stage, 0), size)
        for kind, size in m.workspace_requests:
            name = "BASIC" if kind == 2 else "FOCAL"
            layouts[name] = max(layouts.get(name,0),size)
    elf = Elf(args.resident_elf)
    if args.vm_profile != "local": elf.require_libm_math(args.resident_elf)
    with tempfile.TemporaryDirectory(prefix="mk61-overlay-arm-") as directory:
        work = Path(directory); reader = work/"reader"
        run(["c++", "-std=c++17", "-O2", "-I"+str(ROOT/"code"),
             ROOT/"tests/portable_app_format_self_test.cpp",
             ROOT/"code/loadable_module_format.cpp", ROOT/"code/zx0.cpp", "-o", reader])
        paths = (("tinybasic", "compiler/tinybasic/BASIC.APP"),
                 ("focal", "compiler/focal/FOCAL.APP"),
                 ("language-vm", f"runner/{'local' if args.vm_profile=='local' else 'core'}/LANGVM.APP"),
                 ("language-input", "input/LANGIN.APP"))
        packages = {kind: package(reader, args.system/Path(path).name if args.system else args.apps_dir/path,
                                  elf, work, kind) for kind, path in paths}
        basic = (b"10 S=0\n20 FOR I=1 TO 3\n30 GOSUB 100\n40 NEXT I\n"
                 b"50 A=S;END\n100 INPUT @(I)\n110 S=S+@(I);RETURN\n")
        focal = b"1.10 D 2\n1.20 E\n2.10 F I=1,3; A X\n2.20 S A=X\n"
        for address in range(3):
            m = OverlayMachine(args.resident_elf, True, address)
            assert execute(m, packages, 1, basic, ["10", "1/0", "20", "30"]) == (60, 0, 3, 4, 1)
            record(m)
            if GENERATION >= 8:
                m = OverlayMachine(args.resident_elf, True, address)
                data = (b"10 DATA 3,4\n20 READ B;INPUT C;READ D\n"
                        b"30 IF C=5 THEN A=B+D ELSE A=99\n")
                assert execute(m,packages,1,data,["5"])[:2] == (7,0)
                m = OverlayMachine(args.resident_elf, True, address)
                nested = (b"10 FOR I=1 TO 1;ON 1 GOSUB 100;NEXT I\n"
                          b"20 FOR @(0)=3 TO 1 STEP -1;A=A+@(0);NEXT @(0);STOP\n"
                          b"100 FOR I=1 TO 1;A=A+1;NEXT I;RETURN\n")
                assert execute(m,packages,1,nested,[])[:2] == (7,0)
                m = OverlayMachine(args.resident_elf, True, address)
                assert execute(m,packages,1,b"10 A=1/0\n",[],mode=0,edit_after_error=True)[1] == 16
                assert m.uc.mem_read(m.input+640+34,1)[0] == 1
                assert any("DIV BY ZERO" in line for line in m.lines), m.lines
            m = OverlayMachine(args.resident_elf, True, address)
            assert execute(m, packages, 2, focal, ["10", "20", "30"]) == (30, 0, 3, 3 if GENERATION>=14 else 0, 0)
            record(m)
            if GENERATION>=14:
                for program,answers,expected in (
                    (b'1.10 S A=3+CALL(2,5); E\n2.10 ASK "Z=",Z(2); RETURN ARG(1)+Z(2)\n',["7"],15),
                    (b'1.10 S A=CALL(2,5); E\n2.10 IF(ARG(1)-1) 2.30,2.30; R ARG(1)*CALL(2,ARG(1)-1)\n2.30 R 1\n',[],120),
                    (b'1.10 P "Head",CALL(2,4),!; E\n2.10 ASK N; R ARG(1)*N\n',["2+3"],0),
                    (b'1.10 P %8.3,PI,!; S A=1; E\n',[],1)):
                    m=OverlayMachine(args.resident_elf,True,address)
                    assert execute(m,packages,2,program,answers)[:2]==(expected,0)
                    if b'Head' in program:assert "Head20" in "".join(m.lines),m.lines
                    if b'%8.3' in program:assert "3.14" in "".join(m.lines),m.lines
                    record(m)

            m = OverlayMachine(args.resident_elf, True, address)
            assert execute(m, packages, 1, b'10 PRINT "HEAD";\n20 INPUT A\n30 PRINT A\n', ["5"])[0:2] == (5, 0)
            assert "HEAD5" in "".join(m.lines), m.lines
            record(m)
            for mode, expected in ((1, 13), (0, 0)):
                m = OverlayMachine(args.resident_elf, True, address)
                assert execute(m, packages, 1, b"10 INPUT A\n20 A=999\n", [], True, mode)[1] == expected
                record(m)
            source = b"1.10 S A=SQRT(2)\n1.20 E\n"
            m = OverlayMachine(args.resident_elf, True, address)
            actual, error, *_ = execute(m, packages, 2, source, [])
            expected = math.sqrt(2) if args.vm_profile != "local" else struct.unpack("<f", struct.pack("<f", math.sqrt(2)))[0]
            assert error == 0 and actual == expected, (actual, expected, error)
            record(m)
            # Keep additional stress traces separate from the historical
            # small-input suite so its before/after SP comparisons stay fair.
            deep = "1"
            for _ in range(15): deep = "1+("+deep+")"
            m = OverlayMachine(args.resident_elf, True, address)
            assert execute(m, packages, 1, b"10 INPUT @(2)\n20 A=@(2)\n", [deep])[:2] == (16, 0)
            for stage, size in m.stage_peaks.items():
                stress_peaks[stage] = max(stress_peaks.get(stage,0),size)
            m = OverlayMachine(args.resident_elf, True, address)
            actual, error, *_ = execute(m, packages, 1, b"10 INPUT A\n", ["+".join([".1"]*21)])
            assert error == 0 and math.isclose(actual,2.1,rel_tol=1e-14), (actual,error)
            for stage, size in m.stage_peaks.items():
                stress_peaks[stage] = max(stress_peaks.get(stage,0),size)
        result = {"generation":GENERATION,"profile":args.vm_profile,"native_call_stack_peaks":peaks,
                  "stress_native_call_stack_peaks":stress_peaks,
                  "compiler_workspace_bytes":layouts,
                  "input_image_c_stack_bytes":0 if GENERATION >= 6 else 256 if GENERATION >= 4 else 768,
                  "input_image_in_value_stack":GENERATION >= 6,
                  "note":"APP/native service calls only; resident dispatcher/loader frames and live heap are not modeled."}
        if args.report_file:
            args.report_file.parent.mkdir(parents=True,exist_ok=True)
            args.report_file.write_text(json.dumps(result,indent=2)+"\n")
        print(f"overlay VM ARM v{GENERATION} ({args.vm_profile}): cold validation/finish, real INPUT, frames preserved, 3 addresses PASS")
        print(json.dumps(result,indent=2))


if __name__ == "__main__": main()
