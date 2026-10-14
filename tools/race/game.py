"""RACE emits calculator bytecode; Python only builds the art and program.

R0..R3: packed display, R4: lane (-2..2),
R5: frame within section (0..5), R6: completed sections, R7: lives,
R8: damage cooldown, R9: bend, RA: rival lane, RB: sprite-group base,
RC: field selector, RD/RE: packed art words, RF: palette/steering address.
"""
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'elite'))
from assembler import Assembler, GLYPHS, screen, pack_number, bcd

SECTION_FRAMES = 6
SECTIONS = 20
RECOVERY = 3
WALL_LIMIT = 3
ART_BANK = 8
ART_HELPER = 63
ART_PALETTE = 87
ART_PER_BANK = 4
THUNK_BANK = 27
THUNK_STRIDE = 7
SPRITES_PER_RIVAL = 5 * (SECTION_FRAMES - 1)
BENDS = (0, 1, 1, 0, -1, -1)
RIVALS = (0, -1, 1, 0, 1, -1)
RADIUS = (0, 0, 1, 1, 2, 3, 4, 5, 6, 8, 10, 12)


def road_frame(lateral, phase):
    """Two pairs grow and step across left/right indicator stems.

    These are build-time sprites, not a host substitute for game physics.
    Camera offsets are baked into complete sprites.
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


def scene_frame(lateral, phase, rival):
    """Build a complete road/rival/guide sprite; no runtime pixel arithmetic."""
    camera = lateral * 5
    frame = road_frame(camera, phase % 6)
    depth = phase * 6 - 3
    other = rival * 5
    if depth < 6:
        cells = [(5, 0x48)]
    elif depth < 16:
        cell = int((other - camera) / 8) + 5
        cells = [(cell, 0x6B if cell in (5, 6) else 0x63)]
    elif depth < 26:
        cells = [(int((other - camera) / 5) + 5, 0x3F)]
    else:
        cell = int((other - camera) / 3) + 5
        cells = [(cell, 0x39), (cell + 1, 0x0F)]
    for cell, mask in cells:
        if 0 <= cell < 12:
            frame[cell] = mask
    target = -1 if rival > 0 else 1
    delta = (target - lateral) * 5
    cell = 5 if delta == 0 else max(0, min(11, int(delta / 3) + 5 + (delta > 0)))
    frame[cell] |= 128
    return frame


ART = [scene_frame(lateral, phase, rival)
       for rival in (-1, 0, 1) for lateral in range(-2, 3)
       for phase in range(1, SECTION_FRAMES)]


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
    m.label('tick').call('read_steering')
    m.ld(8).jz('cooldown_done').n(1).op('-').st(8)
    # K MR 5 increments its pointer before reading. Ignore the loaded value:
    # this advances the 0..5 frame counter with one existing ROM instruction.
    m.label('cooldown_done').raw(0xD5)
    m.ld(5).n(2).op('/', 'frac').jnz('bend_done')
    m.ld(4).ld(9).op('-').st(4)
    m.label('bend_done').ld(4).op('abs').n(WALL_LIMIT).op('-').jneg('wall_done')
    m.call('damage').jz('defeat').ld(4).raw(0x32).st(4)
    m.label('wall_done').ld(5).n(SECTION_FRAMES).op('-').jz('section_end')
    m.ld(8).n(RECOVERY).op('-').jz('checkpoint').call('draw_road').jump('tick')
    m.label('checkpoint').call('score').jump('tick')
    m.label('section_end').ld(4).ld('A').op('-').jnz('rival_done')
    m.call('damage').jz('defeat')
    m.label('rival_done')
    m.set(5, 0).add(6, 1).n(SECTIONS).op('-').jz('finish')
    m.call('section_parameters').jump('checkpoint')

    # The ROM's local indirect CALL truncates acos(0) to addresses 1/90/100.
    # Dispatch directly rather than testing 80 and 95 on every frame.
    m = a.module(1, 'angle-switch dispatch')
    m.raw(0x54)
    m.label('steer_left').ld(4).n(1).op('-').st(4).op('ret')
    m.label('read_steering').op('cx').raw(0x1A).st('F').raw(0x8F)
    m.raw(*([0x54] * (90 - 11)))
    m.label('steer_right').ld(4).n(1).op('+').st(4).op('ret')
    m.raw(*([0x54] * 4))
    m.label('steer_neutral').op('ret')

    m = a.module(2, 'damage and section parameters')
    m.label('damage').ld(8).jnz('damage_end').add(7, -1).set(8, RECOVERY)
    m.label('damage_end').ld(7).op('ret')
    m.label('section_parameters').ld(6).mod(6).n(14).op('*')
    m.ptr('E', 'section_table').op('+').st('E').raw(0x1F, 0xAE).op('ret')

    m = a.module(3, 'score and results')
    m.label('score')
    # Together these fields cover all twelve cells; no separate clear and no
    # saved/rebuilt section digits. Put lives at cell 1 after the section.
    m.raw(0x2F, 0x0A, 0x2F, 0x66, 0x2F, 0x06, 0x2F, 0x67)
    m.ld(0).n(GLYPHS['0'] * 65536 + GLYPHS['0'] - GLYPHS['L']).op('-').st(0)
    m.add(1, GLYPHS['n'] - GLYPHS['0'])
    m.set(2, GLYPHS['2'] * 65536).set(3, GLYPHS['0']).raw(0x2F, 0x53).op('ret')
    m.label('finish'); clear_frame(m)
    m.ld(7).st('D').raw(0x2F, 0x04, 0x2F, 0x6D)
    for reg, word in enumerate(packed(screen('FInISH 20 L '))[:3]):
        m.set(reg, word)
    m.ld(3).n(GLYPHS['L'] * 256 - GLYPHS['0'] * 257).op('+').st(3)
    m.raw(0x2F, 0x53).label('finish_stop').op('stop').jump('new_game')
    m.label('defeat'); clear_frame(m)
    m.ld(6).st('E').raw(0x2F, 0x00, 0x2F, 0x6E)
    for reg, word in enumerate(packed(screen('CrASH       '))[:2]):
        m.set(reg, word)
    m.set(3, GLYPHS['2'] + 256 * GLYPHS['0']).raw(0x2F, 0x53).label('defeat_stop').op('stop').jump('new_game')

    m = a.module(4, 'section pattern')
    m.label('section_table')
    for bend, rival in zip(BENDS, RIVALS):
        values = [0x0D if bend == 0 else abs(bend)]
        if bend < 0: values.append(0x0B)
        values.append(0x49)
        values.append(0x0D if rival == 0 else abs(rival))
        if rival < 0: values.append(0x0B)
        values.append(0x4A)
        base = (THUNK_BANK * 112 - THUNK_STRIDE +
                (rival + 1) * SPRITES_PER_RIVAL * THUNK_STRIDE)
        values += list(map(int, str(base)))
        values += [0x4B, 0x52]
        m.raw(*values, *([0x54] * (14 - len(values))))

    m = a.module(5, 'complete frame lookup')
    # RB already includes the rival group and code-table base. Each seven-byte
    # thunk carries its bank and field index, eliminating runtime /4, integer,
    # fractional-part and bank-address calculations.
    m.label('draw_road').ld(4).n(2).op('+').n(5).op('*')
    m.ld(5).op('+').n(THUNK_STRIDE).op('*').ld('B').op('+').st('E').raw(0x1F, 0xAE)
    m.raw(0x2F, 0x00, 0x2F, 0x7D, 0x2F, 0x7E, 0x2F, 0x53).op('ret')

    for page in range((len(ART) + ART_PER_BANK - 1) // ART_PER_BANK):
        bank = ART_BANK + page
        frames = ART[page * ART_PER_BANK:(page + 1) * ART_PER_BANK]
        alphabet = sorted({mask for frame in frames for mask in frame})
        assert len(alphabet) <= 16, (page, alphabet)
        words = []
        for frame in frames:
            codes = [alphabet.index(mask) for mask in frame]
            words += [sum(codes[base + i] << (4 * (5 - i)) for i in range(6))
                      for base in (0, 6)]
        words += [0] * (8 - len(words))
        words.append(bank * 112 + ART_PALETTE)
        m = a.module(bank, f'complete sprites {page}')
        m.raw(*b''.join(pack_number(value) for value in words))
        m.label(f'frame_page_{page}')
        # X = 0,2,4,6. Open nine fields, fetch two packed hex words and the
        # palette into RD/RE/RF, then restore all R0..R8 and the bank's data.
        m.raw(0x1F, 0x56, bank, 0x55, 0x68, 0x4F, 0x14, 0x48,
              0xD8, 0x4D, 0x68, 0x0E, 0x01, 0x10, 0x48, 0xD8, 0x4E,
              0x6F, 0x48, 0x55, 0x1F, 0x56, bank, 0x52)
        m.label(f'frame_palette_{page}').raw(*alphabet, *([0] * (16 - len(alphabet))))
    per_bank = 112 // THUNK_STRIDE
    for page in range((len(ART) + per_bank - 1) // per_bank):
        m = a.module(THUNK_BANK + page, f'frame selectors {page}')
        for index in range(page * per_bank, min(len(ART), (page + 1) * per_bank)):
            field = (index % ART_PER_BANK) * 2
            helper = (ART_BANK + index // ART_PER_BANK) * 112 + ART_HELPER
            m.label(f'select_frame_{index}').raw(
                0x0D if field == 0 else field, 0x4C,
                0x1F, 0x51, *bcd(helper), 0x54)
    # Native extended conditions avoid the ROM's operand cycles.
    for module in a.modules:
        for item in module.items:
            if item.kind == 'branch' and item.value in (0x57, 0x59, 0x5C, 0x5E):
                item.force_far = True
    return a


def check_layout(info):
    labels = info['labels']
    assert labels['steer_left'] == 113
    assert labels['steer_right'] == 202
    assert labels['steer_neutral'] == 212
    for page in range((len(ART) + ART_PER_BANK - 1) // ART_PER_BANK):
        bank = ART_BANK + page
        assert labels[f'frame_page_{page}'] == bank * 112 + ART_HELPER
        assert labels[f'frame_palette_{page}'] == bank * 112 + ART_PALETTE
    for index in range(len(ART)):
        assert labels[f'select_frame_{index}'] == THUNK_BANK * 112 + index * THUNK_STRIDE
    assert info['occupied_bytes'] <= 32 * 112
