"""Golden game scenarios run by the real ROM/core, never a host game model."""
import json
from pathlib import Path
import subprocess
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/elite'))
from assembler import ALPHABET, GLYPHS, Assembler, screen
from game import create_game, check_layout

COUNT=0
START=['run','input 0']
LABELS=create_game().link()[1]['labels']


def game_mode(s):
    value=s['regs'][9]
    if value==0:return 0
    if value<0:
        address=LABELS['combat_input_entry']
        # ROM normalization changes the negative selector after its first
        # use, but its sign and local target must survive every command.
        assert value in (-address,-99999900-address),('bad combat pointer',s)
        return 2
    modes={LABELS['port_input_entry']:1,LABELS['result_input_entry']:3,
           LABELS['new_game']:4}
    assert value in modes,('bad mode pointer',s)
    return modes[value]


def play(commands):
    global COUNT
    r=subprocess.run([sys.argv[1],str(ROOT/'programs/games/ELITE')],
                     input='\n'.join(commands)+'\n',text=True,capture_output=True,
                     check=True,timeout=120)
    states=[json.loads(line) for line in r.stdout.splitlines()]
    for s in states:
        assert not s['running'] and not s['error'],s
        assert s['input_frame_stable'] and not s['auto_display'] and s['segmented'],s
        assert s['frame_changes']<=1,('partial display updates',s)
        assert s['frame'][-2:]==[57,55],s
        frame=[(word >> shift) & 255 for word in s['pages'][5][:4]
               for shift in (0,8,16)]
        assert frame==s['frame'],s
        assert s['pages'][4][6]==sum(hp>0 for hp in s['pages'][4][:5]),s
        if game_mode(s)==2:
            target=s['pages'][3][5]
            hull=s['pages'][3][1] if target==0 else s['pages'][4][target-1]
            assert s['regs'][8]==hull,('stale selected hull',s)
            assert s['regs'][6]==s['pages'][4][6],('stale live drones',s)
            assert s['regs'][5]==target,('stale selected target',s)
            assert s['regs'][7]==GLYPHS['H' if target==0 else str(target)]+65,('stale target glyph',s)
    COUNT+=len(states)
    return states

def state(s):
    return s['pages'][:5]

def number(s,prefix,value):
    if prefix=='H' and game_mode(s)==2 and s['regs'][10]==16:
        # The selected target and its exact hull sit beside the living swarm.
        target=s['pages'][3][5]
        tag='H' if target==0 else str(target)
        count=s['pages'][4][6]
        assert s['frame']==[99]*count+[0]*(6-count)+screen(f'{tag}.{value:03d}СП')[:6],s
        return
    assert s['frame']==screen(f'{prefix} {value:08d}СП'),s

def encounter(seed=8,extra=()):
    return START+list(extra)+[f'set 24 8 {seed}','input 71','input 60']

