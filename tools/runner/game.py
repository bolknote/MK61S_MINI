"""Build the Runner movement prototype as actual MK61 calculator opcodes.

R0..R3 compose the segment frame; between frames R0 selects an action and
R3 marks publication. R4/R5 are the one-based column/floor. R6..R9 are held
left/right/up/down. M61 owns these flags and the one-shot mailbox RA; RC is
reserved. RB/RD hold the open cell's clear-routine pointer and lifetime.
RE caches the floor's cell table base; RF caches its raw sprite atlas base.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'elite'))
from assembler import Assembler

WIDTH, FLOORS = 12, 3
FRAME_MS, HOLE_TICKS = 30, 18
LADDERS = {1: (3, 9), 2: (3, 7, 9, 11), 3: (7, 11)}
FRAME_TABLE_BANK, ATLAS_BANK = 16, 8
CELL_STRIDE, CLEAR_OFFSET = 28, 12


def floor_base(floor):
    # Indirect R0 decrements before branching: base + stride*column - 1.
    return FRAME_TABLE_BANK * 112 + (floor - 1) * WIDTH * CELL_STRIDE - CELL_STRIDE + 1


def hole_pointer(floor, column):
    return FRAME_TABLE_BANK * 112 + ((floor - 1) * WIDTH + column - 1) * CELL_STRIDE + CLEAR_OFFSET


def sprite_base(floor):
    return ATLAS_BANK*112 + (floor-1)*WIDTH*WIDTH - WIDTH


def frame(floor, column):
    return [0x6B if x == column else 0x7E if x in LADDERS[floor] else 8
            for x in range(1, WIDTH + 1)]


def create_game():
    a = Assembler()
    a.far_conditions = {0x51, 0x53, 0x57, 0x59, 0x5C, 0x5E}
    a.inline_helpers = ('age_hole',)
    m = a.module(0, 'startup and frame loop')
    m.label('start').raw(0x2F, 0x50, 0x2F, 0x2A)
    m.op('cx')
    for reg in (6, 7, 8, 9, 'A', 'B', 'C', 'D'):
        m.st(reg)
    m.call('restart').call('draw')
    m.label('frame_ready').set(3, 1).op('stop')
    # The M61 scheduler selects these entries from the already known timer
    # and input. The common no-hole move needs neither aging nor gravity.
    m.label('tick_fast').set(3,3).raw(0x1F,0xA0).jz('frame_ready')
    m.raw(0x2F,0x84,0x2F,0x53).jump('frame_ready')
    m.label('tick_timer').set(3,3).ld('D').n(1).op('-').st('D').jnz('frame_ready')
    m.set('B',0).raw(0x2F,0x84,0x2F,0x53).jump('frame_ready')
    m.label('tick').set(3, 3).ld('D').jz('quiet_tick')
    m.call('age_hole').raw(0x1F, 0xA0).jnz('changed')
    # An unchanged position cannot fall through a new hole: burns are
    # adjacent, and the sole open cell already dropped the hero on entry.
    # Only expiration needs a fresh picture while no action is pending.
    m.ld('D').jnz('frame_ready').jump('draw_ready')
    m.label('quiet_tick').raw(0x1F, 0xA0).jz('frame_ready')
    m.label('changed').ld('B').jz('draw_ready').call('gravity')
    m.label('draw_ready').call('draw').jump('frame_ready')

    a.module(1, 'idle action').label('idle').op('cx', 'ret')

    m = a.module(2, 'horizontal movement and falling')
    m.label('left_key').label('left').ld(7).jnz('horizontal_done')
    m.ld(4).n(1).op('-').jz('horizontal_done').add(4, -1).op('ret')
    m.label('right_key').label('right').ld(6).jnz('horizontal_done')
    m.ld(4).n(WIDTH).op('-').jz('horizontal_done').add(4, 1)
    m.label('horizontal_done').op('ret')
    m.label('gravity').ld(4).n(CELL_STRIDE).op('*').ld('E').op('+')
    m.n(CLEAR_OFFSET - 1).op('+').ld('B').op('-').jnz('gravity_done')
    m.ld(5).n(2).op('-').jz('floor_1').jump('floor_2')
    m.label('gravity_done').op('ret')
    m.label('restart_key').label('restart').set(4, 1).set('B', 0).st('D').jump('floor_2')

    m = a.module(3, 'ladders')
    m.label('up_key').label('up').ld(9).jnz('ladder_done')
    m.ld(5).n(FLOORS).op('-').jz('ladder_done')
    m.ld(5).n(1).op('-').jz('up_lower')
    m.ld(4).n(7).op('-').jz('floor_3')
    m.ld(4).n(11).op('-').jnz('ladder_done')
    m.jump('floor_3')
    m.label('up_lower').ld(4).n(3).op('-').jz('floor_2')
    m.ld(4).n(9).op('-').jz('floor_2').op('ret')
    m.label('down_key').label('down').ld(8).jnz('ladder_done')
    m.ld(5).n(1).op('-').jz('ladder_done')
    m.ld(5).n(2).op('-').jz('down_middle')
    m.ld(4).n(7).op('-').jz('floor_2')
    m.ld(4).n(11).op('-').jnz('ladder_done')
    m.jump('floor_2')
    m.label('down_middle').ld(4).n(3).op('-').jz('floor_1')
    m.ld(4).n(9).op('-').jz('floor_1')
    m.label('ladder_done').op('ret')

    m = a.module(4, 'burning and restoration')
    for name, offset in (('burn_left', 4), ('burn_right', 8)):
        m.label(name+'_key').label(name).ld('D').jnz('burn_done')
        m.ld(4).n(CELL_STRIDE).op('*').ld('E').op('+').n(offset).op('+').st(0).raw(0x1F, 0x80)
    m.label('burn_done').op('cx','ret')
    m.label('burn_publish').call('draw').op('cx','ret')
    m.label('age_hole').ld('D').jz('age_done').n(1).op('-').st('D')
    m.jnz('age_done').set('B', 0)
    m.label('age_done').op('ret')

    m = a.module(5, 'frame composition')
    m.label('draw').raw(0x2F, 0x84).ld('D').jz('publish')
    m.raw(0x1F, 0xAB)
    m.label('publish').raw(0x2F, 0x53).op('ret')

    burnable = [(floor, column) for floor in (2, 3) for column in range(1, WIDTH+1)
                if column not in LADDERS[floor]]
    for index, (floor, column) in enumerate(burnable):
        if index % 8 == 0:
            m = a.module((6, 14, 15)[index//8], 'valid burn destinations')
        m.label(f'burn_{floor}_{column}').set('B', hole_pointer(floor, column)).set('D', HOLE_TICKS).jump('burn_publish')

    m=a.module(12,'floor metadata')
    for floor in range(1,FLOORS+1):
        m.label(f'floor_{floor}').set(5,floor).set('E',floor_base(floor)).set('F',sprite_base(floor)).op('ret')

    atlas = bytes(mask for floor in range(1,FLOORS+1) for column in range(1,WIDTH+1)
                  for mask in frame(floor,column))
    for page in range((len(atlas)+111)//112):
        a.module(ATLAS_BANK+page, 'raw segment sprite atlas').raw(*atlas[page*112:(page+1)*112])

    # Each fixed record provides both burn destinations and a small
    # floor-qualified clear routine. Four records fit a bank exactly.
    # The first four bytes retain the table's existing address layout.
    for index in range(WIDTH * FLOORS):
        floor, column = index//WIDTH + 1, index % WIDTH + 1
        if index % 4 == 0:
            m = a.module(FRAME_TABLE_BANK + index//4, 'cell records')
            if index == 0:
                m.label('frame_table')
        m.raw(0x54, 0x54, 0x54, 0x54)
        for neighbor in (column-1, column+1):
            target = f'burn_{floor}_{neighbor}' if (floor, neighbor) in burnable else 'burn_done'
            m.branch(0x51, target, far=True)
        word, shift = (column-1)//3, 8*((column-1) % 3)
        tail = [0x60+word, *map(int, str(8 << shift)), 0x11, 0x40+word, 0x52]
        return_offset = (index % 4)*CELL_STRIDE + CLEAR_OFFSET + 5 + len(tail) - 1
        body = [0x65, floor, 0x11, 0x5E, (return_offset//10)*16 + return_offset % 10, *tail]
        assert len(body) <= CELL_STRIDE - CLEAR_OFFSET
        m.raw(*body, *([0x54] * (CELL_STRIDE-CLEAR_OFFSET-len(body))))
    return a


def launcher(info):
    lines = ['open? manual.md', 'reinit', 'R3= 3']
    directions = ((4, 'left', 6), (6, 'right', 7), (8, 'up', 8), (2, 'down', 9))
    for key, name, _ in directions:
        lines += [f'bind key {key:02X} down run :{name}',
                  f'bind key {key:02X} up run :u{key}']
    for key, name in ((7, 'burn_l'), (9, 'burn_r'), (0, 'restart'),
                      (0x13, 'help'), (0x14, 'exit')):
        lines.append(f'bind key {key:02X} down run :{name}')
    # Only M61 owns the mailbox. Bound handlers cannot preempt this EXECUTING
    # block, so reading and clearing RA is safe; a quick DOWN/UP keeps its edge.
    lines += ['load 0000 runner.bin', 'run', ':loop', f'wait {FRAME_MS}',
              'if r5==0 ret', f'R0= {info["labels"]["idle"]+1}',
              f'if r6!=r7 R0= {info["labels"]["right"]+1}',
              f'if r6>r7 R0= {info["labels"]["left"]+1}',
              f'if r8!=r9 R0= {info["labels"]["down"]+1}',
              f'if r8>r9 R0= {info["labels"]["up"]+1}',
              'if ra>0 R0= RA', 'RA= 0',
              f'if r0=={info["labels"]["idle"]+1} if rd==0 run :loop',
              'if rd>0 run :active', f'run {info["labels"]["tick_fast"]}', 'run :after',
              ':active', f'if r0=={info["labels"]["idle"]+1} run :timer',
              f'run {info["labels"]["tick"]}', 'run :after',
              ':timer', f'run {info["labels"]["tick_timer"]}',
              ':after', 'if r5==0 ret', 'run :loop']
    for key, name, reg in directions:
        target = info['labels'][name+'_key'] + 1
        lines += [f':{name}', f'R{reg}= 1', f'RA= {target}',
                  'ret', f':u{key}', f'R{reg}= 0', 'ret']
    for key, name in ((7, 'burn_l'), (9, 'burn_r'), (10, 'restart')):
        target = info['labels'][{'burn_l': 'burn_left', 'burn_r': 'burn_right'}.get(name, name)+'_key'] + 1
        lines += [f':{name}', f'RA= {target}', 'ret']
    lines += [':help', 'open? manual.md', 'ret', ':exit', 'reinit', 'ret']
    source = ('\n'.join(lines) + '\n').encode('ascii')
    assert len(source) <= 1536, len(source)
    return source


def check_layout(info, banks):
    labels = info['labels']
    assert labels['start'] == 0
    assert labels['frame_table'] == FRAME_TABLE_BANK * 112
    assert labels['tick'] < 112
    assert labels['tick_fast'] < 112 and labels['tick_timer'] < 112
    # Every conditional clear returns before its padding. There are no
    # address traps: the scheduler resumes only after a bank-zero STOP.
    for bank in range(FRAME_TABLE_BANK, FRAME_TABLE_BANK + WIDTH*FLOORS//4):
        for offset in range(0, 112, CELL_STRIDE):
            start = offset + CLEAR_OFFSET
            operand = banks[bank][start+4]
            returned = (operand >> 4)*10 + (operand & 15)
            assert start+5 <= returned < offset+CELL_STRIDE-1
            assert banks[bank][returned] == 0x52
            assert all(v == 0x54 for v in banks[bank][returned+1:offset+CELL_STRIDE])
