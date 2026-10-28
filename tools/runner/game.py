"""Build the Runner movement prototype as actual MK61 calculator opcodes.

R0..R3 are the segment frame. R4/R5 are the one-based column/floor.
R6..R9 are held left/right/up/down; only M61 writes these registers.
RA is the signed last key request, RC its acknowledgement. RB/RD hold
the open floor cell and its lifetime. RE/RF are scratch/dispatch pointers.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'elite'))
from assembler import Assembler

WIDTH, FLOORS = 12, 3
FRAME_MS, HOLE_TICKS = 120, 18
LADDERS = {1: (3, 9), 2: (3, 7, 9, 11), 3: (7, 11)}
PALETTE = (0, 8, 0x7E, 0x6B)
FRAME_TABLE_BANK, HOLE_TABLE_BANK, PALETTE_BANK = 28, 30, 31


def frame(floor, column):
    return [0x6B if x == column else 0x7E if x in LADDERS[floor] else 8
            for x in range(1, WIDTH + 1)]


def create_game():
    a = Assembler()
    m = a.module(0, 'startup and frame loop')
    m.label('start').raw(0x2F, 0x50, 0x2F, 0x2A)
    m.op('cx')
    for reg in (6, 7, 8, 9, 'A', 'B', 'C', 'D'):
        m.st(reg)
    m.call('restart').call('draw').call('frame_gate')
    m.label('tick').set('E', 0).call('age_hole').call('choose_action')
    m.ld('F').n(4).op('*').ptr('E', 'action_table').op('+').st('E')
    m.raw(0x1F, 0xAE).call('gravity').call('draw').call('frame_gate').jump('tick')

    m = a.module(1, 'input sampling')
    m.label('choose_action').ld('A').ld('C').op('-').jz('held')
    # The game never clears RA. Copy a complete request before decoding it:
    # an edge arriving between LD and STO remains pending for the next frame.
    m.ld('A').st('C').op('abs').st('F').op('ret')
    m.label('held').op('cx').st('F')
    m.ld(6).jz('held_right').ld(7).jnz('held_vertical').set('F', 4)
    m.label('held_right').ld(7).jz('held_vertical')
    m.ld(6).jnz('held_vertical').set('F', 6)
    m.label('held_vertical').ld(8).jz('held_down')
    m.ld(9).jnz('idle').set('F', 8).op('ret')
    m.label('held_down').ld(9).jz('idle').ld(8).jnz('idle').set('F', 2)
    m.label('idle').op('ret')

    m = a.module(2, 'horizontal movement and falling')
    m.label('left').ld(7).jnz('horizontal_done')
    m.ld(4).n(1).op('-').jz('horizontal_done').add(4, -1).op('ret')
    m.label('right').ld(6).jnz('horizontal_done')
    m.ld(4).n(WIDTH).op('-').jz('horizontal_done').add(4, 1)
    m.label('horizontal_done').op('ret')
    m.label('gravity').ld(5).n(1).op('-').jz('gravity_done')
    m.ld(5).n(1).op('-').n(WIDTH).op('*').ld(4).op('+')
    m.ld('B').op('-').jnz('gravity_done').add(5, -1)
    m.label('gravity_done').op('ret')
    m.label('restart').set(4, 1).set(5, 2).set('B', 0).st('D').op('ret')

    m = a.module(3, 'ladders')
    m.label('up').ld(9).jnz('ladder_done')
    m.ld(5).n(FLOORS).op('-').jz('ladder_done')
    m.ld(5).n(1).op('-').jz('up_lower')
    m.ld(4).n(7).op('-').jz('climb_up')
    m.ld(4).n(11).op('-').jnz('ladder_done')
    m.label('climb_up').add(5, 1).op('ret')
    m.label('up_lower').ld(4).n(3).op('-').jz('climb_up')
    m.ld(4).n(9).op('-').jz('climb_up').op('ret')
    m.label('down').ld(8).jnz('ladder_done')
    m.ld(5).n(1).op('-').jz('ladder_done')
    m.ld(5).n(2).op('-').jz('down_middle')
    m.ld(4).n(7).op('-').jz('climb_down')
    m.ld(4).n(11).op('-').jnz('ladder_done')
    m.label('climb_down').add(5, -1).op('ret')
    m.label('down_middle').ld(4).n(3).op('-').jz('climb_down')
    m.ld(4).n(9).op('-').jz('climb_down')
    m.label('ladder_done').op('ret')

    m = a.module(4, 'burning and restoration')
    m.label('burn_left').ld(4).n(1).op('-').st(0).jump('burn')
    m.label('burn_right').ld(4).n(1).op('+').st(0)
    m.label('burn').ld('D').jnz('burn_done')
    m.ld(5).n(1).op('-').jz('burn_done')
    m.ld(0).jz('burn_done').n(WIDTH + 1).op('-').jz('burn_done')
    m.ld(5).n(2).op('-').jnz('burn_upper')
    for column in (3, 9):
        m.ld(0).n(column).op('-').jz('burn_done')
    m.label('burn_upper')
    for column in (7, 11):
        m.ld(0).n(column).op('-').jz('burn_done')
    m.ld(5).n(1).op('-').n(WIDTH).op('*').ld(0).op('+').st('B')
    m.set('D', HOLE_TICKS)
    m.label('burn_done').op('ret')
    m.label('age_hole').ld('D').jz('age_done').n(1).op('-').st('D')
    m.jnz('age_done').set('B', 0)
    m.label('age_done').op('ret')

    m = a.module(5, 'frame composition')
    m.label('draw').ld(5).n(1).op('-').n(WIDTH).op('*')
    m.ld(4).op('+').n(1).op('-').n(4).op('*')
    m.ptr('E', 'frame_table').op('+').st('E').raw(0x1F, 0xAE)
    m.ptr('F', 'palette')
    # The first six cells overwrite R0/R1. R3 retains the second source
    # until 2F 73 reads it, then replaces R2/R3. Only 2F 53 publishes.
    m.raw(0x2F, 0x00, 0x2F, 0x70, 0x2F, 0x73)
    m.call('draw_hole').raw(0x2F, 0x53).op('ret')
    m.label('draw_hole').ld('D').jz('draw_hole_done')
    m.ld('B').n(1).op('-').n(WIDTH).op('/', 'int').n(1).op('+')
    m.ld(5).op('-').jnz('draw_hole_done')
    m.ld('B').ld(5).n(1).op('-').n(WIDTH).op('*').op('-')
    m.n(1).op('-').n(4).op('*').ptr('E', 'hole_table')
    m.op('+').st('E').raw(0x1F, 0xAE)
    m.label('draw_hole_done').op('ret')

    m = a.module(6, 'clear an open cell in the frame')
    for column in range(WIDTH):
        m.label(f'hole_{column}').ld(column // 3)
        m.n(8 << (8 * (column % 3))).op('-').st(column // 3).op('ret')

    # TRAP addresses are local to every bank. Offset 111 is normally an
    # operand or unused; RE guards the occasional other RET at that offset.
    m = a.module(7, 'frame pacing gate').label('frame_gate').set('E', 9999)
    m.branch(0x51, 'frame_pause', far=True).raw(*([0x54] * 102))
    m.label('frame_pause').op('ret')

    m = a.module(8, 'floor and hero sprites')
    for floor in range(1, FLOORS + 1):
        for column in range(1, WIDTH + 1):
            codes = [PALETTE.index(mask) for mask in frame(floor, column)]
            words = [sum(codes[base + i] << (4 * (5 - i)) for i in range(6))
                     for base in (0, 6)]
            m.label(f'frame_{floor}_{column}').set(0, words[0]).set(3, words[1]).op('ret')

    # Uniform four-byte jumps let the calculator index these tables directly.
    for page, indices in enumerate((range(28), range(28, WIDTH * FLOORS))):
        m = a.module(FRAME_TABLE_BANK + page, 'frame jump table')
        if page == 0:
            m.label('frame_table')
        for index in indices:
            m.branch(0x51, f'frame_{index // WIDTH + 1}_{index % WIDTH + 1}', far=True)
    m = a.module(HOLE_TABLE_BANK, 'cell and action jump tables').label('hole_table')
    for column in range(WIDTH):
        m.branch(0x51, f'hole_{column}', far=True)
    m.label('action_table')
    for target in ('idle', 'idle', 'down', 'idle', 'left', 'idle', 'right',
                   'burn_left', 'up', 'burn_right', 'restart'):
        m.branch(0x51, target, far=True)
    a.module(PALETTE_BANK, 'segment palette').label('palette').raw(*PALETTE, *([0] * 12))
    return a


def launcher(info):
    lines = ['open? manual.md', 'reinit']
    directions = ((4, 'left', 6), (6, 'right', 7), (8, 'up', 8), (2, 'down', 9))
    for key, name, _ in directions:
        lines += [f'bind key {key:02X} down run :{name}',
                  f'bind key {key:02X} up run :{name}_up']
    for key, name in ((7, 'burn_l'), (9, 'burn_r'), (0, 'restart'),
                      (0x13, 'help'), (0x14, 'exit')):
        lines.append(f'bind key {key:02X} down run :{name}')
    lines += ['load 0000 runner.bin', 'trap 111 run :frame',
              'run', 'ret', ':frame', f'if re==9999 wait {FRAME_MS}', 'ret']
    for key, name, reg in directions:
        lines += [f':{name}', f'R{reg}= 1', f'if rc=={key} RA= -{key}',
                  f'if rc!={key} RA= {key}', 'ret', f':{name}_up', f'R{reg}= 0', 'ret']
    for key, name in ((7, 'burn_l'), (9, 'burn_r'), (10, 'restart')):
        lines += [f':{name}', f'if rc=={key} RA= -{key}', f'if rc!={key} RA= {key}', 'ret']
    lines += [':help', 'open? manual.md', 'ret', ':exit', 'reinit', 'ret']
    source = ('\n'.join(lines) + '\n').encode('ascii')
    assert len(source) <= 1536, len(source)
    return source


def check_layout(info):
    labels = info['labels']
    assert labels['start'] == 0
    assert labels['frame_table'] == FRAME_TABLE_BANK * 112
    assert labels['hole_table'] == HOLE_TABLE_BANK * 112
    assert labels['action_table'] == HOLE_TABLE_BANK * 112 + WIDTH * 4
    assert labels['palette'] == PALETTE_BANK * 112
    assert labels['frame_pause'] == 7 * 112 + 111
