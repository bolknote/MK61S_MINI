"""Experimental self-extraction of RLE-packed numeric code words on MK61s.

The host creates the initial image. All expansion and program writes after
RUN are performed by calculator opcodes, without a firmware decompressor.
This deliberately covers valid numeric words, not arbitrary bytecode.

Format: up to four pairs (word, repeat count), held as ordinary 7-byte
numeric records. Output: one to three complete 63-byte bank heads; service
bytes start at zero. The 82-byte decoder and the 4-byte destination patch
routine execute on the existing firmware core. Generated fragments are
single-digit/RET probes. Size totals exclude the experiment driver, bank
padding, raw transport text, and working memory; final output still needs
its own banks. This is an experiment, not an ELITE compressor.

Run with the local extended runner built from core_runner.cpp:
  PYTHONDONTWRITEBYTECODE=1 python3 probe.py ./core_runner
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/elite'))
from assembler import Assembler, pack_number

SOURCE = 23
TARGET = 24


def build(runs):
    words = [word for word, count in runs for _ in range(count)]
    assert words and len(words) % 9 == 0 and len(words) <= 27
    assert len(runs) <= 4
    pages = len(words) // 9
    asm = Assembler()
    main = asm.module(0, 'experiment driver')
    main.raw(0x2F, 0x50, 0x2F, 0x2A).call('unpack').op('stop')
    # Execute every generated fragment, stopping after each group of nine.
    for page in range(pages):
        for field in range(9):
            main.op('cx').far(0x53, (TARGET + page) * 112 + field * 7 + 1).st(field)
        main.op('stop')

    decoder = asm.module(1, 'numeric-word RLE decoder')
    decoder.label('unpack')
    # R9 = output word index, RA = destination patch routine address,
    # RB = repeated word, RC = repeats remaining, RD = input word index,
    # RE = destination pages remaining. K1 leaves R9..RF untouched.
    decoder.set(9, 0).set('C', 0).set('D', 0)
    decoder.set('A', TARGET * 112 + 63).set('E', pages)
    decoder.label('fill').ld('C').jnz('have_run')
    decoder.open_page(SOURCE).raw(0xDD).st('B').add('D', 1)
    decoder.raw(0xDD).st('C').add('D', 1).close_page(SOURCE)
    decoder.label('have_run').ld('B').raw(0xB9).add('C', -1).add(9, 1)
    decoder.ld(9).n(9).op('-').jz('flush').jump('fill')
    decoder.label('flush').raw(0x1F, 0xAA).add('A', 112).add('E', -1)
    decoder.ld('E').jz('done').set(9, 0).jump('fill')
    decoder.label('done').op('ret')
    banks, info = asm.link()
    image = bytearray(32 * 112)
    for bank, data in banks.items():
        image[bank * 112:(bank + 1) * 112] = data
    stream = b''.join(pack_number(value) for run in runs for value in run)
    image[SOURCE * 112:SOURCE * 112 + len(stream)] = stream
    for page in range(pages):
        address = (TARGET + page) * 112 + 63
        assert not any(image[address - 63:address])
        image[address:address + 4] = bytes.fromhex('55 56 55 52')
    size = sum(entry['used'] for entry in info['banks'].values()
               if 'numeric-word RLE decoder' in entry['module'])
    return image, words, dict(decoder_bytes=size, stream_bytes=len(stream),
                             patcher_bytes=pages * 4,
                             output_head_bytes=len(words) * 7,
                             labels=info['labels'])


def probe(name, runs, runner):
    image, words, info = build(runs)
    folder = HERE / name
    folder.mkdir(exist_ok=True)
    # Load raw initial bytes. No ZX0/firmware decompressor participates.
    (folder / 'initial.raw').write_bytes(image)
    lines = ['reinit']
    for bank in range(32):
        chunk = image[bank * 112:(bank + 1) * 112]
        lines.append(f'hin {bank * 112:04d} {chunk.hex()}')
    lines.append('run')
    (folder / 'autoexec.m61').write_text('\n'.join(lines) + '\n')
    pages = len(words) // 9
    result = subprocess.run([str(runner), str(folder)],
                            input='dump\n' + 'run\n' * pages, text=True,
                            capture_output=True, check=True, timeout=120)
    states = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(states) == pages + 1, result.stdout
    assert all(not state['running'] and not state['error'] for state in states), states
    for page in range(pages):
        expected = words[page * 9:page * 9 + 9]
        assert states[0]['pages'][page] == expected, states[0]
        expected_hex = b''.join(pack_number(word) for word in expected).hex()
        assert states[0]['output_code'][page] == expected_hex, states[0]
        # The validated payloads contain a single digit followed by RET.
        returns = [pack_number(word)[1] for word in expected]
        assert states[page + 1]['regs'][:9] == returns, states[page + 1]
        assert states[page + 1]['output_code'][page] == expected_hex, states[page + 1]
    info.update(name=name, runs=runs, loader_and_initial_run_steps=states[0]['steps'],
                execution_steps=sum(state['steps'] for state in states[1:]),
                decoder_plus_stream_plus_patchers=(info['decoder_bytes'] +
                    info['stream_bytes'] + info['patcher_bytes']))
    (folder / 'result.json').write_text(json.dumps(states, indent=2) + '\n')
    return info


if __name__ == '__main__':
    cases = [('nine_repeats', [(10005203, 9)]),
             ('cross_bank_run', [(10005203, 4), (10005204, 23)]),
             ('run_at_bank_boundary', [(10005203, 9), (10005209, 18)]),
             ('four_runs', [(10005201, 1), (10005202, 8),
                            (10005203, 10), (10005204, 8)])]
    report = [probe(name, runs, Path(sys.argv[1]).resolve()) for name, runs in cases]
    (HERE / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
