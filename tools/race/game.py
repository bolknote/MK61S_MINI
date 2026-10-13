"""RACE emits calculator bytecode; Python only builds the art and program.

R0..R3: packed display, R4: lateral position in tenths of a lane,
R5: frame within section (0..35), R6: completed sections, R7: lives,
R8: damage cooldown, R9: bend, RA: rival lane, RC: input/scratch,
RD/RE: art/overlay scratch, RF: alphabet or byte weight.
"""
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'elite'))
from assembler import Assembler, GLYPHS, screen

SECTION_FRAMES = 36
SECTIONS = 20
RECOVERY = 15
WALL_LIMIT = 13
ART_BANK = 8
ART_STRIDE = 19
ART_PER_BANK = 5
BENDS = (0, 1, 1, 0, -1, -1)
RIVALS = (0, -8, 8, 0, 8, -8)
RADIUS = (0, 0, 1, 1, 2, 3, 4, 5, 6, 8, 10, 12)


def road_frame(lateral, phase):
    """Two pairs grow and step across left/right indicator stems.

    These are build-time sprites, not a host substitute for game physics.
    Nine camera offsets cover every safe lateral position.
    """
    masks = [0] * 12
    near = 11.5 - lateral * .1 * 11.5 / 1.55
    left_cell = math.floor((near - 11.5) / 2)
    right_cell = math.floor((near + 11.5) / 2)
    for depth in (phase, phase + 6):
        width = .5 + RADIUS[depth]
        center = 11.5 - lateral * .1 * width / 1.55
        for column in (math.floor(center - width + .5), math.floor(center + width + .5)):
            if max(0, left_cell * 2) <= column <= min(23, right_cell * 2 + 1):
                masks[column // 2] |= ((0x30 if depth >= 4 else 0x20)
                                      if column % 2 == 0 else
                                      (0x06 if depth >= 4 else 0x02))
    if 0 <= left_cell < 12:
        masks[left_cell] = 0x39
    if 0 <= right_cell < 12:
        masks[right_cell] = 0x0F
    masks[5] |= 8
    masks[6] |= 8
    return masks


ART = [road_frame(lateral, phase) for lateral in range(-12, 13, 3) for phase in range(6)]
ALPHABET = sorted({mask for frame in ART for mask in frame})
assert len(ALPHABET) <= 16
ALPHABET += [0] * (16 - len(ALPHABET))


def packed(frame):
    return [sum(frame[i + j] << (8 * j) for j in range(3)) for i in range(0, 12, 3)]


def text(m, value):
    for reg, word in enumerate(packed(screen(value))):
        m.set(reg, word)
    return m.raw(0x2F, 0x53)


def clear_frame(m):
    return m.op('cx').st(0).st(1).st(2).st(3)


