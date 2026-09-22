"""ELITE module sources. All operations emit ordinary MK61/MK61s bytecode."""
from assembler import Assembler, ALPHABET, GLYPHS, screen
from ui import add_ui, show_text, show_number, show_name
from economy import add_economy, dynamic_get
from combat import add_combat

def create_game():
    a=Assembler()
    a.data={
        24:[1000,0,0,0,84,42,40,0,12345],
        25:[0,0,0,0,0,0,1010420,3,0],
        26:[0,0,0,30,30,30,30,30,30],
        27:[0,0,0,0,0,0,0,0,0],
        28:[0]*9,
        29:[0]*9,
    }
    m=a.module(0,'kernel')
    m.label('start').raw(0x2F,0x50,0x2F,0x2A).set(9,0).set('A',0)
    show_text(m,'title');m.op('cx','stop')
    m.label('new_game').visit(24,'init_pilot').visit(25,'init_hold')
    m.n(0).call('world').put(24,2).call('arrive')
    m.label('redraw').call('show').op('cx','stop')
    m.label('main').st(0).op('int').ld(0).op('-').jnz('input_invalid')
    m.ld(0).jneg('input_invalid').ld(9).n(4).op('-').jz('new_game')
    m.ld(9).n(3).op('-').jnz('not_result').call('arrive').jump('redraw')
    m.label('not_result').ld(9).n(2).op('-').jz('combat_input_entry')
    m.call('port_input').jump('redraw')
    m.label('combat_input_entry').call('combat_input').jump('redraw')
    m.label('input_invalid').call('bad_action').jump('redraw')
    m.label('bad_action').set('A',99).op('ret')

    m=a.module(12,'input')
    m.label('port_input').ld(0).n(10).op('-').jneg('set_view')
    m.ld(0).n(70).op('-').jge('select_check')
    m.ld(0).n(60).op('-').jz('jump')
    m.ld(0).n(50).op('-').jge('station_check')
    m.ld(0).call('mod10').st(1).n(6).op('-').jge('bad_action')
    m.ld(0).n(10).op('/','int').st(8).n(3).op('-').jneg('set_view')
    m.n(7).ld(8).n(2).op('*','-').st(7).jump('trade')
    m.label('station_check').ld(0).n(54).op('-').jge('bad_action').jump('station')
    m.label('select_check').ld(0).n(326).op('-').jge('bad_action').jump('select_world')
    m.label('set_view').ld(0).st('A').op('ret')

    m=a.module(17,'views')
    m.label('show').ld('A').n(99).op('-').jz('show_invalid').jge('show_result')
    m.ld(9).n(2).op('-').jnz('port_view')
    m.ld('A').jz('combat_view').n(9).op('-').jge('combat_view')
    m.label('port_view').ld('A').n(9).op('-').jz('distance_view')
    m.ld('A').jz('show_world').ld('A').n(8).op('-').jz('show_destination')
    m.ld('A').n(10).op('-').jneg('show_stat')
    m.ld('A').n(20).op('-').jneg('show_price')
    m.ld('A').n(20).op('-').st(1);dynamic_get(m,25,1)
    m.jump('good_prefix')
    m.label('show_price').ld('A').n(10).op('-').st(1).call('price').st('C')
    m.label('good_prefix').ld(1).n(1).op('+').call('glyph').st('D').jump('draw_number')
    m.label('show_stat').ld('A').n(7).op('-').jz('show_hold')
    m.ld('A').n(6).op('-').jz('show_missiles')
    m.ld('A').n(2).op('+').st('B').ld('A').n(1).op('-').jnz('stat_get').set('B',0)
    m.label('stat_get').far(0x53,24*112+63).jump('stat_prefix')
    m.label('show_missiles').get(25,7)
    m.label('stat_prefix').ptr('E','stat_masks').ld('A').n(1).op('-').n(4).op('*').ld('E').op('+').st('E').raw(0x1F,0xAE).st('D').jump('draw_number')
    m.label('show_hold').visit(25,'sum_hold').set('D',GLYPHS['U']).jump('draw_number')
    m.label('show_world').get(24,1).jump('draw_name')
    m.label('show_destination').get(24,2)
    m.label('draw_name');show_name(m);m.op('ret')
    m.label('draw_number').visit(29,'number_frame').visit(29,'display').op('ret')
    m.label('show_invalid');show_text(m,'invalid');m.op('ret')
    m.label('stat_masks')
    m.raw(*(v for ch in 'CHSFtr' for v in [*(int(d) for d in f'{GLYPHS[ch]:03d}'),0x52]))
    add_ui(a)
    add_economy(a)
    add_combat(a)
    return a
