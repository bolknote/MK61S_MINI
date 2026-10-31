"""Runner bytecode and immutable board tables. Python only builds the game.

R4 hero, R5/R8 guards, R6 collected mask*36, R7 hole (36 means absent).
R9..RC held directions, RD mailbox, RE clock threshold, RF scratch.
R0..R3 atomic screen buffer. R3=1 marks a published/stopped native frame.
M61 evaluates movement/chase tables; native code composes and publishes LCD.
"""
from collections import deque
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'elite'))
from assembler import Assembler, screen

WIDTH, FLOORS, ABSENT = 12, 3, 36
FRAME_MS, HOLE_MS = 30, 4000
HERO, GUARD, GOLD, FLOOR, LADDER = 0x6B, 0x77, 0xC9, 0x08, 0x7E
LEVELS = (
    dict(name='First steps', links=((3, 9), (7, 11)), start=12,
         guards=(35, ABSENT), gold=(0, 23, 24), enemy_ms=2000),
    dict(name='Crossroads', links=((2, 10), (4, 8)), start=17,
         guards=(0, 35), gold=(11, 12, 30), enemy_ms=1000),
    dict(name='Long ladders', links=((1, 12), (5, 9)), start=18,
         guards=(5, 35), gold=(6, 22, 24), enemy_ms=1000),
)


def ladders(level, floor):
    result = set()
    if floor:
        result.update(level['links'][floor-1])
    if floor < 2:
        result.update(level['links'][floor])
    return result


def destination(level, cell, direction):
    floor, column = divmod(cell, WIDTH)
    if direction == 'left':
        return cell-1 if column else cell
    if direction == 'right':
        return cell+1 if column < WIDTH-1 else cell
    if direction == 'up':
        return cell+WIDTH if floor < 2 and column+1 in level['links'][floor] else cell
    return cell-WIDTH if floor and column+1 in level['links'][floor-1] else cell


def chase_table(level):
    result = bytearray()
    for hero in range(ABSENT):
        distances, queue = {hero: 0}, deque([hero])
        while queue:
            cell = queue.popleft()
            for direction in ('up', 'down', 'left', 'right'):
                neighbor = destination(level, cell, direction)
                if neighbor not in distances:
                    distances[neighbor] = distances[cell]+1
                    queue.append(neighbor)
        assert len(distances) == ABSENT, 'disconnected level'
        for enemy in range(ABSENT):
            options = [destination(level, enemy, direction)
                       for direction in ('up', 'down', 'left', 'right')]
            result.append(min([enemy, *options], key=distances.__getitem__))
        result.append(ABSENT)
    return bytes(result)


