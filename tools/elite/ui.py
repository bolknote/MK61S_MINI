from assembler import GLYPHS, ALPHABET, screen, CALL

def chunks(text):
    f=screen(text)
    return [sum(f[i+j]*256**j for j in range(3)) for i in range(0,12,3)]

def add_ui(a):
    m=a.module(2,'display')
    m.label('display').raw(0x2F,0x53)
    for r in range(4):m.ld(r).st(r+4)
    m.op('ret')
    m.label('name_alphabet').raw(*(GLYPHS[ch] for ch in ALPHABET))

    m=a.module(3,'glyphs')
    # Fixed four-byte entries, called only after the lookup arithmetic.
    for ch in '0123456789'+ALPHABET:
        m.raw(*(int(d) for d in f'{GLYPHS[ch]:03d}'),0x52)

    m=a.module(4,'arithmetic')
    for base in (10,16,100,256):m.label(f'mod{base}').mod(base).op('ret')
    m.label('glyph').n(4).op('*').n(336).op('+').st('E').raw(0x1F,0xAE).op('ret')

    m=a.module(18,'messages')
    for label,text in [('title','三 ELItE 三 СП'),('victory','YES. CLEAr СП'),
                       ('defeat','dEAd      СП'),('escape','SAFE      СП'),
                       ('invalid','ErrOr     СП'),('pirate','PIrAtE    СП'),
                       ('thargoid','tHArGOId  СП')]:
        m.label(label)
        for i,v in enumerate(chunks(text)[:3]):m.set(i,v)
        m.jump('text_end')
    m.label('text_end').set(3,chunks('          СП')[3]).jump('display')
    m.label('show_message').far(0x53,29*112+CALL).op('ret')

    m=a.module(19,'format')
    m.label('number_frame').ld('D').st(0).set(1,0).set(2,0).set(3,chunks('          СП')[3])
    m.raw(0x2F,0x02,0x2F,0x6C).jump('display')
    m.label('name_frame')
    for i,v in enumerate(chunks('          СП')):m.set(i,v)
    m.ptr('F','name_alphabet').raw(0x2F,0x00,0x2F,0x7C).jump('display')

def show_text(m, label):
    m.ptr('F',label).call('show_message')

def show_number(m, prefix):
    # X/RC from a page GET. Preserve it while setting the prefix.
    m.st('C').set('D',GLYPHS[prefix]).visit(29,'number_frame')

def show_name(m):
    m.st('C').visit(29,'name_frame')
