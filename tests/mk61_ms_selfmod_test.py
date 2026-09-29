"""Run literal and branch self-modification through the unchanged ROM/core."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
RUNNER = sys.argv[1]
sys.path[:0] = [str(ROOT/'tools/elite'), str(ROOT/'tools')]
from assembler import Assembler, pack_number
from program_pack import program_binary

def probe(out, name, first, second, expected, targets=()):
    a = Assembler()
    m = a.module(0, 'caller')
    m.raw(0x2F, 0x50, 0x2F, 0x2A).op('cx')
    for r in range(9): m.st(r)
    for word, result in ((first, 'A'), (second, 'B')):
        m.set(0, word).far(0x53, 24*112+63)
        m.op('cx').far(0x53, 24*112+1).st(result)
    m.op('stop')
    banks, info = a.link()
    image = bytearray(32*112)
    for bank, data in banks.items(): image[bank*112:(bank+1)*112] = data
    # The patcher is outside the 63-byte exchanged head. The payload
    # consists of valid numeric words, so the ROM can carry it unchanged.
    image[24*112+63:24*112+67] = bytes.fromhex('55 56 55 52')
    for address, value in targets:
        image[24*112+address:24*112+address+2] = bytes((value, 0x52))
    folder = out/name
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'elite.bin').write_bytes(program_binary(image))
    (folder/'autoexec.m61').write_text('reinit\nload 0000 elite.bin\nrun\n')
    result = subprocess.run([RUNNER, str(folder)], input='run\n', text=True,
                            capture_output=True, check=True, timeout=120)
    state = json.loads(result.stdout)
    assert not state['running'] and not state['error'], state
    assert state['regs'][10:12] == list(expected), state
    assert state['pages'][0][0] == second, state
    (folder/'result.json').write_text(json.dumps(state, indent=2)+'\n')
    return dict(probe=name, returns=state['regs'][10:12], steps=state['steps'],
                first_word=pack_number(first).hex(' '),
                second_word=pack_number(second).hex(' '))

with TemporaryDirectory(prefix='mk61-ms-selfmod-') as temp:
    out = Path(temp)
    # R0=10005203 represents bytes 00 03 52 00 10 70 00. At bank:01
    # that is 3; RET. The second write replaces it with 4; RET.
    print(json.dumps(probe(out,'literal',10005203,10005204,(3,4))))
    # Change only the BP operand: 00 51 70 ... -> 00 51 80 ... .
    print(json.dumps(probe(out,'branch',10007051,10008051,(7,8),((70,7),(80,8)))))
print('MK61 real-core: 55/56 self-modifying literal and branch verified')