def create_game(number=1):
    level = LEVELS[number-1]
    a = Assembler()
    a.far_conditions = {0x51, 0x53, 0x57, 0x59, 0x5C, 0x5E}
    data, tables = bytearray(), {}
    data_bank = 6

    def table(name, values, width=1):
        tables[name] = data_bank*112 + len(data)
        for value in values:
            data.extend(int(value).to_bytes(width, 'little'))

    for direction in ('left', 'right', 'up', 'down'):
        table(direction, [destination(level, cell, direction) for cell in range(ABSENT)])
    for direction, shift in (('burn_left', -1), ('burn_right', 1)):
        values = []
        for cell in range(ABSENT):
            floor, column = divmod(cell, WIDTH)
            target = column+shift
            values.append(floor*WIDTH+target if floor and 0 <= target < WIDTH and
                          target+1 not in ladders(level, floor) else ABSENT)
        table(direction, values)
    table('chase', chase_table(level))
    table('chase_rows', [tables['chase']+37*hero for hero in range(ABSENT)],3)
    table('collect', [(mask | sum(1 << n for n, gold in enumerate(level['gold']) if gold == cell))*36
                      for mask in range(8) for cell in range(ABSENT)])
    table('background_index', [2*(cell//WIDTH) + bool(mask & (1 << (cell//WIDTH)))
                              for mask in range(8) for cell in range(ABSENT)])
    backgrounds = []
    for floor in range(FLOORS):
        for collected in (False, True):
            backgrounds.extend(GOLD if not collected and level['gold'][floor] == floor*WIDTH+column
                               else LADDER if column+1 in ladders(level, floor) else FLOOR
                               for column in range(WIDTH))
    table('backgrounds', backgrounds)
    table('hero_points', [(cell % WIDTH)*256+HERO for cell in range(ABSENT)], 3)
    table('enemy_points', [(enemy % WIDTH)*256+GUARD if enemy//WIDTH == floor else 65535
                           for floor in range(FLOORS) for enemy in range(ABSENT+1)], 3)
    def layer(mode, index, name, row=255, divisor=0, stride=0):
        base = tables[name]
        return [mode, index, row, divisor, stride, base & 255, base >> 8]
    table('composition', [5,
          *layer(0, 0, 'backgrounds'), *layer(1, 4, 'hero_points'),
          *layer(2, 7, 'enemy_points', 4, 12, 37),
          *layer(1, 5, 'enemy_points', 4, 12, 37),
          *layer(1, 8, 'enemy_points', 4, 12, 37)])
    table('counts', [3-mask.bit_count() for mask in range(8)])
    table('hud', [mask for remaining in range(4) for mask in screen(f'L{number}  GOLd {remaining}')])
    table('lost', screen('CAUGHt  0'))
    table('won', screen('ALL CLEAr' if number == len(LEVELS) else f'L{number} CLEAr'))
    table('fall', [cell-WIDTH if cell>=WIDTH else cell for cell in range(ABSENT)])

    def base(m, name):
        return m.far(0x4F, tables[name])

    def read(m, reg, width=1):
        return m.raw(0x1F, (0xB0 if width == 1 else 0xD0)+int(str(reg), 16))

    m = a.module(0, 'startup and common frame boundary')
    m.label('start').set(3, 3).raw(0x2F, 0x50, 0x2F, 0x2A).op('cx')
    for reg in (9, 'A', 'B', 'C', 'D'):
        m.st(reg)
    # M61 initializes the world after native startup has selected LCD mode.
    m.label('frame_ready').far(0x43, 1).op('stop')
    m.label('dispatch').far(0x43, 4).raw(0x1F, 0xA0).jump('frame_ready')
    m.label('draw_entry').jump('draw')
    m.label('lost_entry').jump('lost')
    m.label('npc_dispatch').raw(0x2F,0x56,0x2F,0x53).jump('frame_ready')
    # Paired entries stay 24 bytes apart, checked after linking. The short
    # addresses also keep the M61 handlers within the C9 file limit.
    for name in ('left','right','up','down','burn_left','burn_right'):
        m.label(name+'_entry').jump(name)
    for name in ('left','right','up','down'):
        m.label(name+'_fast_entry').jump(name+'_fast')
    m.label('npc_fast_start').jump('npc_fast_dispatch')
    m.label('hole_start').jump('hole_dispatch')

    m = a.module(1, 'movement and burning')
    m.label('idle').jump('draw')
    for direction in ('left', 'right', 'up', 'down'):
        m.label(direction)
        m.ld({'left': 'A', 'right': 9, 'up': 'C', 'down': 'B'}[direction]).jnz('idle')
        base(m, direction)
        read(m, 4).st(4).jump('move_done')
    m = a.module(2, 'atomic board composition')
    m.label('draw').ld(6).ld(4).op('+').st(0)
    m.label('draw_indexed')
    base(m, 'background_index')
    read(m, 0).st(0)
    base(m, 'composition').raw(0x2F, 0x56, 0x2F, 0x53).op('ret')

    for direction in ('burn_left', 'burn_right'):
        m.label(direction).ld(7).n(ABSENT).op('-').jnz('idle')
        base(m, direction)
        read(m, 4).st(7).n(ABSENT).op('-').jz('idle')
        m.call('draw').set('F', -1).op('ret')

    # R0..R3 indirect calls decrement their pointer before entering it.
    # A guard reaching the hero overrides the already selected action.
    m.label('collision').far(0x43,4).ptr(0, 'lost', lift=False).add(0, 1).op('ret')

    m = a.module(3, 'gravity, treasures and autonomous guards')
    m.label('move_done').ld(4).ld(7).op('-').jnz('collect')
    m.add(4, -WIDTH)
    m.label('collect').ld(6).ld(4).op('+').st(0)
    base(m, 'collect')
    # R0 still indexes the pre-pickup background. Only the hero's covered
    # cell changes when collecting gold, so that index draws the same frame.
    read(m, 0).st(6).jump('draw_indexed')
    m.label('guards')
    base(m,'chase_rows')
    read(m,4,3).st('F')
    m.ld(5).ld(7).op('-').jz('second_guard')
    read(m, 5).st(5).ld(4).op('-').jz('collision')
    m.label('second_guard').ld(8).ld(7).op('-').jz('guards_done')
    read(m, 8).st(8).ld(4).op('-').jz('collision')
    m.label('guards_done').op('ret')
    m.label('guards_fast')
    base(m,'chase_rows')
    read(m,4,3).st('F')
    read(m,5).st(5).ld(4).op('-').jz('collision')
    read(m,8).st(8).ld(4).op('-').jz('collision').jump('guards_done')

    m.label('enemies').call('guards').jump('draw')

    m = a.module(5, 'movement without an active hole')
    m.label('npc_fast_dispatch').far(0x43,3).call('guards_fast').far(0x43,4)
    m.raw(0x1F,0xA0).jump('frame_ready')
    m.label('hole_dispatch').far(0x43,4).call('hole_action').raw(0x1F,0xA0).jump('frame_ready')
    for direction in ('left','right','up','down'):
        m.label(direction+'_fast')
        m.ld({'left':'A','right':9,'up':'C','down':'B'}[direction]).jnz('idle')
        base(m,direction)
        read(m,4).st(4).jump('collect')

    m = a.module(4, 'restart, score and end screens')
    m.label('restart').set(4, level['start']).set(5, level['guards'][0])
    m.set(6, 0).set(7, ABSENT).set(8, level['guards'][1]).call('draw').set('F', -2).op('ret')
    m.label('hud').ld(6).n(36).op('/').st(0)
    base(m, 'counts')
    read(m, 0).st(0)
    base(m, 'hud').raw(0x2F, 0x80, 0x2F, 0x53).set('F', -3).op('ret')
    for name, state in (('lost', -1), ('won', -2)):
        m.label(name).set(4, state).set(0, 0)
        base(m, name).raw(0x2F, 0x80, 0x2F, 0x53).op('ret')

    # Late input uses the fast entries too. With a hole, map only those four
    # entries to the matching gravity-aware routines before dispatch.
    m.label('hole_action').ptr('F','left_fast_entry',lift=False)
    m.ld(0).ld('F').op('-').jneg('mapped')
    m.n(16).op('-').jge('mapped')
    m.ld(0).n(24).op('-').st(0)
    m.label('mapped').op('ret')

    for page in range((len(data)+111)//112):
        a.module(data_bank+page, 'immutable board and path tables').raw(*data[page*112:(page+1)*112])
    return a, tables


def launcher(info, number=1):
    """Bounded M61 loop; generic table reads evaluate the immutable game data."""
    level, labels, tables = LEVELS[number-1], info['labels'], info['tables']
    addr = lambda name: labels.get(name+'_entry', labels[name])+1
    dispatch = f'run {labels["dispatch"]}'
    threshold = (HOLE_MS-level['enemy_ms'])//1000
    lines = []
    for key, name in ((4, 'a'), (6, 'b'), (8, 'c'), (2, 'd')):
        lines += [f'bind key {key:02X} down run :{name}',
                  f'bind key {key:02X} up run :{name.upper()}']
    for key, name in ((7, 'f'), (9, 'g'), (0, 'r'), (5, 's'), (0x13, 'h'), (0x14, 'x')):
        lines.append(f'bind key {key:02X} down run :{name}')
    lines += ['bind timer run :t', f'load 0000 runner{number}.bin', 'run',
              ':z', 'RD=0', f'R0={addr("restart")}', dispatch,
              ':v', f'RE={threshold}e3', f'timer {HOLE_MS}', 'run :L',
              ':l', f'wait {FRAME_MS}', 'if r7<1 ret',
              'if rd==-1 run :z', 'if rd==-2 run :q', 'if r4<0 run :l', 'R0=0']
    for reg, opposite, direction in (('9', 'a', 'left'), ('a', '9', 'right'),
                                     ('b', 'c', 'up'), ('c', 'b', 'down')):
        lines.append(f'if r{reg}>r{opposite} R0={tables[direction]}')
    lines += ['if rd!=0 R0=RD', 'RD=0', 'if re<0 run :e', 'if timer<=re run :n',
              'if r0==0 run :l', 'run :J',
              ':e', f'if r5==r7 R5={level["guards"][0]}',
              f'if r8==r7 R8={level["guards"][1]}', 'R7=36',
              f'RE={threshold}e3', f'timer {HOLE_MS}', 'run :U', ':n']
    for value in range(level['enemy_ms'], HOLE_MS, level['enemy_ms']):
        lines.append(f'if re=={value//1000}e3 RE={(value-level["enemy_ms"])//1000}e3')
    lines += [':U', f'if r5!=r7 @R5 {tables["chase"]} R5 R4 37',
              'if r4==r5 if r5!=r7 run :o',
              f'if r8!=r7 @R8 {tables["chase"]} R8 R4 37',
              'if r4==r8 if r8!=r7 run :o',
              ':J', 'if r0>0 if r0<112 run :F', 'if r0>0 @R4 R0 R4',
              f'if r4==r7 @R4 {tables["fall"]} R4',
              f'@R6 {tables["collect"]} R4 R6 1',
              'if r4==r5 if r5!=r7 run :o', 'if r4==r8 if r8!=r7 run :o',
              ':L', f'@R0 {tables["background_index"]} R4 R6 1',
              f'RF={tables["composition"]}', f'run {labels["npc_dispatch"]}',
              'timer resume', 'if r6>251 run :w', 'run :l',
              ':F', dispatch, 'if rf==-1 run :v', 'run :l',
              ':q', 'RD=0', 'timer pause', f'R0={addr("hud")}', dispatch,
              'wait 900', 'run :L',
              ':o', f'R0={addr("lost")}', 'run :E',
              ':w', f'R0={addr("won")}', ':E', 'timer 0', dispatch,
              'if r4==-2 wait 1500', 'if r4==-2 ret', 'run :l',
              ':t', 'RE=-1', 'ret']
    for name, reg, opposite, direction in (('a', '9', 'a', 'left'), ('b', 'A', '9', 'right'),
                                            ('c', 'B', 'c', 'up'), ('d', 'C', 'b', 'down')):
        # A pending tap must not bypass cancellation of opposite held keys.
        lines += [':'+name, f'R{reg}=1', f'RD={tables[direction]}',
                  f'if r{opposite}>0 RD=0', 'ret',
                  ':'+name.upper(), f'R{reg}=0', 'ret']
    for name, value in (('f', addr('burn_left')), ('g', addr('burn_right')), ('r', -1), ('s', -2)):
        lines += [':'+name, f'RD={value}', 'ret']
    lines += [':h', 'timer pause', 'open? manual.md', 'timer resume', 'ret',
              ':x', 'reinit', 'ret']
    # IF's numeric parser ends the operand before the next command. Register
    # operands retain their delimiter. Compact register assignments and @ keep
    # the complete level, including all handlers, within the C9 1536-byte file.
    lines = [re.sub(r'((?:==|!=|<=|>=|<|>)-?[0-9]+(?:e[0-9]+)?) ', r'\1',
                    line.replace('0e3', '0')) for line in lines]
    names = [line[1:] for line in lines if line.startswith(':')]
    assert len(names) == len(set(names)), 'duplicate M61 label'
    source = ('\n'.join(lines)+'\n').encode('ascii')
    assert len(source) <= 1536, len(source)
    return source


def campaign():
    return (('open? manual.md\nreinit\nbind key 00 down run :r\n'
             'bind key 14 down run :x\n:a\n') +
            ''.join(f'open level{n}.m61\nif r7==0 ret\n' for n in range(1, len(LEVELS)+1)) +
            ':l\nwait 30\nif r7==0 ret\nif rd==-1 run :a\nrun :l\n'
            ':r\nRD= -1\nret\n:x\nreinit\nret\n').encode('ascii')


def check_layout(info, banks):
    assert info['labels']['start'] == 0
    assert info['labels']['dispatch'] < 112
    for name in ('npc_dispatch','npc_fast_start','hole_start'):
        assert info['labels'][name] < 112
    assert max(banks) < 32
    for name in ('left','right','up','down'):
        assert info['labels'][name+'_fast_entry']-info['labels'][name+'_entry']==24
