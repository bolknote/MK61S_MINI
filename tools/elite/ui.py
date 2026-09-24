from assembler import GLYPHS, ALPHABET, screen, CALL

def chunks(text):
    f=screen(text)
    return [sum(f[i+j]*256**j for j in range(3)) for i in range(0,12,3)]

# The ninth word of the screen page is a persistent frame template.
FRAME_SUFFIX_WORD = chunks('          СП')[3]

DRONE_MASK = 0x63  # upper rectangle: a small ship, distinct from a digit
BAR_MASK = 0x36    # two full-height vertical strokes

def add_ui(a):
    m=a.module(2,'name alphabet')
    # Publish/return is three bytes: inline it instead of a four-byte far JP.
    # 2F 53 compares with the visible frame itself; no second software copy.
    m.label('name_alphabet').raw(*(GLYPHS[ch] for ch in ALPHABET))

    m=a.module(3,'glyphs')
    # Entry zero is the carrier; 1..6 also serve the commodity prefixes.
    # Start at local 00: 4*index is already a native indirect address.
    m.label('glyph_table')
    for ch in 'H123456':
        m.raw(*(int(d) for d in f'{GLYPHS[ch]:03d}'),0x52)

    m.label('glyph').n(4).op('*').st('E').raw(0x8E)

    # Seven four-byte glyph records and the five-byte lookup leave local 33.
    m.label('bar_patterns').raw(*(byte for value in (0,65536,69632,69888,69904,69905)
                                for byte in [*(int(d) for d in f'{value:05d}'),0x52]))
    m.label('bar_pattern').n(6).op('*').n(33).op('+').st('E').raw(0x8E)

    m=a.module(23,'range table')
    # A second table at local 00 avoids constructing an absolute pointer.
    m.label('range_patterns').raw(*(byte for value in (0x100020,0x010020,0x001020,0x000120,0x000030,0x000021)
                                  for byte in [*(int(d) for d in f'{value:07d}'),0x52]))
    m.label('range_pattern').n(8).op('*').st('E').raw(0x8E)

    m=a.module(4,'arithmetic')
    # mod10 has no callers; the two mod100 expressions are shorter in place
    # once their shared procedure and its bank continuation are removed.
    for base in (16,256):
        m.label(f'mod{base}')
        # mod16 is exact on its 0..65535 domain.
        # The 24-bit world codes still need integer subtraction for mod256.
        if base==16:m.n(base).op('/','frac').n(base).op('*')
        else:m.mod(base)
        m.op('ret')

    m=a.module(18,'messages')
    for label,text in [('title','三 ELItE 三 СП'),('victory','YES. CLEAr СП'),
                       ('defeat','dEAd      СП'),('escape','SAFE      СП'),
                       ('invalid','ErrOr     СП'),('pirate','PIrAtE    СП'),
                       ('thargoid','tHArGOId  СП')]:
        m.label(label)
        for i,v in enumerate(chunks(text)[:3]):m.set(i,v)
        m.jump('text_end')
    m.label('text_end').ld(8).st(3).raw(0x2F,0x53).op('ret')
    m.label('show_message').far(0x53,29*112+CALL).op('ret')

    # Frequent FRAME callbacks have three-digit pointers in this low bank.
    m=a.module(8,'format')
    m.label('number_frame').ld('D').st(0).ld(8).st(3)
    m.raw(0x2F,0x02,0x2F,0x6C,0x2F,0x53).op('ret')
    m.label('name_frame')
    m.op('cx').st(2).ld(8).st(3)
    m.ptr('F','name_alphabet',lift=False).raw(0x2F,0x00,0x2F,0x7C,0x2F,0x53).op('ret')

    # Battle: RC hull, RB live drones, RD target mask minus decimal zero.
    # Gauge: RC value, RA selects the prefix, RE holds the bar pattern.
    # Both formatters build the page before 2F 53 publishes the twelve slots.
    # The six-slot formation changes only on launch or destruction. Cache
    # its two packed words in FRAME R4/R5, keyed by the live count in R6.
    # Ordinary turns only copy these words, then replace the exact hull.
    m.label('battle_frame').ld(8).st(3).raw(0x2F,0x02,0x2F,0x6C).ld('B').ld(6).op('-').jz('formation_ready')
    m.ld('B').st(6).call('bar_pattern').n(16).op('*').st('E')
    m.ptr('F','drone_alphabet',lift=False).raw(0x2F,0x00,0x2F,0x7E).ld(0).st(4).ld(1).st(5)
    m.label('formation_ready').ld(4).st(0).ld(5).st(1)
    m.ld(2).ld('D').op('+').st(2).raw(0x2F,0x53).op('ret')
    m.label('gauge_frame').ld('A').ld(7).op('*').ld('E').op('+').st('E').ptr('F','bar_alphabet',lift=False)
    m.label('instrument_frame').ld(8).st(3).raw(0x2F,0x02,0x2F,0x6C,0x2F,0x00,0x2F,0x7E)
    m.ld(2).n(63).op('-').st(2).raw(0x2F,0x53).op('ret')

    # Five bars, rounded upwards: even a small nonzero reserve is visible.
    # RC value, RA view/prefix, RE units per cell. Preserves outer R0..R8.
    # A few spare bytes at a bank end would otherwise split this hot entry
    # and add a bridge to every gauge. Keep its final tail call with it.
    m.label('draw_gauge',keep_block=True).ld('C').ld('E').n(1).op('-','+').ld('E').op('/','int')
    m.call('bar_pattern').st('E').visit(29,'gauge_frame').op('ret')
    # rNN, player U, six range cells. The dot in slot eight is the fixed
    # laser boundary; enemies beyond 18 are always on its far side.
    m.label('range_frame').raw(0x2F,0x07,0x2F,0x6C)
    m.ld(0).n(GLYPHS['r']-63).op('+').st(0).set(1,GLYPHS['U']).ld(8).st(3)
    m.ptr('F','range_alphabet',lift=False).raw(0x2F,0x04,0x2F,0x7E,0x2F,0x53).op('ret')
    m.label('draw_range').ld('C').n(19).op('-').jge('range_far')
    m.ld('C').n(4).op('/','int').jump('range_index')
    m.label('range_far').raw(5)
    m.label('range_index').call('range_pattern').st('E')
    m.visit(29,'range_frame').op('ret')
    # The two binary alphabets use only entries 0/1. Their remaining entries
    # share storage with the next alphabet; every 2F 7n still has 16 bytes.
    m.label('drone_alphabet').raw(0,DRONE_MASK)
    m.label('bar_alphabet').raw(0,BAR_MASK,GLYPHS['H'],GLYPHS['S'],GLYPHS['F'],GLYPHS['t'],0,GLYPHS['U'])
    m.label('range_alphabet').raw(64,GLYPHS['H'],192,GLYPHS['H']|128,*([0]*12))

def show_text(m, label):
    m.ptr('F',label,lift=False).call('show_message')

def show_number(m, prefix):
    # X/RC from a page GET. Preserve it while setting the prefix.
    m.st('C').set('D',GLYPHS[prefix]).visit(29,'number_frame')

def show_name(m):
    m.st('C').visit(29,'name_frame')