def create_game():
    a = Assembler()
    m = a.module(0, 'start and race loop')
    m.label('start').raw(0x2F, 0x50, 0x2F, 0x2A)
    text(m, 'rACE L3 20СП').op('stop')
    m.label('new_game').op('cx').st(4).st(5).st(6).st(8).set(7, 3)
    m.call('section_parameters').call('score')
    m.label('tick').call('read_steering').ld(4).ld('C').op('+').st(4)
    m.ld(8).jz('cooldown_done').n(1).op('-').st(8)
    m.label('cooldown_done').add(5, 1)
    m.ld(5).n(3).op('/', 'frac').jnz('bend_done')
    m.ld(4).ld(9).op('-').st(4)
    m.label('bend_done').ld(4).op('abs').n(WALL_LIMIT).op('-').jneg('wall_done')
    m.call('damage').ld(4).raw(0x32).n(10).op('*').st(4)
    m.label('wall_done').ld(5).n(33).op('-').jnz('rival_done')
    m.ld(4).ld('A').op('-', 'abs').n(6).op('-').jge('rival_done').call('damage')
    m.label('rival_done').ld(7).jz('defeat')
    m.ld(5).n(SECTION_FRAMES).op('-').jneg('section_done')
    m.set(5, 0).add(6, 1).n(SECTIONS).op('-').jz('finish')
    m.call('section_parameters')
    m.label('section_done').ld(8).n(RECOVERY).op('-').jz('checkpoint')
    m.ld(5).jz('checkpoint').call('draw_road').jump('tick')
    m.label('checkpoint').call('score').jump('tick')

    m = a.module(1, 'steering and damage')
    # arccos(0) = 1.5707963 (P), 100 (GRD), 90 (G), read during RUN.
    m.label('read_steering').op('cx').raw(0x1A).n(80).op('-').jneg('steer_left')
    m.n(15).op('-').jneg('steer_right').set('C', 0).op('ret')
    m.label('steer_left').set('C', -1).op('ret')
    m.label('steer_right').set('C', 1).op('ret')
    m.label('damage').ld(8).jnz('damage_end').add(7, -1).set(8, RECOVERY)
    m.label('damage_end').op('ret')
    # Six section entries of equal width, selected by an absolute call.
    m.label('section_parameters').ld(6).mod(6).n(10).op('*')
    m.ptr('E', 'section_table').op('+').st('E').raw(0x1F, 0xAE).op('ret')

    m = a.module(2, 'frame selection and publication')
    m.label('draw_road').ld(4).n(13).op('+').n(3).op('/', 'int').n(6).op('*').st('D')
    m.ld(5).mod(6).ld('D').op('+').st('D')
    # Five 19-byte records per 112-byte bank. Addressing avoids ROM loops.
    m.ld('D').n(5).op('/', 'int').st('E').n(112).op('*').st('C')
    m.ld('D').ld('E').n(5).op('*', '-').n(ART_STRIDE).op('*')
    m.ld('C').op('+').n(ART_BANK * 112).op('+').st('E').raw(0x1F, 0xAE)
    m.ptr('F', 'road_alphabet').raw(0x2F, 0x00, 0x2F, 0x7D, 0x2F, 0x7E)
    m.call('draw_rival').call('draw_guide').raw(0x2F, 0x53).op('ret')

    m = a.module(3, 'approaching rival')
    m.label('draw_rival').ld(5).n(34).op('-').jge('rival_hidden')
    m.ld(5).n(6).op('-').jneg('rival_far')
    m.n(10).op('-').jneg('rival_small')
    m.n(10).op('-').jneg('rival_medium')
    m.ld('A').ld(4).op('-').n(3).op('/', 'int').n(5).op('+').st('E')
    m.set('D', 0x39).call('paint_cell').add('E', 1).set('D', 0x0F).jump('paint_cell')
    m.label('rival_far').set('E', 5).set('D', 0x48).jump('paint_cell')
    m.label('rival_small').ld('A').ld(4).op('-').n(8).op('/', 'int').n(5).op('+').st('E')
    m.set('D', 0x63).ld('E').n(5).op('-').jz('rival_on_nose')
    m.n(1).op('-').jnz('paint_cell')
    m.label('rival_on_nose').set('D', 0x6B).jump('paint_cell')
    m.label('rival_medium').ld('A').ld(4).op('-').n(5).op('/', 'int').n(5).op('+').st('E')
    m.set('D', 0x3F).jump('paint_cell')
    m.label('rival_hidden').op('ret')

    m = a.module(4, 'safe-path marker')
    m.label('draw_guide').ld('A').jge('guide_test_right')
    m.label('guide_right').n(9).jump('guide_target')
    m.label('guide_test_right').jz('guide_right').n(-9)
    m.label('guide_target').ld(4).op('-').st('D').op('abs').n(3).op('-').jneg('guide_center')
    m.ld('D').n(3).op('/', 'int').n(5).op('+').st('E')
    m.ld('D').jneg('guide_clip').add('E', 1)
    m.label('guide_clip').ld('E').jneg('guide_left_edge').n(12).op('-').jneg('guide_place')
    m.set('E', 11).jump('guide_place')
    m.label('guide_left_edge').set('E', 0).jump('guide_place')
    m.label('guide_center').set('E', 5)
    m.label('guide_place').call('cell_weight').ld('F').n(128).op('*').raw(0xDC).op('+').raw(0xBC).op('ret')

    m = a.module(5, 'atomic cell overlays')
    # RE: cell, RD: replacement mask. Keep the cockpit's bottom strokes.
    # RC indexes R0..R3 through ordinary K MR/K PM; RF is the byte weight.
    m.label('paint_cell').ld('E').jneg('paint_end').n(12).op('-').jge('paint_end')
    m.call('cell_weight').raw(0xDC).ld('F').op('/', 'int', 'enter')
    m.n(256).op('/', 'int').n(256).op('*', '-')
    m.ld('D').op('swap', '-').ld('F').op('*').raw(0xDC).op('+').raw(0xBC)
    m.label('paint_end').op('ret')
    m.label('cell_weight').ld('E').n(3).op('/', 'int').st('C')
    m.n(3).op('*').ld('E').op('swap', '-').jz('weight_one')
    m.n(1).op('-').jz('weight_256').set('F', 65536).op('ret')
    m.label('weight_one').set('F', 1).op('ret')
    m.label('weight_256').set('F', 256).op('ret')

    m = a.module(6, 'score and results')
    m.label('score'); clear_frame(m)
    m.ld(6).n(1).op('+').st('E').raw(0x2F, 0x0A, 0x2F, 0x6E).ld(1).st('E')
    m.ld(7).st('D').raw(0x2F, 0x05, 0x2F, 0x6D)
    # Decimal formatters paint leading zero glyphs, not blank masks.
    m.ld(0).mod(256).n(256).op('*').n(GLYPHS['L']).op('+').st(0)
    m.ld('E').n(GLYPHS['n'] - GLYPHS['0']).op('+').st(1)
    m.set(2, GLYPHS['2'] * 65536).set(3, GLYPHS['0']).raw(0x2F, 0x53).op('ret')
    m.label('finish'); clear_frame(m)
    m.ld(7).st('D').raw(0x2F, 0x04, 0x2F, 0x6D)
    for reg, word in enumerate(packed(screen('FInISH 20 L '))[:3]):
        m.set(reg, word)
    m.ld(3).n(GLYPHS['L'] * 256 - GLYPHS['0'] * 257).op('+').st(3)
    m.raw(0x2F, 0x53).op('stop').jump('new_game')
    m.label('defeat'); clear_frame(m)
    m.ld(6).st('E').raw(0x2F, 0x00, 0x2F, 0x6E)
    for reg, word in enumerate(packed(screen('CrASH       '))[:2]):
        m.set(reg, word)
    m.set(3, GLYPHS['2'] + 256 * GLYPHS['0']).raw(0x2F, 0x53).op('stop').jump('new_game')

    m = a.module(7, 'section pattern and alphabet')
    m.label('section_table')
    for index, (bend, rival) in enumerate(zip(BENDS, RIVALS)):
        # Literal, sign and stores padded to a fixed ten-byte record.
        values = [0x0D if bend == 0 else abs(bend)]
        if bend < 0: values.append(0x0B)
        values.append(0x49)
        values.append(0x0D if rival == 0 else abs(rival))
        if rival < 0: values.append(0x0B)
        values += [0x4A, 0x52]
        m.raw(*values, *([0x54] * (10 - len(values))))
    m.label('road_alphabet').raw(*ALPHABET)

    for bank in range(11):
        m = a.module(ART_BANK + bank, f'wall sprites {bank}')
        for index in range(bank * ART_PER_BANK, min(len(ART), (bank + 1) * ART_PER_BANK)):
            frame = ART[index]
            codes = [ALPHABET.index(mask) for mask in frame]
            # Formatter writes most significant hex digit first.
            words = [sum(codes[base + i] << (4 * (5 - i)) for i in range(6))
                     for base in (0, 6)]
            m.label(f'art_{index}')
            for reg, word in zip(('D', 'E'), words):
                m.raw(*map(int, f'{word:08d}')).st(reg)
            m.op('ret')
    return a


def check_layout(info):
    labels = info['labels']
    for index in range(len(ART)):
        expected = (ART_BANK + index // ART_PER_BANK) * 112 + (index % ART_PER_BANK) * ART_STRIDE
        assert labels[f'art_{index}'] == expected, (index, labels[f'art_{index}'], expected)
    assert labels['section_table'] // 112 == 7
    assert labels['road_alphabet'] == 7 * 112 + 60
    assert info['occupied_bytes'] <= 32 * 112
