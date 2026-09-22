from assembler import GLYPHS, ALPHABET, screen

def chunks(text):
    f=screen(text)
    return [sum(f[i+j]*256**j for j in range(3)) for i in range(0,12,3)]

def add_ui(a):
    m=a.module(2,'display')
    m.label('display').set('B',0).raw(0x2F,0)
    m.label('display_word').raw(0xDB).st('C')
    m.ld('B').n(4).op('+').st('E').raw(0xDE).st('D').set('F',3)
    m.label('display_cell').ld('C').call('mod256').st('E')
    m.ld('D').call('mod256').ld('E').op('-').jz('display_skip')
    m.ld('E').raw(0x2F,0x0E).jump('display_shift')
    m.label('display_skip').raw(0x2F,0x25)
    m.label('display_shift').ld('C').n(256).op('/','int').st('C')
    m.ld('D').n(256).op('/','int').st('D').add('F',-1).jnz('display_cell')
    m.ld('B').n(4).op('+').st('E').raw(0xDB,0xBE)
    m.add('B',1).n(4).op('-').jneg('display_word').op('ret')

    m=a.module(3,'glyphs')
    # Fixed four-byte entries, called only after the lookup arithmetic.
    for ch in '0123456789'+ALPHABET:
        m.raw(*(int(d) for d in f'{GLYPHS[ch]:03d}'),0x52)

    m=a.module(4,'arithmetic')
    for base in (10,16,100,256):m.label(f'mod{base}').mod(base).op('ret')
    m.label('glyph').n(4).op('*').n(336).op('+').st('E').raw(0x1F,0xAE).op('ret')
    m.label('frame_put').st(8).ld('B').n(3).op('/','int').st('E')
    # Integer factors avoid the ROM power function's rounding error.
    m.ld('B').mod(3).jz('factor1').n(1).op('-').jz('factor256')
    m.n(65536).jump('factor_ready')
    m.label('factor1').n(1).jump('factor_ready')
    m.label('factor256').n(256)
    m.label('factor_ready').st('D')
    m.ld(8).ld('D').op('*').raw(0xDE).op('+').raw(0xBE).op('ret')

    m=a.module(18,'messages')
    for label,text in [('title','三 ELItE 三 СП'),('victory','YES. CLEAr СП'),
                       ('defeat','dEAd      СП'),('escape','SAFE      СП'),
                       ('invalid','ErrOr     СП'),('pirate','PIrAtE    СП'),
                       ('thargoid','tHArGOId  СП')]:
        m.label(label)
        for i,v in enumerate(chunks(text)[:3]):m.set(i,v)
        m.jump('text_end')
    m.label('text_end').set(3,chunks('          СП')[3]).op('ret')
    m.label('show_message').far(0x53,29*112+78).visit(29,'display').op('ret')

    m=a.module(19,'format')
    m.label('number_frame').ld('D').st(0).set(1,0).set(2,0).set(3,chunks('          СП')[3]).set('B',9)
    m.label('number_digit').ld('C').call('mod10').call('glyph').call('frame_put')
    m.ld('C').n(10).op('/','int').st('C').add('B',-1).n(1).op('-').jnz('number_digit').op('ret')
    m.label('name_frame')
    for i,v in enumerate(chunks('          СП')):m.set(i,v)
    m.set('B',5)
    m.label('name_digit').ld('C').call('mod16').n(10).op('+').call('glyph').call('frame_put')
    m.ld('C').n(16).op('/','int').st('C').add('B',-1).jge('name_digit').op('ret')

def show_text(m, label):
    m.ptr('F',label).call('show_message')

def show_number(m, prefix):
    # X/RC from a page GET. Preserve it while setting the prefix.
    m.st('C').set('D',GLYPHS[prefix]).visit(29,'number_frame').visit(29,'display')

def show_name(m):
    m.st('C').visit(29,'name_frame').visit(29,'display')
