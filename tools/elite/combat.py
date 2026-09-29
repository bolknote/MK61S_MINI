"""Turn combat, emitted as calculator instructions; no host game logic."""
from assembler import GLYPHS
from ui import show_text
from economy import dynamic_get

def add_combat(a):
    m=a.module(13,'combat')
    m.label('combat_input').ld(0).n(10).op('-').jneg('set_view')
    m.n(70).op('-').jge('choose_target')
    m.n(64).op('+').jneg('fight_command')
    m.n(4).op('-').jneg('set_view')
    m.label('fight_command').ld(0).st(2).raw(0x0C).st(2).jz('bad_action')
    m.n(5).op('-').jge('bad_action')
    m.ld(0).ld(2).op('-').n(10).op('/').st(1).n(5).op('-').jge('bad_action').jump('fight')
    m.label('choose_target').n(6).op('-').jge('bad_action')
    # X1 retains 6 from the bound check; Lx undoes that subtraction.
    m.raw(0x0F).op('+').st(1).call('target_hp').jz('bad_action').st(8)
    m.label('store_target').ld(1).st(5).put(27,5)
    m.ld(1).call('glyph').n(65).op('+').st(7).set('A',16).op('ret')

    # Outside page callbacks: R1 maneuver, R2 action.
    # Between commands R5/R6/R7/R8 cache target / live drones / target glyph
    # delta / selected hull; queries preserve them. The pre-hit drone count
    # is used for simultaneous fire. The glyph changes only on selection.
    # Validate before consuming ammunition, advancing enemies or cooling.
    # Shield and escape remain available after the selected target is dead.
    m.label('fight').ld(2).n(3).op('-').jge('ammo_ready')
    m.ld(8).jz('bad_action')
    m.ld(2).n(2).op('-').jnz('ammo_ready')
    # Check and consume in one HOLD opening. Keep the old count in RC so
    # an empty magazine returns to the dispatcher only after closing it.
    m.open_page(25).ld(7).st('C').jz('missile_empty').n(1).op('-').st(7)
    m.label('missile_empty').close_page(25).ld('C').jz('bad_action')
    # Keep COMBAT open across the whole simultaneous turn. PILOT and
    # DRONES temporarily exchange the live COMBAT registers via nested Ms.
    m.label('ammo_ready').ld(1).st('D').ld(2).st('C').ld(6).n(3).op('*').st('E')
    m.open_page(27).call('enemy_tick')
    # enemy_tick returns action RC, laser RD, incoming RE, launch RF.
    m.visit(24,'weapon')
    # PILOT returns hull RC and shot RD. Keep the hull outside R0..8
    # while DRONES is nested; move launch RF into its RE input first.
    m.ld('F').st('E').ld('C').st('F').ld('D').st('C')
    m.ld(4).n(4).op('-').jnz('shot_ready').ld('C').n(2).op('/','int').st('C')
    m.label('shot_ready').ld(5).st('D').visit(28,'drone_tick')
    # DRONES leaves shot RC, live count RD, selected hull RE, player hull RF.
    # COMBAT stays loaded here, so apply the carrier hit directly.
    m.label('apply_damage').ld(5).jnz('enemy_hit_done').ld(1).ld('C').op('-').max0().st(1).st('E')
    m.label('enemy_hit_done').ld(1).ld('D').op('+').st('C').ld(6).st('B')
    m.close_page(27).ld('D').st(6).ld('E').st(8)
    m.ld('F').jz('lost')
    m.ld('C').jz('won')
    m.ld('B').n(4).op('-').jge('escaped').set('A',16).op('ret')
    m.label('won').visit(24,'reward').visit(25,'count_kill').ptr(9,'result_input_entry',lift=False).ptr('A','victory',lift=False).op('ret')
    m.label('escaped').ptr(9,'result_input_entry',lift=False).ptr('A','escape',lift=False).op('ret')
    m.label('lost').ptr(9,'new_game',lift=False).ptr('A','defeat',lift=False).op('ret')

    m=a.module(14,'weapons')
    # PILOT callback: action RC, laser damage RD, incoming RE
    # -> player hull RC, outgoing shot RD. Shield boost precedes the hit.
    # Assign the final outgoing RD in each arm and read incoming RE directly.
    # Saturation reuses the comparison's bound in X1 (60 / 99999999).
    m.page(24,'weapon',inline=False).ld(7).n(10).op('-').max0().st(7)
    m.ld('C').n(1).op('-').jz('laser')
    # X1 retains the subtracted unit across both conditional branches.
    m.raw(0x0F).op('-').jz('missile')
    m.raw(0x0F).op('-').jnz('no_shot')
    m.add(5,18).n(60).op('-').jneg('no_shot').raw(0x0F).st(5)
    m.label('no_shot').set('D',0).jump('weapon_done')
    m.label('laser').ld(7).n(70).op('-').jge('no_shot').add(7,28).jump('weapon_done')
    m.label('missile').add(7,10).set('D',45)
    m.label('weapon_done')
    m.label('player_hit').ld(5).ld('E').op('-').st(5).jge('shield_holds')
    m.ld(4).op('+').max0().st(4).set(5,0)
    m.label('shield_holds').add(3,1).ld(4).st('C').op('ret')
    m.end_page().page(24,'reward').add(0,250).n(99999999).op('-').jneg('reward_done').raw(0x0F).st(0)
    m.label('reward_done').op('ret')
    m.end_page().page(25,'count_kill').add(8,1).op('ret')

    m.end_page()

    m=a.module(15,'enemies')
    # Called with COMBAT already open: action RC, maneuver RD,
    # pre-hit drone attack RE -> action RC, laser RD, incoming RE, launch RF.
    m.label('enemy_tick').ld('D').st(4).n(4).op('-').jz('motion_ready')
    m.n(2).op('+').jz('motion_ready').raw(0x0F).op('*').ld(2).op('+').max0().st(2)
    m.n(99).ld(2).op('-').jge('motion_ready').set(2,99)
    m.label('motion_ready').ld('C').n(4).op('-').jnz('charge_reset')
    m.add(6,1).jump('charge_ready')
    m.label('charge_reset').set(6,0)
    m.label('charge_ready').set('F',0).ld(1).jz('enemy_ready')
    m.ld(7).ld('E').op('+').st('E')
    m.ld(0).n(4).op('-').jnz('enemy_ready')
    m.branch(0x5A,'enemy_ready').set(3,3).set('F',1)
    m.label('enemy_ready').ld(8).ld(2).op('-').st('D')
    m.ld(2).n(19).op('-').jneg('incoming_ready').set('E',0).st('D')
    m.label('incoming_ready').ld(4).n(4).op('-').jnz('weapon_ready')
    m.ld('E').n(2).op('/','int').st('E')
    m.label('weapon_ready').op('ret')
    # DRONES callback: shot RC, target RD, launch RE. R0..4 are hulls;
    # the formation shares the carrier's range. R5 last launched index,
    # R6 alive. K STO 5 increments R5 before writing the next drone's hull.
    m.page(28,'drone_tick').ld('E').jz('drones_hit').ld(5).n(4).op('-').jge('drones_hit')
    m.n(18).raw(0xB5).add(6,1)
    m.label('drones_hit').ld('D').jz('drones_ready')
    m.n(1).op('-').st('B').raw(0xDB).st('E').jz('drones_ready')
    m.ld('C').op('-').max0().raw(0xBB).st('E').jnz('drones_ready').add(6,-1)
    m.label('drones_ready').ld(6).st('D').op('ret')

    m.end_page()

    m.label('carrier_hp').get(27,1).op('ret')

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
    m.label('target_number').ld(5).st('C').set('D',GLYPHS['t']).jump('draw_number')
    m.label('contact_name').get(27,0).n(4).op('-').jz('alien_name')
    show_text(m,'pirate');m.op('ret')
    m.label('alien_name');show_text(m,'thargoid');m.op('ret')
    m.label('show_result').ld('A').st('F').jump('show_message')
    # X target index -> X/RC hull. R0..8 are preserved for command parsing.
    m.label('target_hp').jz('carrier_hp')
    m.n(1).op('-').st('B').page_bytes(28,0xDB,0x4C).op('ret')
