from assembler import GLYPHS, READ, WRITE
from ui import show_name, show_number, show_text

def dynamic_get(m,bank,index):
    m.ld(index).st('B').far(0x53,bank*112+63)

def dynamic_put(m,bank,index):
    m.st('C').ld(index).st('B').far(0x53,bank*112+WRITE)

def add_economy(a):
    m=a.module(1,'initialization')
    m.label('init_pilot')
    for i,v in enumerate(a.data[24]):m.set(i,v)
    m.op('ret').label('init_hold')
    m.n(0)
    for i in (0,1,2,3,4,5,8):m.st(i)
    m.set(6,a.data[25][6]).set(7,3).op('ret')
    m.label('sum_hold').ld(0)
    for i in range(1,6):m.ld(i).op('+')
    m.st('C').op('ret')
    # HOLD callback: RB good -> RD held, RC free capacity, in one opening.
    m.label('trade_hold').raw(0xDB).st('D').call('sum_hold')
    m.ld(6).call('mod100').ld('C').op('-').st('C').op('ret')
    m.label('trade_money').ld('C').st(0).add(3,1).op('ret')

    m=a.module(5,'world')
    m.label('world').st('D').n(251).op('*').n(12345).op('+').mod(65536).n(256).op('*').ld('D').op('+','ret')
    m.label('select_world').ld(0).n(70).op('-').call('world').put(24,2).set('A',8).op('ret')
    # Decode the world's economy once on arrival, in the formerly reserved R2.
    m.label('init_market').ld('C').st(0).n(1048576).op('/','int').st(2).ld('D').st(1).n(30)
    for i in range(3,9):m.st(i)
    m.op('ret')
    m.label('arrived_pilot').ld(2).st(1).st('C').ld(3).st('D').set(5,60).set(7,0).op('ret')

    m=a.module(6,'prices')
    # A single open market page supplies both economy and stock. RD retains
    # the unclamped quote; R2 carries it back to a trade for its next display.
    m.label('price').ld(1).st('B').visit(26,'price_market').ld('D').st(2).ld('C').op('ret')
    # economy + 2*good is in 0..25: one subtraction replaces general mod 16.
    m.label('price_market').ld('B').n(2).op('*').ld(2).op('+').n(16).op('-').jge('price_wrapped')
    m.n(16).op('+')
    m.label('price_wrapped').n(16).op('+').st('D')
    # Consecutive factors give an even product. This is exactly the original
    # floor((g+1)*(g+2)*10*(80+5*e)/100), with smaller integer intermediates.
    m.ld('B').n(1).op('+').ld('B').n(2).op('+','*').n(2).op('/').ld('D').op('*').st('D')
    m.ld('B').n(3).op('+').st('B').raw(0xDB).st('E')
    m.n(30).op('swap','-').n(2).op('*').ld('D').op('+').st('D').st('C').n(1).op('-').jge('price_ready')
    m.set('C',1).label('price_ready').op('ret')

    m=a.module(7,'trade')
    m.label('trade').call('price').st(3).ld('E').st(6).ld(7).jge('trade_quote')
    # Four-credit spread prevents making money by buying and immediately
    # selling into the two-credit stock adjustment of the same market.
    m.ld(3).n(4).op('-').call('max0').st(3)
    m.label('trade_quote').get(24,0).st(4)
    m.ld(7).jneg('sell_checks')
    m.ld(4).ld(3).op('-').jneg('bad_action').ld(6).jz('bad_action')
    m.ld(1).st('B').visit(25,'trade_hold').ld('D').st(5)
    m.ld('C').jz('bad_action').jneg('bad_action')
    m.jump('trade_commit')
    m.label('sell_checks');dynamic_get(m,25,1)
    m.st(5).jz('bad_action').ld(6).n(99).op('-').jge('bad_action')
    m.n(99999999).ld(3).op('-').ld(4).op('-').jneg('bad_action')
    # Keep credits beneath the product in Y instead of swapping afterwards.
    m.label('trade_commit').ld(4).ld(3).ld(7).op('*','-').st('C').visit(24,'trade_money')
    m.ld(5).ld(7).op('+');dynamic_put(m,25,1)
    m.ld(6).ld(7).op('-').st('C').ld(1).n(3).op('+').st('B').far(0x53,26*112+WRITE)
    # Keep the unclamped quote: at saturated stocks max(1, raw)+2 is wrong.
    m.ld(2).ld(7).n(2).op('*','+').st('C').n(1).op('-').jge('trade_price_ready')
    m.set('C',1)
    m.label('trade_price_ready').ld(1).n(30).op('+').st('A').op('ret')

    m=a.module(8,'station')
    m.label('station').set(3,5).set(4,6).set(5,24*112+WRITE).set(7,1).set(8,99)
    m.ld(0).n(50).op('-').jz('service_ready')
    m.ld(0).n(51).op('-').jz('service_hull')
    m.ld(0).n(52).op('-').jz('service_missile')
    m.set(3,300).set(5,25*112+WRITE).set(7,1000000).set(8,3010420).jump('service_ready')
    m.label('service_hull').set(3,20).set(4,4).set(7,10).jump('service_ready')
    m.label('service_missile').set(3,60).set(4,7).set(5,25*112+WRITE).set(8,9)
    m.label('service_ready').ld(4).st('B').ld(5).n(WRITE-READ).op('-').st('E').raw(0x1F,0xAE).st(2)
    m.ld(8).op('-').jge('bad_action').ld(2).ld(7).op('+').st(2).ld(8).op('-').jneg('service_pay')
    m.ld(8).st(2)
    m.label('service_pay').call('pay').jneg('bad_action')
    m.ld(2).st('C').ld(4).st('B').ld(5).st('E').raw(0x1F,0xAE).set('A',1).op('ret')
    m.label('pay').get(24,0).ld(3).op('-').jneg('pay_done').st('C').visit(24,'trade_money').n(0)
    m.label('pay_done').op('ret')

    m=a.module(9,'navigation')
    m.label('distance').get(24,2).call('mod256').st(0).get(24,1).call('mod256').st(1)
    m.ld(0).n(16).op('/','int').ld(1).n(16).op('/','int','-','abs').st(2)
    m.ld(0).call('mod16').ld(1).call('mod16').op('-','abs').ld(2).op('+').st(2).op('ret')
    m.label('distance_view').call('distance').st('C').set('D',GLYPHS['r']).jump('draw_number')

    m=a.module(10,'flight')
    m.label('jump').call('distance').jz('bad_action')
    m.get(25,6).n(100).op('/','int').call('mod100').ld(2).op('-').jneg('bad_action')
    m.get(24,6).ld(2).op('-').jneg('bad_action')
    m.ld(2).st('C').visit(24,'jump_tick').ld('C').jz('alien_contact')
    m.st(3).get(24,2).n(65536).op('/','int').call('mod16').n(4).op('/','int').n(2).op('+')
    m.ld(3).op('swap','-').jneg('pirate_contact').jump('arrive')
    m.label('alien_contact').n(4).jump('start_contact')
    m.label('pirate_contact').n(2).jump('start_contact')
    m.label('arrive').visit(24,'arrived_pilot').visit(26,'init_market').set(9,1).set('A',0).op('ret')
    m.label('jump_tick').ld(6).ld('C').op('-').st(6).add(3,1)
    m.ld(8).n(253).op('*').n(13849).op('+').mod(65536).st(8).call('mod16').st('C').op('ret')

    m=a.module(11,'contacts')
    # Equipment cannot change in flight. Decode the laser once per contact;
    # COMBAT R8 holds its base damage throughout the battle.
    m.label('start_contact').st(1).get(25,6).n(1000000).op('/','int').n(12).op('*').n(20).op('+').st('D')
    m.ld(1).st('C').visit(27,'init_enemy').visit(28,'init_drones').ld('D').st(6).ld('E').st(8)
    m.set(5,0).set(7,GLYPHS['H']+65).set(9,2).set('A',0).op('ret')
    m.label('init_enemy').ld('D').st(8).ld('C').st(0).n(2).op('*').n(10).op('+').st(7)
    m.set(1,60).ld(0).n(4).op('-').jnz('enemy_fields').set(1,120)
    m.label('enemy_fields').ld(1).st('E').set(2,14).n(0)
    for i in range(3,7):m.st(i)
    m.set(4,3).op('ret').label('init_drones').n(0)
    for i in range(9):m.st(i)
    m.ld('C').n(4).op('-').jnz('drones_done').set(0,18).set(1,18).set(5,2).set(6,2)
    m.label('drones_done').ld(6).st('D').op('ret')