def test_assembler_continuations():
    a=Assembler()
    m=a.module(0,'caller')
    m.raw(*([0x54]*106)).label('call').far(0x53,152).raw(*([0x54]*5)).op('ret')
    a.module(1,'callee').raw(*([0x54]*40)).op('ret')
    banks,info=a.link()
    address=info['labels']['call']+4
    # The low address byte 52 must not masquerade as RET: execution after
    # the call must reach the continuation, never padding/stopped memory.
    assert banks[address//112][address%112] in (0x54,0x1F)
    a=Assembler();m=a.module(0,'labelled return')
    m.call('callee').label('return_entry').op('ret').label('callee').op('ret')
    banks,_=a.link()
    assert banks[0][0]==0x53 # a separately callable RET cannot be removed
    a=Assembler();m=a.module(0,'local branch')
    m.jz('target').raw(0x54).label('target').op('ret')
    before=a.expand_branches()
    assert not m.items[0].short
    after=a.relax_branches()
    assert m.items[0].short and after[0]['target']==before[0]['target']-2
    a=Assembler();m=a.module(0,'closed-entry fallthrough')
    m.n(3).st(0).jump('next').label('next').ld(0).op('ret')
    banks,_=a.link()
    assert banks[0][:5]==bytes([0x0e,3,0x40,0x60,0x52])
    a=Assembler();m=a.module(0,'independent jump entry')
    m.n(3).st(0).label('entry').jump('next').label('next').ld(0).op('ret')
    banks,_=a.link()
    assert banks[0][3]==0x51
    # Re-linking an optimized assembler must be deterministic.
    assert a.link()[0]==banks
    a=Assembler();m=a.module(0,'whole entry')
    m.raw(*([0x54]*100)).op('ret').label('helper',keep_block=True)
    for _ in range(12):m.raw(0x54)
    m.op('ret')
    banks,info=a.link()
    # Starting in the last eleven bytes would need a continuation jump.
    # The independent entry instead moves as one block, without a bridge.
    assert info['labels']['helper']==112 and info['occupied_bytes']==114
    assert banks[1][:13]==bytes([0x54]*12+[0x52])
    a=Assembler();m=a.module(0,'fallthrough into whole entry')
    m.raw(*([0x54]*100)).label('helper',keep_block=True)
    for _ in range(12):m.raw(0x54)
    m.op('ret')
    banks,info=a.link()
    assert info['labels']['helper']==112
    assert banks[0][100:104]==bytes([0x1F,0x51,0x01,0x12])
    a=Assembler();m=a.module(0,'exact block fit')
    m.raw(*([0x54]*90)).op('ret').label('helper',keep_block=True)
    for _ in range(20):m.raw(0x54)
    m.op('ret').label('next').op('ret')
    banks,info=a.link()
    # Do not reserve a bridge inside a protected block ending in RET at 111.
    assert info['labels']['helper']==91 and banks[0][111]==0x52
    assert info['labels']['next']==112 and info['occupied_bytes']==113
    print('ELITE: control flow, operand 52, labelled returns and whole blocks OK',flush=True)

def test_worlds_and_display():
    title,port,credits,again=play(START+['input 1','input 1'])
    assert title['frame']==[73,0,121,56,6,120,121,0,73,0,57,55]
    assert port['frame']==screen('dAdnAA    СП')
    assert port['pages'][0]==[1000,3160320,3160320,0,84,60,40,0,12345]
    number(credits,'C',1000)
    assert again['revision']==credits['revision']
    # Catch a return of the slow ROM loops that took 657/1142/1180 core steps.
    assert title['steps']<80 and port['steps']<220 and credits['steps']<150
    assert title['frame_changes']==port['frame_changes']==credits['frame_changes']==1
    assert again['frame_changes']==0
    # Exhaustive coordinate/name coverage exercises eight-digit packed masks.
    states=play(START+[f'input {70+i}' for i in range(256)])[2:]
    names=set()
    for i,s in enumerate(states):
        code=(((251*i+12345)%65536)<<8)|i
        name=''.join(ALPHABET[(code>>shift)&15] for shift in (20,16,12,8,4,0))
        assert s['frame']==screen(name+'    СП'),(i,s)
        assert s['pages'][0][2]==code and s['pages'][0][3]==0,s
        assert s['steps']<=88,('world generation regressed',i,s['steps'])
        names.add(name)
    assert len(names)==256
    print('ELITE: title, frozen display, 256 worlds and register F callbacks OK',flush=True)

def test_trade_and_station():
    s=play(START+['input 10','input 30','input 20','input 40','input 40'])
    number(s[2],'1',19)
    assert s[3]['pages'][0][0]==981 and s[3]['pages'][1][0]==1
    assert s[3]['pages'][2][3]==29
    assert s[3]['steps']<340,('trade recalculated the displayed quote',s[3])
    number(s[4],'1',1)
    assert s[5]['pages'][0][0]==998 and s[5]['pages'][1][0]==0
    assert state(s[5])==state(s[6]) and s[6]['frame']==screen('ErrOr     СП')
    s=play(START+['input 50','input 51','input 52','input 53','input 53','input 53'])
    assert s[2]['pages'][0][0]==995 and s[2]['pages'][0][6]==41
    assert s[3]['pages'][0][0]==975 and s[3]['pages'][0][4]==94
    assert s[4]['pages'][0][0]==915 and s[4]['pages'][1][7]==4
    assert s[6]['pages'][1][6]==3010420 and s[6]['pages'][0][0]==315
    assert state(s[6])==state(s[7])
    fixtures=[(['set 24 0 0'],'input 30'),(['set 24 0 0'],'input 50'),
              (['set 25 0 20'],'input 30'),(['set 26 3 0'],'input 30'),
              (['set 24 6 99'],'input 50'),(['set 24 4 99'],'input 51'),
              (['set 25 7 9'],'input 52')]
    for setup,cmd in fixtures:
        s=play(START+setup+['dump',cmd])
        assert state(s[-2])==state(s[-1]),(setup,s[-1])
    s=play(START+['set 24 4 95','input 51'])[-1]
    assert s['pages'][0][4]==99 and s['pages'][0][0]==980
    s=play(START+['set 24 0 10000']+[f'input {30+i}' for i in range(6)])[-1]
    assert s['pages'][1][:6]==[1]*6 and s['pages'][1][6]==1010420
    s=play(START+['set 24 0 99999999','set 25 0 1','input 1','input 40'])
    number(s[-2],'C',99999999)
    assert state(s[-2])==state(s[-1])
    print('ELITE: six goods, spread, capacity, money and station services OK',flush=True)

def test_price_equivalence():
    commands=START.copy()
    expected=[]
    for economy in range(16):
        commands += [f'set 24 1 {economy*1048576}',
                     f'set 26 0 {economy*1048576}',f'set 26 2 {economy}']
        for good in range(6):
            # The original unsimplified formula is the independent oracle.
            base=((good+1)*(good+2)*10*(80+5*((economy+2*good)%16)))//100
            for stock in (0,1,30,98,99):
                commands += [f'set 26 {3+good} {stock}',f'input {10+good}']
                expected.append((economy,good,max(1,base+2*(30-stock))))
    for s,(economy,good,quote) in zip(play(commands)[2:],expected):
        number(s,str(good+1),quote)
        assert s['pages'][2][2]==economy,s

    # Updating a clamped price as old_price+2 is wrong at abundant stock.
    for stock,command,credits,next_stock,quote in (
            (98,30,999,97,1),(40,30,999,39,1),(39,30,999,38,3),
            (98,40,1000,99,1),(39,40,1000,40,1),(38,40,1000,39,1)):
        s=play(START+[f'set 26 3 {stock}','set 25 0 1',f'input {command}'])[-1]
        number(s,'1',quote)
        assert s['pages'][0][0]==credits and s['pages'][2][3]==next_stock,s

    # A real arrival must replace the cached economy, not retain the old one.
    s=play(START+['set 25 6 1013120','set 24 8 1','input 214','input 60','input 10'])[-1]
    world=(((251*144+12345)%65536)<<8)|144
    assert game_mode(s)==1 and s['pages'][0][1]==world,s
    assert s['pages'][2][2]==world//1048576,s
    number(s,'1',16+world//1048576)
    print('ELITE: 480 original-formula quotes, minimum-price trades and arrival cache OK',flush=True)

def test_navigation_and_input():
    s=play(START+['input 71','input 9','input 60'])
    number(s[3],'r',1)
    assert s[-1]['pages'][0][1:4]==[3224577,3224577,1]
    assert s[-1]['pages'][0][6]==39 and game_mode(s[-1])==1
    # The second letter changes piracy risk for the same random roll.
    for destination,mode in ((71,1),(74,2)):
        s=play(START+['set 24 8 13',f'input {destination}','input 60'])[-1]
        assert game_mode(s)==mode,s
    for setup in ([],['input 325'],['input 71','set 24 6 0']):
        s=play(START+setup+['dump','input 60'])
        assert state(s[-2])==state(s[-1]),s[-1]
    for value in ('-1','1.5','16','29','36','46','54','69','326','99999999'):
        s=play(START+[f'input {value}'])
        assert state(s[1])==state(s[-1]) and s[-1]['frame']==screen('ErrOr     СП'),(value,s[-1])
    # More than the entire 64-entry return stack: no leaked return addresses.
    s=play(START+['input 0']*72)
    assert state(s[1])==state(s[-1]) and s[1]['revision']==s[-1]['revision']
    print('ELITE: routes, invalid input, free queries and return stack OK',flush=True)

def test_pirates_and_results():
    s=play(encounter()+['input 11','input 16','input 22','run','input 1'])
    assert s[3]['frame']==screen('PIrAtE    СП') and game_mode(s[3])==2
    assert s[4]['pages'][3][1:3]==[40,12] and s[4]['pages'][0][5]==46
    assert s[4]['pages'][0][7]==28
    number(s[4],'H',40) # a shot reports damage without another query
    number(s[5],'H',40)
    assert s[6]['frame']==screen('YES. CLEAr СП') and game_mode(s[6])==3
    assert s[6]['pages'][0][0]==1250 and s[6]['pages'][1][7:9]==[2,1]
    assert s[7]['pages'][0][1]==3224577 and s[7]['pages'][0][0]==1250
    assert s[8]['pages'][0][0]==1250
    s=play(encounter()+['input 44']*4+['run'])
    assert s[-2]['frame']==screen('SAFE      СП') and s[-2]['pages'][0][0]==1000
    assert s[-1]['pages'][0][1]==3224577 and s[-1]['pages'][1][8]==0
    # Both salvos resolve, even on mutual destruction. Defeat has priority.
    s=play(encounter()+['set 24 4 1','set 24 5 0','set 27 1 18','input 21','run'])
    assert s[-2]['frame']==screen('dEAd      СП') and s[-2]['pages'][3][1]==0
    assert s[-2]['pages'][0][0]==1000 and s[-2]['pages'][1][8]==0
    assert game_mode(s[-1])==1 and s[-1]['pages'][0][4]==84
    s=play(encounter()+['set 25 7 0','dump','input 22'])
    assert state(s[-2])==state(s[-1])
    s=play(encounter()+['set 24 7 90','input 41'])[-1]
    assert s['pages'][3][1]==60 and s['pages'][0][7]==80 and s['pages'][0][5]==53
    s=play(encounter(extra=['input 53'])+['input 21'])[-1]
    assert s['pages'][3][1]==30 and s['pages'][0][0]==700
    s=play(encounter()+['input 34']*4)
    assert s[-2]['pages'][0][5]==32 and s[-1]['frame']==screen('SAFE      СП')
    # The cap must keep its exact constant even when Lx reuses it after a
    # conditional branch. Cover both sides and equality, including 10^8.
    for credits in (99999748,99999749,99999750,99999999):
        s=play(encounter()+[f'set 24 0 {credits}','input 22','input 22'])[-1]
        assert s['frame']==screen('YES. CLEAr СП')
        assert s['pages'][0][0]==min(99999999,credits+250),s
        assert s['pages'][1][8]==1,s
    for shield in (41,42,43,60):
        s=play(encounter()+[f'set 24 5 {shield}','input 23'])[-1]
        assert s['pages'][0][4:6]==[84,min(60,shield+18)-14],s
        assert s['pages'][3][1]==60,s
    print('ELITE: simultaneous fire, heat, range, missiles, escape, win/loss OK',flush=True)

def test_thargoids():
    s=play(encounter(3)+['input 81','input 41'])[-1]
    assert s['pages'][4][0]==9 and s['pages'][0][5]==48
    s=play(encounter(3)+['input 81','input 21','input 82','input 21','input 80','input 22'])
    assert s[3]['frame']==screen('tHArGOId  СП')
    assert s[3]['pages'][4][:7]==[18,18,0,0,0,1,2]
    assert s[5]['pages'][4][0]==0 and s[5]['pages'][3][1]==120
    assert s[5]['pages'][0][5]==36 # dead drone's simultaneous shot counts
    assert s[-1]['pages'][4][:7]==[0,0,18,0,0,2,1]
    s=play(encounter(3)+['set 27 2 30']+['input 23']*12)[-1]
    assert s['pages'][4][:7]==[18,18,18,18,18,4,5]
    # Victory with the initial ship and ammunition, without state fixtures.
    s=play(encounter(3)+['input 22']*3+
           ['input 81','input 21','input 82','input 21','input 83','input 21'])
    assert s[6]['pages'][3][1]==0 and game_mode(s[6])==2
    # Graphics add a cached formation and target identity. Allow rebuilding
    # the formation on casualties, but never a repeated per-symbol ROM loop.
    assert s[4]['steps']<350 and s[6]['steps']<380,('repeated combat setup/page reads',s[4],s[6])
    assert s[8]['steps']<335,('extra ship-page opening in a laser turn',s[8])
    assert s[-1]['frame']==screen('YES. CLEAr СП') and s[-1]['pages'][1][8]==1
    assert s[-1]['pages'][4][6]==0
    for cmd in ('input 81','input 85','input 86','input 10','input 15','input 45','input 60'):
        s=play(encounter()+[cmd])
        assert state(s[-2])==state(s[-1]),(cmd,s[-1])
    print('ELITE: carrier, independent targets, five drones and alien victory OK',flush=True)

def test_destroyed_targets():
    dead_carrier=encounter(3)+['input 22']*3
    s=play(dead_carrier+['input 81','input 80'])
    number(s[6],'H',0)
    assert s[-1]['frame']==screen('ErrOr     СП')
    assert state(s[-2])==state(s[-1]) and s[-1]['pages'][3][5]==1
    # Both weapons reject a dead selected carrier or drone before any side
    # effect, including a missile which is actually available to consume.
    for setup in (dead_carrier,encounter(3)+['input 81','input 21']):
        for action in ('11','22','31','42'):
            s=play(setup+['set 25 7 2','dump',f'input {action}'])
            assert state(s[-2])==state(s[-1]),(action,s[-1])
            assert s[-1]['frame']==screen('ErrOr     СП')
        s=play(setup+['dump','input 23','input 24'])
        assert s[-2]['pages'][0][3]==s[-3]['pages'][0][3]+1
        assert s[-1]['pages'][3][6]==1 # a dead target cannot block escape
    s=play(encounter(3)+['input 81','input 21','input 81'])
    number(s[-2],'H',0)
    assert state(s[-2])==state(s[-1])
    print('ELITE: dead targets reject selection/fire atomically; defence and escape remain available OK',flush=True)

def test_combat_cache_and_motion():
    # Every legal free query, plus refused selections/commands, must retain
    # the selected hull cache and leave all persistent battle data unchanged.
    queries=[str(i) for i in range(10)]+['16','17','18','19','85','86','10','15','60']
    for target in ('80','81'):
        s=play(encounter(3)+[f'input {target}']+[f'input {q}' for q in queries])
        assert all(state(row)==state(s[4]) for row in s[5:])
        assert all(row['regs'][8]==s[4]['regs'][8] for row in s[5:])
    # The equipment cache must refresh at each contact and cover all laser
    # levels and manoeuvres, including range limits and evasive half-damage.
    for level in (1,2,3):
        for maneuver,initial_range,final_range in ((1,0,0),(1,14,12),(2,14,14),(3,18,20),(3,98,99),(4,14,14)):
            setup=[f'input 53']*(level-1)
            s=play(encounter(extra=setup)+[f'set 27 2 {initial_range}',f'input {maneuver}1'])[-1]
            damage=0 if final_range>18 else 20+12*level-final_range
            if maneuver==4:damage//=2
            assert s['pages'][3][1:3]==[max(0,60-damage),final_range],s
            assert s['pages'][3][8]==20+12*level,s
            number(s,'H',max(0,60-damage))
    # Returning to port and improving the laser must replace the old cache.
    s=play(encounter()+['input 22']*2+['run','input 53','set 24 8 8','input 70','input 60','input 21'])[-1]
    assert s['pages'][3][8]==44 and s['pages'][3][1]==30,s
    print('ELITE: battle queries preserve cached hull; three lasers, all manoeuvres and re-equipped contact OK',flush=True)

def test_instruments_and_formation():
    # Independent threshold oracle: each lit cell covers the next interval,
    # and the right-hand number remains exact at every zero/boundary/cap.
    for view,field,prefix,step,values in (
            (2,4,'H',20,(0,1,19,20,21,40,60,80,81,99)),
            (3,5,'S',12,(0,1,11,12,13,24,36,48,49,60)),
            (4,6,'F',20,(0,1,20,21,40,60,80,99)),
            (5,7,'t',20,(0,1,20,40,60,69,70,79,80,99))):
        commands=START.copy()
        for value in values:commands += [f'set 24 {field} {value}',f'input {view}',f'input {view}']
        rows=play(commands)[2:]
        for value,before,again in zip(values,rows[::2],rows[1::2]):
            cells=sum(value>threshold for threshold in range(0,5*step,step))
            expected=[GLYPHS[prefix]]+[54]*cells+[0]*(6-cells)+screen(f'{value:03d}СП')[:5]
            assert before['frame']==expected,(value,before)
            assert again['revision']==before['revision'] and state(again)==state(before)
    for value in (0,1,4,5,8,12,16,17,20):
        s=play(START+[f'set 25 0 {value}','input 7'])[-1]
        cells=sum(value>threshold for threshold in (0,4,8,12,16))
        assert s['frame']==[62]+[54]*cells+[0]*(6-cells)+screen(f'{value:03d}СП')[:5],s

    commands=encounter(3)
    for distance in range(100):commands += [f'set 27 2 {distance}','input 9']
    for distance,s in enumerate(play(commands)[4:]):
        expected=screen(f'r{distance:02d}U-----.-СП')
        position=4+min(distance//4,4) if distance<=18 else 9
        expected[position]=118|(128 if position==8 else 0)
        assert s['frame']==expected,(distance,s)
        assert s['pages'][0][3]==1 and s['pages'][3][2]==distance,s

    # Fill the formation, select every target, then remove drones one by one.
    # Queries between shots must not invalidate the formation or glyph cache.
    commands=encounter(3)+['set 27 2 30']+['input 23']*9+['set 25 7 9']
    for target in range(1,6):
        commands += [f'input {80+target}','input 3','input 9','input 16','input 22']
    rows=play(commands)
    for s in rows:
        if s['regs'][10]==16:number(s,'H',s['regs'][8])
    assert rows[-1]['pages'][4][6]==0 and rows[-1]['pages'][3][1]==120
    print('ELITE: instrument boundaries, 100 range diagrams, five targets and cached formation OK',flush=True)

def main():
    directory=ROOT/'programs/games/ELITE'
    parts=sorted(directory.glob('part[0-9][0-9].m61'))
    assert len(parts)==2 and not list(directory.glob('b[0-9][0-9].m61'))
    expected=['open? manual.md','reinit']+[f'open {p.name}' for p in parts]+['run']
    assert (directory/'autoexec.m61').read_text().splitlines()==expected
    # The real M61/core loader decodes all zin records before every scenario;
    # its checked CRC must describe the complete linked bank image.
    banks,info=create_game().link()
    check_layout(info)
    assert set(info['banks'])=={str(bank) for bank in banks}
    image=b''.join(banks.get(bank,bytes(112)) for bank in range(32))
    records=[line for part in parts for line in part.read_text().splitlines()]
    assert records[0]==f'ztart 0000 {zlib.crc32(image):08X}'
    assert all(line.startswith('zin ') for line in records[1:])
    assert sum(path.stat().st_size for path in parts)<2800
    for path in directory.glob('*.m61'):
        assert path.stat().st_size<=1536
        assert all(len(line)<=239 for line in path.read_text().splitlines())
    for path in directory.glob('*.md'):
        assert path.stat().st_size<=1536
    tests=(test_assembler_continuations,test_worlds_and_display,test_trade_and_station,test_price_equivalence,test_navigation_and_input,
           test_pirates_and_results,test_thargoids,test_destroyed_targets,test_combat_cache_and_motion,
           test_instruments_and_formation)
    for test in tests:
        if len(sys.argv)<3 or sys.argv[2] in test.__name__:test()
    print(f'ELITE real-core: {COUNT} stopped states verified',flush=True)

if __name__=='__main__':main()
