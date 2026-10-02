"""Turn combat, emitted as calculator instructions; no host game logic."""
from assembler import GLYPHS
from ui import show_text
from economy import dynamic_get

def add_combat(a):
    m=a.module(13,'combat')
    # Closed recalls/conditions supply automatic lift for these literals;
    # parsing exports R1/R2, not the lower stack. Keep the X2 extractor.
    m.label('combat_input').ld(0).raw(1,0).op('-').jneg('set_view')
    m.raw(7,0).op('-').jge('choose_target')
    m.raw(6,4).op('+').jneg('fight_command')
    m.raw(4).op('-').jneg('set_view')
    m.label('fight_command').ld(0).st(2).raw(0x0C).st(2).jz('bad_action')
    m.raw(5).op('-').jge('bad_action')
    # Keep the valid bound delta m-5; adjustment waits for the turn guards.
    m.ld(0).ld(2).op('-').raw(1,0).op('/').raw(5).op('-').jge('bad_action').st(1).jump('fight')
    m.label('choose_target').raw(6).op('-').jge('bad_action')
    # X1 retains 6 from the bound check; Lx undoes that subtraction.
    m.raw(0x0F).op('+').st('C').visit(27,'select_target').jz('bad_action').st(8)
    m.ld('C').st(1).st(5)
    m.call('glyph').n(65).op('+').st(7).set('A',16).op('ret')

    # Outside page callbacks: R1 maneuver-5, R2 action; ammo_ready exports maneuver-4.
    # Between commands R5/R6/R7/R8 cache target / live drones / target glyph
    # delta / selected hull; queries preserve them. The pre-hit drone count
    # is used for simultaneous fire. The glyph changes only on selection.
    # Validate before consuming ammunition, advancing enemies or cooling.
    # Shield and escape remain available after the selected target is dead.
    # Recalls close entry; the following digits lift X into Y automatically.
    # Keep explicit ENTER where X1/X2 or another stack operand is live.
    m.label('fight').ld(2).raw(3).op('-').jge('ammo_ready')
    m.ld(8).jz('bad_action')
    m.ld(2).raw(2).op('-').jnz('ammo_ready')
    # Check and consume in one HOLD opening. Keep the old count in RC so
    # an empty magazine returns to the dispatcher only after closing it.
    m.open_page(25).ld(7).st('C').jz('missile_empty').n(1).op('-').st(7)
    m.label('missile_empty').close_page(25).ld('C').jz('bad_action')
    # Keep COMBAT open across the whole simultaneous turn. PILOT and
    # DRONES temporarily exchange the live COMBAT registers via nested Ms.
    # Only a validated turn adjusts the parser's m-5 to COMBAT's m-4.
    m.label('ammo_ready').ld(1).raw(1).op('+').st('D').ld(2).st('C').ld(6).raw(3).op('*').st('E')
    m.open_page(27).call('enemy_tick')
    # enemy_tick returns action RC, laser RD, incoming RE, launch RF.
    m.visit(24,'weapon')
    # PILOT exports shot RC, launch RE and hull RF for the next page.
    # No caller-side shuffle is needed before nesting DRONES.
    m.ld(4).jnz('shot_ready').ld('C').raw(2).op('/','int').st('C')
    m.label('shot_ready').ld(5).st('D').visit(28,'drone_tick')
    # DRONES leaves shot RC, live count RD, selected hull RE, player hull RF.
    # COMBAT stays loaded here, so apply the carrier hit directly.
    m.label('apply_damage').ld(5).jnz('enemy_hit_done').ld(1).ld('C').op('-').max0().st(1).st('E')
    m.label('enemy_hit_done').ld(1).ld('D').op('+').st('C').ld(6).st('B')
    m.close_page(27).ld('D').st(6).ld('E').st(8)
    m.ld('F').jz('lost')
    m.ld('C').jz('won')
    m.ld('B').raw(4).op('-').jge('escaped').set('A',16).op('ret')
    m.label('won').visit(24,'reward').visit(25,'count_kill').ptr(9,'result_input_entry',lift=False).ptr('A','victory',lift=False).op('ret')
    m.label('escaped').ptr(9,'result_input_entry',lift=False).ptr('A','escape',lift=False).op('ret')
    m.label('lost').ptr(9,'new_game',lift=False).ptr('A','defeat',lift=False).op('ret')

    m=a.module(14,'weapons')
    # PILOT callback: action RC, laser damage RD, incoming RE, launch RF
    # -> outgoing shot RC, launch RE, player hull RF. Shield precedes the hit.
    # Each arm first sets RD; after applying incoming RE, export the results.
    # Shield saturation uses a clipped delta; reward reuses 99999999 in X1.
    m.page(24,'weapon',inline=False).ld(7).raw(1,0).op('-').max0().st(7)
    m.ld('C').raw(1).op('-').jz('laser')
    # X1 retains the subtracted unit across both conditional branches.
    m.raw(0x0F).op('-').jz('missile')
    m.raw(0x0F).op('-').jnz('no_shot')
    # min(60, shield+18) = 60+min(0, shield-42); write once.
    m.ld(5).raw(4,2).op('-').jneg('shield_under_cap').op('cx')
    # Keep ENTER before 60: the Cx path leaves entry open.
    m.label('shield_under_cap').n(60).op('+').st(5)
    m.label('no_shot').set('D',0).jump('weapon_done')
    # The bound test leaves cooled heat-70 in X and closes number entry.
    # Adding 98 gives cooled heat+28 without recalling the heat register.
    m.label('laser').ld(7).raw(7,0).op('-').jge('no_shot').raw(9,8).op('+').st(7).jump('weapon_done')
    m.label('missile').add(7,10).set('D',45)
    m.label('weapon_done')
    m.label('player_hit').ld(5).ld('E').op('-').st(5).jge('shield_holds')
    m.ld(4).op('+').max0().st(4).set(5,0)
    m.label('shield_holds').add(3,1).ld('F').st('E').ld('D').st('C').ld(4).st('F').op('ret')
    m.end_page().page(24,'reward').add(0,250).n(99999999).op('-').jneg('reward_done').raw(0x0F).st(0)
    m.label('reward_done').op('ret')
    m.end_page().page(25,'count_kill').add(8,1).op('ret')

    m.end_page()

    m=a.module(15,'enemies')
    # Called with COMBAT already open: action RC, maneuver-4 RD,
    # pre-hit drone attack RE -> action RC, laser RD, incoming RE, launch RF.
    # R4 holds maneuver-4 after a turn: zero selects evasive half-damage.
    # The initial zero remains a pre-turn sentinel. n(2) keeps its ENTER;
    # the following Lx reads the 2 produced by that addition.
    m.label('enemy_tick').ld('D').st(4).jz('motion_ready')
    m.n(2).op('+').jz('motion_ready').raw(0x0F).op('*').ld(2).op('+').max0().st(2)
    m.n(99).ld(2).op('-').jge('motion_ready').set(2,99)
    m.label('motion_ready').ld('C').raw(4).op('-').jnz('charge_reset')
    m.add(6,1).jump('charge_ready')
    m.label('charge_reset').set(6,0)
    m.label('charge_ready').set('F',0).ld(1).jz('enemy_ready')
    m.ld(7).ld('E').op('+').st('E')
    m.ld(0).raw(4).op('-').jnz('enemy_ready')
    m.branch(0x5A,'enemy_ready').set(3,3).set('F',1)
    m.label('enemy_ready').ld(8).ld(2).op('-').st('D')
    m.ld(2).raw(1,9).op('-').jneg('incoming_ready').set('E',0).st('D')
    m.label('incoming_ready').ld(4).jnz('weapon_ready')
    m.ld('E').raw(2).op('/','int').st('E')
    m.label('weapon_ready').op('ret')
    # DRONES callback: shot RC, target RD, launch RE. R0..4 are hulls;
    # the formation shares the carrier's range. R5 last launched index,
    # R6 alive. K STO 5 increments R5 before writing the next drone's hull.
    m.page(28,'drone_tick').ld('E').jz('drones_hit').ld(5).raw(4).op('-').jge('drones_hit')
    m.n(18).raw(0xB5).add(6,1)
    m.label('drones_hit').ld('D').jz('drones_ready')
    m.n(1).op('-').st('B').raw(0xDB).st('E').jz('drones_ready')
    m.ld('C').op('-').max0().raw(0xBB).st('E').jnz('drones_ready').add(6,-1)
    m.label('drones_ready').ld(6).st('D').op('ret')

    m.end_page()

    m=a.module(16,'combat views')
    # As in port_view, each condition closes entry before the next literal.
    m.label('combat_view').ld('A').jz('contact_name')
    m.raw(9).op('-').jz('range_view')
    m.raw(7).op('-').jz('target_view')
    m.raw(1).op('-').jz('drones_view')
    m.raw(1).op('-').jz('charge_view').jump('target_number')
    m.label('range_view').get(27,2).jump('draw_range')
    m.label('target_view').ld(8).st('C').ld(7).st('D').ld(6).st('B').visit(29,'battle_frame').op('ret')
    m.label('drones_view').ld(6).st('C').set('D',GLYPHS['d']).jump('draw_number')
    m.label('charge_view').get(27,6).set('D',GLYPHS['P']).jump('draw_number')
    m.label('target_number').ld(5).st('C').set('D',GLYPHS['t']).jump('draw_number')
    m.label('contact_name').get(27,0).raw(4).op('-').jz('alien_name')
    show_text(m,'pirate');m.op('ret')
    m.label('alien_name');show_text(m,'thargoid');m.op('ret')
    m.label('show_result').ld('A').st('F').jump('show_message')
    # RC target -> X/RD hull. COMBAT remains open from the hull check to
    # the target write; a drone read temporarily nests DRONES. Rejecting a
    # dead target changes no page or cache. Both read paths already leave
    # the hull in X, and the outer close preserves it for the caller.
    m.page(27,'select_target').ld('C').jz('select_carrier')
    m.raw(1).op('-').st('B').page_bytes(28,0xDB,0x4D).jump('select_hp')
    m.label('select_carrier').ld(1).st('D')
    # This existing far condition avoids a slower native branch on refusals.
    m.label('select_hp').jz('select_done',far=True).ld('C').st(5).ld('D')
    m.label('select_done').op('ret').end_page()
