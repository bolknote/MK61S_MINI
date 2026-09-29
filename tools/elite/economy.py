from assembler import GLYPHS, READ, WRITE
from ui import show_name, show_number, show_text

def dynamic_get(m,bank,index):
    m.ld(index).st('B').far(0x53,bank*112+63)

def dynamic_put(m,bank,index):
    m.st('C').ld(index).st('B').far(0x53,bank*112+WRITE)

def add_economy(a):
    m=a.module(1,'initialization')
    m.page(24,'init_pilot',inline=False)
    # World 0 is 12345*256. Build the already-landed starting ship once;
    # init_hold preserves RC, and finish_arrive consumes it as the world.
    m.op('cx').st(3).st(7)
    m.set(1,3160320).st(2).st('C')
    for i in (0,4,5,6,8):m.set(i,60 if i==5 else a.data[24][i])
    m.op('ret').end_page().page(25,'init_hold',inline=False)
    m.op('cx')
    for i in (0,1,2,3,4,5,8):m.st(i)
    m.set(6,a.data[25][6]).set(7,3).op('ret')
    m.end_page().label('sum_hold').ld(0)
    for i in range(1,6):m.ld(i).op('+')
    m.st('C').op('ret')
    # Purchase callback: money and market stock were checked by the caller.
    # RB good -> RC old free capacity. Only a positive capacity commits the
    # item here; this avoids opening HOLD a second time after paying.
    m.page(25,'trade_hold').raw(0xDB).st('D').call('sum_hold')
    m.ld(6).n(100).op('/','frac').n(100).op('*').ld('C').op('-').st('C').jneg('buy_done').jz('buy_done')
    m.ld('D').n(1).op('+').raw(0xBB)
    m.label('buy_done').op('ret')

    m.end_page()

    m=a.module(5,'world')
    # For i in 0..255 the packed world is (64257*i+3160320) mod 2**24.
    # Subtract the modulus in the constant term; one add repairs negatives.
    # All intermediates fit eight digits. Keep the same names and economies.
    m.label('world').n(64257).op('*').n(13616896).op('-').jge('world_ready').n(16777216).op('+')
    m.label('world_ready').op('ret')
    m.label('select_world').ld(0).n(70).op('-').call('world').put(24,2).set('A',8).op('ret')
    # Decode the world's economy once on arrival. MARKET R0/R1 are reserved;
    # the former world/time copies have no readers and need no writes.
    m.page(26,'init_market').ld('C').n(1048576).op('/','int').st(2).n(30)
    for i in range(3,9):m.st(i)
    m.op('ret')
    m.end_page().page(24,'arrived_pilot').ld(2).st(1).st('C').set(5,60).set(7,0).op('ret')

    m.end_page()

    m=a.module(6,'prices')
    # A single open market page supplies both economy and stock. RD retains
    # the unclamped quote; R2 carries it back to a trade for its next display.
    m.label('price').ld(1).st('B').visit(26,'price_market').ld('D').st(2).ld('C').op('ret')
    # economy + 2*good is in 0..25: one subtraction replaces general mod 16.
    m.page(26,'price_market').ld('B').n(2).op('*').ld(2).op('+').n(16).op('-').jge('price_wrapped')
    m.raw(0x0F).op('+')
    m.label('price_wrapped').raw(0x0F).op('+')
    # Consecutive factors give an even product. This is exactly the original
    # floor((g+1)*(g+2)*10*(80+5*e)/100), with smaller integer intermediates.
    # Keep 16+e below the triangular factor in the stack; no RD spill/reload.
    m.ld('B').n(1).op('+','square').raw(0x0F).op('+').n(2).op('/','*').st('D')
    m.ld('B').raw(0x20).op('+').st('B').n(30).raw(0xDB).st('E')
    # Quotes are integers: positive means >=1, without materializing and
    # subtracting one. Keep the unclamped RD for the post-trade quote.
    m.op('-').n(2).op('*').ld('D').op('+').st('D').st('C').jneg('price_clamp').jnz('price_ready')
    m.label('price_clamp').set('C',1).label('price_ready').op('ret')

    m.end_page()

    m=a.module(7,'trade')
    m.label('trade').call('price').ld('E').st(6).ld(7).jge('trade_quote')
    # Four-credit spread prevents profit from an immediate reverse trade.
    m.ld('C').n(4).op('-').max0().st('C')
    # Keep PILOT open across the HOLD check/update; only commit credits
    # after every guard passed. Working R1/R2/R6/R7 return on close.
    m.label('trade_quote').ld(1).st('B').ld(7).open_page(24).jneg('sell_checks')
    m.ld(0).ld('C').op('-').st('F').jneg('trade_refused').ld('E').jz('trade_refused')
    m.visit(25,'trade_hold').ld('C').jz('trade_refused').jneg('trade_refused').jump('trade_commit')
    m.label('sell_checks').ld(0).st('F').open_page(25).raw(0xDB).st('D').jz('sell_empty')
    m.ld('E').n(99).op('-').jge('sell_empty')
    # Keep the exact eight-digit bound: comparison to 1e8 rounds near-cap
    # balances on the ROM and would reject valid sales.
    m.n(99999999).ld('C').op('-').ld('F').op('-').jneg('sell_empty')
    m.ld('D').n(1).op('-').raw(0xBB).close_page(25)
    m.ld('F').ld('C').op('+').st('F')
    m.label('trade_commit').ld('F').st(0).add(3,1).close_page(24)
    m.ld(6).ld(7).op('-').st('C').ld(1).raw(0x20).op('+').st('B').page_bytes(26,0x6C,0xBB)
    # Update the unclamped quote: max(1, raw)+2 is wrong at high stocks.
    m.ld(2).ld(7).n(2).op('*','+').st('C').jneg('trade_price_clamp').jnz('trade_price_ready')
    m.label('trade_price_clamp').set('C',1)
    m.label('trade_price_ready').ld(1).n(30).op('+').st('A').op('ret')
    m.label('sell_empty').close_page(25)
    m.label('trade_refused').close_page(24).jump('bad_action')

    m=a.module(19,'station')
    # RB field, RC cost then remaining credits, RD increment, RE cap.
    # RF selects PILOT (<0) or HOLD (>=0); registers B..F survive both
    # exchanges. PILOT stays open until the entire transaction is done.
    m.label('station').set('C',5).set('B',6).set('D',1).set('E',99)
    m.ld(0).n(51).op('-').st('F').jneg('service_ready').jz('service_hull')
    m.n(1).op('-').jz('service_missile')
    m.set('C',300).raw(1,0x0C,6).st('D').set('E',3010420).jump('service_ready')
    m.label('service_hull').set('C',20).set('B',4).set('D',10).set('F',-1).jump('service_ready')
    m.label('service_missile').set('C',60).set('B',7).set('E',9)
    m.label('service_ready').open_page(24).ld(0).ld('C').op('-').st('C').jneg('service_done')
    m.ld('F').jge('service_hold').call('service_check').jneg('service_done').jump('service_commit')
    # HOLD nests inside PILOT. Full fields and insufficient money leave
    # both pages unchanged; successful writes are followed by one debit
    # and one time increment before closing PILOT.
    m.label('service_hold').open_page(25).call('service_check').close_page(25).jneg('service_done')
    m.label('service_commit').ld('C').st(0).add(3,1)
    m.label('service_done').close_page(24).jneg('bad_action').set('A',1).op('ret')
    # Keep old-cap in X: min(0, old-cap+increment)+cap is the saturated
    # result. No temporary result or restoration of old is needed.
    m.label('service_check').raw(0xDB).ld('E').op('-').jge('service_full')
    m.ld('D').op('+').jneg('service_checked').op('cx')
    m.label('service_checked').ld('E').op('+').raw(0xBB).op('cx','ret')
    m.label('service_full').raw(1,0x0B).op('ret')

    m=a.module(9,'navigation')
    # Read both worlds during one PILOT opening. Only RC/RD/RE and the
    # stack are scratch; none of the exposed pilot fields may be changed.
    m.label('distance').open_page(24).ld(2).call('mod256').st('D').ld(1).call('mod256').st('E')
    # Keep the low-byte difference below both coordinate quotients; their
    # subtraction leaves it in Y, avoiding another load of the row delta.
    m.ld('D').ld('E').op('-').ld('D').n(16).op('/','int').ld('E').n(16).op('/','int','-').st('C')
    m.n(16).op('*','-','abs').ld('C').op('abs','+').st('C')
    # Ms exchanges preserve X, already equal to RC.
    m.close_page(24).st(2).op('ret')
    m.label('distance_view').call('distance').set('D',GLYPHS['r']).jump('draw_number')

    m=a.module(10,'flight')
    m.label('jump').call('distance').jz('bad_action')
    m.get(25,6).n(100).op('/','int').n(100).op('/','frac').n(100).op('*').ld(2).op('-').jneg('bad_action')
    m.ld(2).st('C').visit(24,'jump_tick').ld('D').jneg('bad_action').ld('C').jz('alien_contact')
    m.st(3).ld('E').n(65536).op('/','int').call('mod16').n(4).op('/','int').n(2).op('+')
    m.ld(3).op('swap','-').jneg('pirate_contact').jump('arrive')
    m.label('alien_contact').n(4).jump('start_contact')
    m.label('pirate_contact').n(2).jump('start_contact')
    # Keeping this entry whole avoids a bridge after victory or escape.
    m.label('arrive',keep_block=True).visit(24,'arrived_pilot').label('finish_arrive').visit(26,'init_market').ptr(9,'port_input_entry',lift=False).set('A',0).op('ret')
    # RC distance -> RD fuel balance, RC random roll, RE destination.
    # A negative balance leaves every pilot field untouched; the caller
    # reports the refusal after the page has closed. Equality may commit.
    m.page(24,'jump_tick').ld(6).ld('C').op('-').st('D').jneg('jump_tick_done').st(6).add(3,1)
    # Encounters observe only the old 16-bit generator's low four bits.
    # (253*s+13849) mod 16 == (13*(s mod 16)+9) mod 16. Store only that
    # projected state; 13*r+9 is at most 204, so mod16 stays exact.
    m.ld(8).n(13).op('*').n(9).op('+').call('mod16').st(8).st('C').ld(2).st('E')
    m.label('jump_tick_done').op('ret')

    m.end_page()

    m=a.module(11,'contacts')
    # Equipment cannot change in flight. Decode the laser once per contact;
    # COMBAT R8 holds its base damage throughout the battle.
    m.label('start_contact').st(1).get(25,6).n(1).op('swap','roll').raw(0x0C).n(12).op('*').n(20).op('+').st('D')
    m.ld(1).st('C').visit(27,'init_enemy').visit(28,'init_drones').ld('D').st(6).ld('E').st(8)
    m.set(5,0).set(7,GLYPHS['H']+65).ptr(9,'combat_input_entry',negate=True,lift=False).set('A',0).op('ret')
    m.page(27,'init_enemy').ld('D').st(8).ld('C').st(0).n(2).op('*').n(10).op('+').st(7)
    # Types 2/4 imply hull 60/120 and initial drone count 0/2.
    m.ld(0).n(30).op('*').st(1)
    m.label('enemy_fields').ld(1).st('E').set(2,14).op('cx')
    for i in range(4,7):m.st(i)
    m.set(3,3).op('ret').end_page().page(28,'init_drones').op('cx')
    for i in range(9):m.st(i)
    m.ld('C').n(2).op('-').st(6).jz('drones_done').set(0,18).st(1).set(5,1)
    m.label('drones_done').ld(6).st('D').op('ret')
    m.end_page()
