"""Golden game scenarios run by the real ROM/core, never a host game model."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/elite'))
from assembler import ALPHABET, screen

COUNT=0
START=['run','input 0']

def play(commands):
    global COUNT
    r=subprocess.run([sys.argv[1],str(ROOT/'programs/games/ELITE')],
                     input='\n'.join(commands)+'\n',text=True,capture_output=True,
                     check=True,timeout=120)
    states=[json.loads(line) for line in r.stdout.splitlines()]
    for s in states:
        assert not s['running'] and not s['error'],s
        assert s['input_frame_stable'] and not s['auto_display'] and s['segmented'],s
        assert s['frame'][-2:]==[57,55],s
        assert s['pages'][5][:4]==s['pages'][5][4:8],s
        assert s['pages'][4][6]==sum(hp>0 for hp in s['pages'][4][:5]),s
    COUNT+=len(states)
    return states

def state(s):
    return s['pages'][:5]

def number(s,prefix,value):
    assert s['frame']==screen(f'{prefix} {value:08d}СП'),s

def encounter(seed=8,extra=()):
    return START+list(extra)+[f'set 24 8 {seed}','input 71','input 60']

def test_worlds_and_display():
    title,port,credits,again=play(START+['input 1','input 1'])
    assert title['frame']==[73,0,121,56,6,120,121,0,73,0,57,55]
    assert port['frame']==screen('dAdnAA    СП')
    assert port['pages'][0]==[1000,3160320,3160320,0,84,60,40,0,12345]
    number(credits,'C',1000)
    assert again['revision']==credits['revision']
    # Exhaustive coordinate/name coverage exercises eight-digit packed masks.
    states=play(START+[f'input {70+i}' for i in range(256)])[2:]
    names=set()
    for i,s in enumerate(states):
        code=(((251*i+12345)%65536)<<8)|i
        name=''.join(ALPHABET[(code>>shift)&15] for shift in (20,16,12,8,4,0))
        assert s['frame']==screen(name+'    СП'),(i,s)
        assert s['pages'][0][2]==code and s['pages'][0][3]==0,s
        names.add(name)
    assert len(names)==256
    print('ELITE: title, frozen display, 256 worlds and register F callbacks OK',flush=True)

def test_trade_and_station():
    s=play(START+['input 10','input 30','input 20','input 40','input 40'])
    number(s[2],'1',19)
    assert s[3]['pages'][0][0]==981 and s[3]['pages'][1][0]==1
    assert s[3]['pages'][2][3]==29
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

def test_navigation_and_input():
    s=play(START+['input 71','input 9','input 60'])
    number(s[3],'r',1)
    assert s[-1]['pages'][0][1:4]==[3224577,3224577,1]
    assert s[-1]['pages'][0][6]==39 and s[-1]['regs'][9]==1
    # The second letter changes piracy risk for the same random roll.
    for destination,mode in ((71,1),(74,2)):
        s=play(START+['set 24 8 13',f'input {destination}','input 60'])[-1]
        assert s['regs'][9]==mode,s
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
    assert s[3]['frame']==screen('PIrAtE    СП') and s[3]['regs'][9]==2
    assert s[4]['pages'][3][1:3]==[40,12] and s[4]['pages'][0][5]==46
    assert s[4]['pages'][0][7]==28
    number(s[5],'H',40)
    assert s[6]['frame']==screen('YES. CLEAr СП') and s[6]['regs'][9]==3
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
    assert s[-1]['regs'][9]==1 and s[-1]['pages'][0][4]==84
    s=play(encounter()+['set 25 7 0','dump','input 22'])
    assert state(s[-2])==state(s[-1])
    s=play(encounter()+['set 24 7 90','input 41'])[-1]
    assert s['pages'][3][1]==60 and s['pages'][0][7]==80 and s['pages'][0][5]==53
    s=play(encounter(extra=['input 53'])+['input 21'])[-1]
    assert s['pages'][3][1]==30 and s['pages'][0][0]==700
    s=play(encounter()+['input 34']*4)
    assert s[-2]['pages'][0][5]==32 and s[-1]['frame']==screen('SAFE      СП')
    print('ELITE: simultaneous fire, heat, range, missiles, escape, win/loss OK',flush=True)

def test_thargoids():
    s=play(encounter(3)+['input 81','input 41'])[-1]
    assert s['pages'][4][0]==9 and s['pages'][0][5]==48
    s=play(encounter(3)+['input 81','input 21','input 82','input 21','input 80','input 22'])
    assert s[3]['frame']==screen('tHArGOId  СП')
    assert s[3]['pages'][4][:7]==[18,18,0,0,0,2,2]
    assert s[5]['pages'][4][0]==0 and s[5]['pages'][3][1]==120
    assert s[5]['pages'][0][5]==36 # dead drone's simultaneous shot counts
    assert s[-1]['pages'][4][:7]==[0,0,18,0,0,3,1]
    s=play(encounter(3)+['set 27 2 30']+['input 23']*12)[-1]
    assert s['pages'][4][:7]==[18,18,18,18,18,5,5]
    # Victory with the initial ship and ammunition, without state fixtures.
    s=play(encounter(3)+['input 22']*3+
           ['input 81','input 21','input 82','input 21','input 83','input 21'])
    assert s[6]['pages'][3][1]==0 and s[6]['regs'][9]==2
    assert s[-1]['frame']==screen('YES. CLEAr СП') and s[-1]['pages'][1][8]==1
    assert s[-1]['pages'][4][6]==0
    for cmd in ('input 81','input 85','input 86','input 10','input 15','input 45','input 60'):
        s=play(encounter()+[cmd])
        assert state(s[-2])==state(s[-1]),(cmd,s[-1])
    print('ELITE: carrier, independent targets, five drones and alien victory OK',flush=True)

def main():
    directory=ROOT/'programs/games/ELITE'
    parts=sorted(directory.glob('part[0-9][0-9].m61'))
    assert len(parts)==6 and not list(directory.glob('b[0-9][0-9].m61'))
    expected=['open manual.md','reinit']+[f'open {p.name}' for p in parts]+['run']
    assert (directory/'autoexec.m61').read_text().splitlines()==expected
    addresses=[int(line.split()[1]) for p in parts for line in p.read_text().splitlines()]
    assert addresses==list(range(0,32*112,112))
    for path in directory.glob('*.m61'):
        assert path.stat().st_size<=1536
        assert all(len(line)<=239 for line in path.read_text().splitlines())
    for path in directory.glob('*.md'):
        assert path.stat().st_size<=1536
    tests=(test_worlds_and_display,test_trade_and_station,test_navigation_and_input,
           test_pirates_and_results,test_thargoids)
    for test in tests:
        if len(sys.argv)<3 or sys.argv[2] in test.__name__:test()
    print(f'ELITE real-core: {COUNT} stopped states verified',flush=True)

if __name__=='__main__':main()
