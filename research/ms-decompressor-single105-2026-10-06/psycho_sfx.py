"""One 105-cell program page. No code, seeds or startup in another bank.

M61 assigns ordinary gameplay registers after the first native run. The
20-byte native unpacker obtains both of its seeds from the loaded program.
"""
from concurrent.futures import ThreadPoolExecutor
from itertools import product
import json,random,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
START=83
KERNEL=bytes.fromhex('56 55 68 4b 67 08 40 14 60 4c 14 bc 6b 11 5d 91 40 55 56 52')
TAIL=bytes.fromhex('6e 01 10 4e 50 6d 01 11 4d 50 6e 03 11 59 80 6c 50 02 00 50')
SERVICES={0:0x54,7:0x8a,14:0x8b,21:0x54,28:0x8b,35:0x8a,42:0x8b,49:0x8a}
CELL={0:0,3:4,6:11,9:18,12:25,15:32,18:39,21:7,26:46,29:53,32:60,35:14,38:8,41:15,44:35,49:21,50:22,53:29,56:36,59:43,62:49,67:50,70:57,73:28,76:59,79:3,82:42,85:10,88:17,91:73}
PLACE=[0,11,12,13,14,15,16,17,18,19]
ORIGINAL=bytes.fromhex(next(p['raw'] for p in json.loads((ROOT/'tmp/ms-compression-search-2026-10-01/catalog.json').read_text())['programs'] if p['title']=='The Land of Psycho Lamers'))
EXPECTED=bytearray(b''.join(bytes([0,0x60+i,0x50,0,0x61+i,0x50,0]) for i in range(9)))
for a,b in SERVICES.items():EXPECTED[a]=b
EXPECTED=bytes(EXPECTED)
assert len(KERNEL)==20 and len(TAIL)==20 and START+len(KERNEL)<=105
assert len(set(CELL.values()))==len(CELL)==30


def image(reference=False,parts=0,health=5):
    if reference:
        regs=dict(enumerate(PLACE+[30,20]));regs.update({13:health,14:parts})
        lines=['reinit']+[f'R{r:X}= {v}' for r,v in regs.items()]+['hin 0000 '+ORIGINAL.hex(),'run']
    else:
        lines=['reinit','hin 0000 545183']
        for a,b in SERVICES.items():
            if a not in (0,49):lines.append(f'hin {a:04d} {b:02x}')
        lines += ['hin 0049 8a6850','hin 0053 6950','hin 0057 10','hin 0060 1040','hin 0063 '+(TAIL+KERNEL).hex(),'run']
        regs=dict(enumerate(PLACE+[63,68,30,health,parts]))
        lines += [f'R{r:X}= {v}' for r,v in regs.items()]+['run']
    for line in lines:
        if line.startswith('hin '):
            _,a,h=line.split();assert int(a)+len(h)//2<=105,(a,h)
    return '\n'.join(lines)+'\n'


def run(runner,name,cells,reference=False,parts=0,health=5):
    folder=HERE/'probes'/('reference' if reference else 'selfextract')/name;folder.mkdir(parents=True,exist_ok=True)
    source=image(reference,parts,health);(folder/'autoexec.m61').write_text(source)
    commands='dump\n'+''.join(f'{"jump" if reference else "goto"} {a if reference else CELL[a]:02d}\n' for a in cells)
    p=subprocess.run([str(runner),str(folder)],input=commands,text=True,capture_output=True,check=True,timeout=20)
    states=[json.loads(s) for s in p.stdout.splitlines()]
    assert len(states)==len(cells)+1,(name,p.stdout)
    for s in states:
        assert not s['error'] and not s['running'],(name,s)
        assert s['pc']<105 or (reference and s['pc']==105),(name,'PC out of page',s['pc'])
        if not reference:
            assert s['output_code'][0]==EXPECTED.hex(),(name,s['output_code'][0])
            assert s['output_tail'][0]==(TAIL+KERNEL+bytes(112-103)).hex(),name
            assert s['regs'][15]==0,(name,'RF changed')
    (folder/'states.json').write_text(json.dumps(states,indent=2)+'\n')
    return states


def compare(runner,case):
    name,cells,parts,health=case
    old=run(runner,name,cells,True,parts,health);new=run(runner,name,cells,False,parts,health)
    project=lambda s:(s['x'],tuple(s['regs'][r] for r in list(range(10))+[13,14]))
    assert list(map(project,old))==list(map(project,new)),name
    hp=health;count=parts
    places={0:0,3:1,6:2,9:3,12:4,15:5,18:6,26:7,29:8,32:9,38:1,41:2,53:4,56:5,59:6,67:7,70:8,76:9,79:1,85:2,88:3}
    for cell,s in zip([0]+cells,new):
        if cell in (21,44,62):count+=1;wanted=count
        elif cell in (35,73,82):hp-=1;wanted=hp
        elif cell==91:wanted=30 if count>=3 else 20
        elif cell in (49,50):wanted=13
        else:wanted=PLACE[places[cell]]
        assert s['x']==wanted,(name,cell,s['x'],wanted)
    return {'case':name,'stops':len(new),'outputs':[s['x'] for s in new]}


def main(runner):
    rng=random.Random(20261001)
    cases=[('all-cells',list(CELL),0,5),('victory',[3,6,21,38,41,44,49,50,53,56,59,62,79,88,91],0,5),('defeat',[29,32,35,32,35,32,35,32,35,32,35],0,5)]
    for parts,health in product(range(5),(1,5)):cases.append((f'exit-{parts}-{health}',[91,21,91,35,91],parts,health))
    for i in range(40):cases.append((f'random-{i:02d}',[rng.choice(list(CELL)) for _ in range(20)],0,5))
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda c:compare(runner,c),cases))
    source=image();(HERE/'psycho-selfextract.m61').write_text(source)
    (HERE/'psycho-expanded.raw').write_bytes(EXPECTED+TAIL)
    (HERE/'psycho-decoder.raw').write_bytes(KERNEL)
    loaded=sum(len(line.split()[2])//2 for line in source.splitlines() if line.startswith('hin '))
    assert loaded==57
    report={'decoder_bytes':20,'packed_code_and_data_bytes_including_entry':loaded,'expanded_game_bytes':len(EXPECTED)+len(TAIL),'expanded_game_plus_decoder_bytes':START+len(KERNEL),'highest_written_address':102,'program_limit':105,'extra_program_banks':0,'uses_rf':False,'entry_before_unpacking':'00 NOP; 01 BP 83','entry_after_unpacking':'00 NOP; 01 RCL 0; 02 STOP','initialization':'M61 R0= .. RE= after unpacking, no program-memory bytes','ms_bytes_generated':63,'scenarios':len(rows),'checked_game_stops':sum(r['stops'] for r in rows),'text_m61_bytes':len(source.encode()),'requires_ms_enabled_mk61s_mode':True,'reference_is_reconstruction':True,'cell_map':CELL,'cases':rows}
    (HERE/'psycho-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases','cell_map')},indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
