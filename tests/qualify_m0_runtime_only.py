#!/usr/bin/env python3
"""Run arithmetic, conversions and ABI checks without calling pow or scientific functions."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_eabi_m0_arm_self_test as support


def main():
    elf, rom, destination = map(Path, sys.argv[1:])
    assert not destination.exists()
    start = time.monotonic()
    class RuntimeMachine(support.Machine):
        counts = Counter()
        def call(self, name, *args, **kwargs):
            assert 'pow' not in name, name
            assert time.monotonic() - start <= 600, 'wall deadline'
            assert self.calls < 1000000, 'math call cap'
            answer = super().call(name, *args, **kwargs)
            self.counts[name] += 1
            return answer
        def floating(self, name, a, b, expected, width=64, result_width=None):
            actual = self.call(name, a, b, width)[0]
            rw = result_width or width
            actual &= (1 << rw) - 1
            if support.nan(expected, rw):
                assert support.nan(actual, rw) and actual & (1 << (51 if rw == 64 else 22)), (name, 'NaN must be quiet', hex(actual))
            else:
                assert actual == expected, (name, hex(a), hex(b), hex(actual), hex(expected))
    machine = RuntimeMachine(elf, True, stack_bytes=4096, instruction_budget=1000000, bootrom=rom)
    assert not machine.rom_initializers and not machine.rom_models
    phases, fatal = [], None
    try:
        for name, function, extra in [
            ('arithmetic_conversions_integer', support.arithmetic, (1000,)),
            ('fast_path_boundaries', support.fast_path_boundaries, ()),
            ('addition_rounding', support.addition_rounding, ()),
            ('mixed_sign_nearby', support.mixed_sign_nearby, ()),
            ('multiplication_division', support.multiplication_division, (1000,)),
        ]:
            before = machine.calls
            function(machine, *extra)
            phases.append(dict(name=name, actual_calls=machine.calls-before))
            print('PASS', name, machine.calls-before, flush=True)
        contexts = dict(READY=(0,0,0,0,0,0,1), DIRTY=(17,3,17,3,5,2,3),
                        PENDING=(0x80000001,7,0x80000001,7,0x11223344,0x55667788,2))
        context_calls = 0
        for state, words in contexts.items():
            for op, operation in [('dadd',lambda x,y:x+y),('dsub',lambda x,y:x-y),
                                  ('dmul',lambda x,y:x*y),('ddiv',lambda x,y:x/y)]:
                for x,y in [(0.7,1.3),(1.,2.),(-17.,3.),(2.**-1022,1.5),(1.5,2.**-1022)]:
                    before=struct.pack('<7I',*words)
                    machine.uc.mem_write(0xd0000060,before)
                    machine.floating('__aeabi_'+op,support.bits(x),support.bits(y),support.bits(operation(x,y)))
                    if state!='READY':
                        assert bytes(machine.uc.mem_read(0xd0000060,28))==before,(op,state,'SIO preservation')
                    context_calls+=1
        phases.append(dict(name='SIO_contexts',actual_calls=context_calls))
    except Exception as error:
        fatal=dict(type=type(error).__name__,message=str(error))
    result=dict(status='PASS_FINITE_RUNTIME' if fatal is None else 'FAIL',fatal=fatal,
                ELF_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),ROM_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                operator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                machine_sha256=hashlib.sha256((HERE/'native_eabi_m0_arm_self_test.py').read_bytes()).hexdigest(),
                phases=phases,actual_completed_calls=machine.calls,call_counts=dict(machine.counts),
                maximum_observed_stack_bytes=support.SP-machine.stack_lowest,elapsed_seconds=time.monotonic()-start,
                quiet_NaN_checked=True,pow_calls=0,physical_device_IO=0,scope='Finite runtime/ABI checks; not an exhaustive proof or hardware timing.')
    destination.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='call_counts'}),flush=True)
    if fatal is not None:
        raise SystemExit(1)


if __name__=='__main__':
    main()
