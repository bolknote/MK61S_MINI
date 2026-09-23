from assembler import GLYPHS, ALPHABET, screen, CALL

def chunks(text):
    f=screen(text)
    return [sum(f[i+j]*256**j for j in range(3)) for i in range(0,12,3)]

# The unused ninth word of the screen page is a persistent frame template.
FRAME_SUFFIX_WORD = chunks('          СП')[3]

def add_ui(a):
    m=a.module(2,'display')
    # 2F 53 compares with the visible frame itself; no second software copy.
    m.label('display').raw(0x2F,0x53).op('ret')
    m.label('name_alphabet').raw(*(GLYPHS[ch] for ch in ALPHABET))

    m=a.module(3,'glyphs')
    # Only the six commodity prefixes use this fixed four-byte lookup.
    # Keep entry zero so the existing 4*index+336 addressing stays valid.
    for ch in '0123456':
        m.raw(*(int(d) for d in f'{GLYPHS[ch]:03d}'),0x52)

    m=a.module(4,'arithmetic')
    for base in (10,16,100,256):
        m.label(f'mod{base}')
        # Decimal shifts preserve all eight significant digits. Binary
        # divisors still need subtraction: their fractions lose low bits.
        if base in (10,100):m.n(base).op('/','frac').n(base).op('*')
        else:m.mod(base)
        m.op('ret')
    m.label('glyph').n(4).op('*').n(336).op('+').st('E').raw(0x1F,0xAE).op('ret')

    m=a.module(18,'messages')
    for label,text in [('title','三 ELItE 三 СП'),('victory','YES. CLEAr СП'),
                       ('defeat','dEAd      СП'),('escape','SAFE      СП'),
                       ('invalid','ErrOr     СП'),('pirate','PIrAtE    СП'),
                       ('thargoid','tHArGOId  СП')]:
        m.label(label)
        for i,v in enumerate(chunks(text)[:3]):m.set(i,v)
        m.jump('text_end')
    m.label('text_end').ld(8).st(3).jump('display')
    m.label('show_message').far(0x53,29*112+CALL).op('ret')

    m=a.module(19,'format')
    m.label('number_frame').ld('D').st(0).op('cx').st(1).st(2).ld(8).st(3)
    m.raw(0x2F,0x02,0x2F,0x6C).jump('display')
    m.label('name_frame')
    m.op('cx').st(0).st(1).st(2).ld(8).st(3)
    m.ptr('F','name_alphabet').raw(0x2F,0x00,0x2F,0x7C).jump('display')

def show_text(m, label):
    m.ptr('F',label).call('show_message')

def show_number(m, prefix):
    # X/RC from a page GET. Preserve it while setting the prefix.
    m.st('C').set('D',GLYPHS[prefix]).visit(29,'number_frame')

def show_name(m):
    m.st('C').visit(29,'name_frame')
