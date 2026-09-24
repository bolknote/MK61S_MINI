"""ELITE module sources. All operations emit ordinary MK61/MK61s bytecode."""
from assembler import Assembler, ALPHABET, GLYPHS, screen
from ui import add_ui, show_text, show_number, show_name, FRAME_SUFFIX_WORD
from economy import add_economy, dynamic_get
from combat import add_combat

def create_game():
    a=Assembler()
    a.data={
        24:[1000,0,0,0,84,42,40,0,12345 % 16],
        25:[0,0,0,0,0,0,1010420,3,0],
        26:[0,0,0,30,30,30,30,30,30],
        27:[0,0,0,0,0,0,0,0,0],
        28:[0]*9,
        29:[0]*7+[1048576,FRAME_SUFFIX_WORD],
    }
    m=a.module(0,'kernel')
    m.label('start').raw(0x2F,0x50,0x2F,0x2A).set(9,0).set('A',0)
    show_text(m,'title');m.op('cx','stop')
    m.label('new_game').visit(24,'init_pilot').visit(25,'init_hold')
    m.op('cx').call('world').put(24,2).call('arrive')
    m.label('redraw').call('show').op('cx','stop')
    m.label('main').st(0).op('frac').jnz('input_invalid')
    # R9 is a local handler address as well as the mode flag. Combat uses
    # its negative form; ordinary K BP 9 preserves the sign and low digits.
    m.ld(0).jneg('input_invalid').raw(0x89)
    m.label('result_input_entry').call('arrive').jump('redraw')
    m.label('port_input_entry').call('port_input').jump('redraw')
    m.label('combat_input_entry').call('combat_input').jump('redraw')
    m.label('input_invalid').call('bad_action').jump('redraw')
    m.label('bad_action').set('A',99).op('ret')

    m=a.module(12,'input')
    m.label('port_input').ld(0).n(10).op('-').jneg('set_view')
    m.n(60).op('-').jge('select_check')
    m.n(10).op('+').jz('jump')
    m.n(10).op('+').jge('station_check')
    m.ld(0).st(1).raw(0x0C).st(1).n(6).op('-').jge('bad_action')
    m.ld(0).ld(1).op('-').st(8).n(30).op('-').jneg('set_view')
    m.n(5).op('swap','-').raw(0x32).st(7).jump('trade')
    m.label('station_check').n(4).op('-').jge('bad_action').jump('station')
    m.label('select_check').n(256).op('-').jge('bad_action').jump('select_world')
    m.label('set_view').ld(0).st('A').op('ret')

    m=a.module(17,'views')
    m.label('show').ld('A').n(99).op('-').jz('show_invalid').jge('show_result')
    m.ld(9).jge('port_view')
    m.ld('A').jz('combat_view').n(9).op('-').jge('combat_view')
    m.label('port_view').ld('A').n(9).op('-').jz('distance_view')
    m.ld('A').jz('show_world').ld('A').n(8).op('-').jz('show_destination')
    m.ld('A').n(10).op('-').jneg('show_stat')
    m.ld('A').n(20).op('-').jneg('show_price')
    m.n(10).op('-').jge('show_cached_price')
    m.ld('A').n(20).op('-').st(1);dynamic_get(m,25,1)
    m.jump('good_prefix')
    # Views 30..35 are one-use trade results in RC. Restore the normal price
    # view before drawing, so the next command uses the usual dispatch.
    m.label('show_cached_price').ld('A').n(20).op('-').st('A').jump('good_prefix')
    m.label('show_price').ld('A').n(10).op('-').st(1).call('price').st('C')
    m.label('good_prefix').ld(1).n(1).op('+').call('glyph').st('D').jump('draw_number')
    m.label('show_stat').ld('A').n(7).op('-').jz('show_hold')
    m.ld('A').n(6).op('-').jz('show_missiles')
    m.ld('A').n(2).op('+').st('B').ld('A').n(1).op('-').jnz('stat_get').set('B',0)
    m.label('stat_get').far(0x53,24*112+63)
    m.ld('A').n(1).op('-').jz('show_credits')
    m.set('E',20).ld('A').n(3).op('-').jnz('draw_gauge').set('E',12).jump('draw_gauge')
    m.label('show_missiles').get(25,7).set('D',GLYPHS['r']).jump('draw_number')
    m.label('show_credits').set('D',GLYPHS['C']).jump('draw_number')
    m.label('show_hold').visit(25,'sum_hold').set('E',4).jump('draw_gauge')
    m.label('show_world').get(24,1).jump('draw_name')
    m.label('show_destination').get(24,2)
    m.label('draw_name');show_name(m);m.op('ret')
    m.label('draw_number').visit(29,'number_frame').op('ret')
    m.label('show_invalid');show_text(m,'invalid');m.op('ret')
    add_ui(a)
    add_economy(a)
    add_combat(a)
    return a


def check_layout(info):
    """Guard addresses embedded in the native, one-byte indirect jumps."""
    labels=info['labels']
    exact={'glyph_table':3*112, 'bar_patterns':3*112+33,
           'range_patterns':23*112}
    for label,address in exact.items():
        if labels[label]!=address:
            raise ValueError(f'{label} must stay at {address} for its local lookup')
    for label,bank in (('glyph',3),('bar_pattern',3),('range_pattern',23)):
        if labels[label]//112!=bank:
            raise ValueError(f'{label} must share bank {bank} with its table')
    # Negative native selectors retain their last two digits. Every mode
    # handler must therefore remain in 01..99 of the dispatcher's bank 0.
    for label in ('main','new_game','port_input_entry','combat_input_entry','result_input_entry'):
        if not 0<labels[label]<100:
            raise ValueError(f'{label} must stay within bank 0, addresses 01..99')
