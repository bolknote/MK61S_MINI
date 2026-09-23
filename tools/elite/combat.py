"""Turn combat, emitted as calculator instructions; no host game logic."""
from assembler import GLYPHS
from ui import show_text
from economy import dynamic_get

def add_combat(a):
    m=a.module(13,'combat')
    m.label('combat_input').ld(0).n(10).op('-').jneg('set_view')
    m.ld(0).n(80).op('-').jge('choose_target')
    m.ld(0).n(16).op('-').jneg('fight_command')
    m.ld(0).n(20).op('-').jneg('set_view')
    m.label('fight_command').ld(0).n(10).op('/','int').st(1)
    m.ld(1).n(5).op('-').jge('bad_action')
    m.ld(0).call('mod10').st(2).jz('bad_action')
    m.ld(2).n(5).op('-').jge('bad_action').jump('fight')
    m.label('choose_target').ld(0).n(86).op('-').jge('bad_action')
    m.ld(0).n(80).op('-').st(1).call('target_hp').jz('bad_action').st(8)
    m.label('store_target').ld(1).st(5).put(27,5)
    m.ld(1).call('glyph').n(65).op('+').st(7).set('A',16).op('ret')

    # Outside page callbacks: R1 maneuver, R2 action, R3 outgoing damage,
    # R4 incoming damage, R5 target, R6 surviving drones.
    # Between commands R5/R6/R7/R8 cache target / live drones / target glyph
    # delta / selected hull; queries preserve them. The pre-hit drone count
    # is used for simultaneous fire. The glyph changes only on selection.
    # During a turn R8 temporarily carries the enemy's launch flag.
    # Validate before consuming ammunition, advancing enemies or cooling.
    # Shield and escape remain available after the selected target is dead.
    m.label('fight').ld(2).n(3).op('-').jge('ammo_ready')
    m.ld(8).jz('bad_action')
    m.ld(2).n(2).op('-').jnz('ammo_ready')
    m.get(25,7).jz('bad_action').n(1).op('-').put(25,7)
    m.label('ammo_ready').ld(1).st('C').ld(2).st('D').visit(27,'enemy_tick')
    # RD/RE already carry range/attack until the PILOT callback. Avoid copies.
    m.ld('C').st(5).ld('F').st(8)
    m.ld(6).n(3).op('*').ld('E').op('+').st(4)
    m.ld('D').n(19).op('-').jneg('incoming_ready').set(4,0).set('B',0)
    m.label('incoming_ready').ld(1).n(4).op('-').jnz('weapon_ready')
    m.ld(4).n(2).op('/','int').st(4)
    # One PILOT opening resolves weapon/heat/shield and incoming damage.
    # Apply enemy casualties afterwards, including on mutual destruction.
    m.label('weapon_ready').ld('B').st('D').ld(4).st('E').ld(2).st('C').visit(24,'weapon')
    m.ld('C').st(0).ld('D').st(3)
    m.ld(1).n(4).op('-').jnz('shot_ready').ld(3).n(2).op('/','int').st(3)
    m.label('shot_ready').ld(3).st('C').ld(5).st('D').ld(8).st('E').visit(28,'drone_tick')
    m.ld('D').st(6)
    m.label('apply_damage').ld(3).st('C').visit(27,'enemy_hit').ld('C').st(8)
    m.ld(0).jz('lost')
    # enemy_hit already returned carrier hull and escape charge.
    m.ld('D').ld(6).op('+').jz('won')
    m.ld('E').n(4).op('-').jge('escaped').set('A',16).op('ret')
    m.label('won').visit(24,'reward').visit(25,'count_kill').set(9,3).ptr('A','victory').op('ret')
    m.label('escaped').set(9,3).ptr('A','escape').op('ret')
    m.label('lost').set(9,4).ptr('A','defeat').op('ret')

    m=a.module(14,'weapons')
    # PILOT callback: action RC, laser damage RD, incoming RE
    # -> player hull RC, outgoing shot RD. Shield boost precedes the hit.
    m.label('weapon').ld(7).n(10).op('-').call('max0').st(7)
    m.ld('C').n(1).op('-').jz('laser')
    m.n(1).op('-').jz('missile')
    m.n(1).op('-').jnz('no_shot')
    m.add(5,18).n(60).op('-').jneg('no_shot').set(5,60)
    m.label('no_shot').set('C',0).jump('weapon_done')
    m.label('laser').ld(7).n(70).op('-').jge('no_shot').add(7,28).ld('D').st('C').jump('weapon_done')
    m.label('missile').add(7,10).set('C',45)
    m.label('weapon_done').ld('C').st('D').ld('E').st('C')
    m.label('player_hit').ld(5).ld('C').op('-').st(5).jge('shield_holds')
    m.ld(4).ld(5).op('+').call('max0').st(4).set(5,0)
    m.label('shield_holds').add(3,1).ld(4).st('C').op('ret')
    m.label('max0').jge('positive').n(0)
    m.label('positive').op('ret')
    m.label('reward').add(0,250).n(99999999).op('-').jneg('reward_done').set(0,99999999)
    m.label('reward_done').op('ret')
    m.label('count_kill').add(8,1).op('ret')

    m=a.module(15,'enemies')
    # COMBAT callback: maneuver RC, action RD. Return target RC, range RD,
    # carrier's pre-hit attack RE, launch flag RF, laser damage RB.
    # All shots are simultaneous.
    m.label('enemy_tick').ld('C').st(3).n(4).op('-').jz('motion_ready')
    m.ld('C').n(2).op('-').jz('motion_ready').n(2).op('*').ld(2).op('+').call('max0').st(2)
    m.n(99).ld(2).op('-').jge('motion_ready').set(2,99)
    m.label('motion_ready').ld('D').n(4).op('-').jnz('charge_reset')
    m.add(6,1).jump('charge_ready')
    m.label('charge_reset').set(6,0)
    m.label('charge_ready').set('E',0).set('F',0).ld(1).jz('enemy_ready')
    m.ld(7).st('E') # fixed carrier attack, prepared at contact
    # R4 counts 3,2,1 until a live carrier launches; no general remainder.
    m.ld(0).n(4).op('-').jnz('enemy_ready')
    m.ld(4).n(1).op('-').st(4).jnz('enemy_ready').set(4,3).set('F',1)
    m.label('enemy_ready').ld(8).ld(2).op('-').st('B').ld(5).st('C').ld(2).st('D').op('ret')
    # RE arrives from drone_tick with the selected drone's remaining hull.
    # Return selected hull RC, carrier hull RD, escape charge RE.
    m.label('enemy_hit').ld(5).jnz('enemy_hit_done').ld(1).ld('C').op('-').call('max0').st(1).st('E')
    m.label('enemy_hit_done').ld('E').st('C').ld(1).st('D').ld(6).st('E').op('ret')
    # DRONES callback: shot RC, target RD, launch RE. R0..4 are hulls;
    # the formation shares the carrier's range. R5 total launched, R6 alive.
    m.label('drone_tick').ld('E').jz('drones_hit').ld(5).n(5).op('-').jge('drones_hit')
    m.ld(5).st('B').n(18).raw(0xBB).add(5,1).add(6,1)
    m.label('drones_hit').ld('D').jz('drones_ready')
    m.n(1).op('-').st('B').raw(0xDB).st('E').jz('drones_ready')
    m.ld('C').op('-').call('max0').raw(0xBB).st('E').jnz('drones_ready').add(6,-1)
    m.label('drones_ready').ld(6).st('D').op('ret')

    m=a.module(16,'combat views')
    m.label('combat_view').ld('A').jz('contact_name')
    m.n(9).op('-').jz('range_view')
    m.n(7).op('-').jz('target_view')
    m.n(1).op('-').jz('drones_view')
    m.n(1).op('-').jz('charge_view').jump('target_number')
    m.label('range_view').get(27,2).jump('draw_range')
    m.label('target_view').ld(8).st('C').ld(7).st('D').ld(6).st('B').visit(29,'battle_frame').op('ret')
    m.label('drones_view').ld(6).st('C').set('D',GLYPHS['d']).jump('draw_number')
    m.label('charge_view').get(27,6).set('D',GLYPHS['P']).jump('draw_number')
    m.label('target_number').get(27,5).set('D',GLYPHS['t']).jump('draw_number')
    m.label('contact_name').get(27,0).n(4).op('-').jz('alien_name')
    show_text(m,'pirate');m.op('ret')
    m.label('alien_name');show_text(m,'thargoid');m.op('ret')
    m.label('show_result').ld('A').st('F').jump('show_message')
    # X target index -> X/RC hull. R0..8 are preserved for command parsing.
    m.label('target_hp').jz('carrier_hp')
    m.n(1).op('-').st('B').far(0x53,28*112+63).op('ret')
    m.label('carrier_hp').get(27,1).op('ret')
