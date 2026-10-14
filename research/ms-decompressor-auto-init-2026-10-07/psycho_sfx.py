"""Native automatic game initialization and unpacking in one 105-cell page.

The M61 uses only reinit/hin and run 8. No R assignments,
stack injection, extra code banks, or RF use prepare the candidate.
"""
from concurrent.futures import ThreadPoolExecutor
from itertools import product
import json,random,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
START=86
KERNEL=bytes.fromhex('56 55 68 4d 67 60 4c 14 bc 6d 11 5d 91 40 55 56 05 4d 52')
TAIL=bytes.fromhex('6e 01 10 4e 50 6d 01 11 4d 50 6e 03 11 59 83 03 00 50 02 00 50')
SERVICES={0:0x54,7:0x8a,14:0x8b,21:0x54,28:0x8b,35:0x51,42:0x8b,49:0x8a}
CELL={0:0,3:4,6:11,9:18,12:25,15:32,18:39,21:7,26:46,29:53,32:60,35:14,38:8,41:15,44:35,49:21,50:22,53:29,56:36,59:43,62:49,67:50,70:57,73:28,76:59,79:3,82:42,85:10,88:17,91:75}
PLACE=[0,11,12,13,14,15,16,17,18,19]
ORIGINAL=bytes.fromhex(next(p['raw'] for p in json.loads((ROOT/'tmp/ms-compression-search-2026-10-01/catalog.json').read_text())['programs'] if p['title']=='The Land of Psycho Lamers'))
EXPECTED=bytearray(b''.join(bytes([0,0x60+i,0x50,0,0x61+i,0x50,0]) for i in range(9)))
for a,v in SERVICES.items():EXPECTED[a]=v
EXPECTED=bytes(EXPECTED)
assert len(KERNEL)==19 and len(TAIL)==21 and START+len(KERNEL)==105
assert len(set(CELL.values()))==len(CELL)==30


def packed_image():
    img=bytearray(105)
    for a,v in SERVICES.items():img[a]=v
    img[4]=0x80 # Initial word 0 is the numerical loop count 8.
    img[8:13]=bytes.fromhex('01 05 4b 09 4c') # RB=15; RC=9.
    img[15:21]=bytes.fromhex('6c 01 00 10 bc 6c')
    img[22:27]=bytes.fromhex('01 11 4c 57 37') # RC--, zero -> 37.
    img[29:35]=bytes.fromhex('06 05 4a 07 00 4b') # RA=65; RB=70.
    img[36:41]=bytes.fromhex('86 40 4e 51 29') # Jump to 86; R0=RE=0.
    img[50:56]=bytes.fromhex('68 50 00 69 50 00')
    img[56:63]=bytes.fromhex('00 10 00 00 10 40 00')
    img[65:86]=TAIL;img[86:105]=KERNEL
    return bytes(img)


def image(reference=False,rf_canary=None):
    if reference:
        regs=dict(enumerate(PLACE+[30,20]));regs.update({13:5,14:0})
        return '\n'.join(['reinit']+[f'R{r:X}= {v}' for r,v in regs.items()]+['hin 0000 '+ORIGINAL.hex(),'run'])+'\n'
    raw=packed_image();lines=['reinit'];a=0
    while a<len(raw):
        if raw[a]==0:a+=1;continue
        b=a+1
        while b<len(raw) and raw[b]!=0:b+=1
        lines.append(f'hin {a:04d} {raw[a:b].hex()}');a=b
    if rf_canary is not None:lines.append('RF= '+str(rf_canary))
    lines += ['run 8']
    return '\n'.join(lines)+'\n'


def run(runner,name,cells,reference=False):
    folder=HERE/'probes'/('reference' if reference else 'selfextract')/name;folder.mkdir(parents=True,exist_ok=True)
    source=image(reference);(folder/'autoexec.m61').write_text(source)
    commands='dump\n'+''.join(f'{"jump" if reference else "goto"} {a if reference else CELL[a]:02d}\n' for a in cells)
    r=subprocess.run([str(runner),str(folder)],input=commands,text=True,capture_output=True,check=True,timeout=20)
    states=[json.loads(s) for s in r.stdout.splitlines()]
    assert len(states)==len(cells)+1,name
    for s in states:
        assert not s['error'] and not s['running'],(name,s)
        assert s['pc']<=105 and (reference or s['pc']<105),(name,s['pc'])
        if not reference:
            assert s['output_code'][0]==EXPECTED.hex(),(name,s['output_code'][0])
            assert s['output_tail'][0]==(bytes(2)+TAIL+KERNEL+bytes(7)).hex(),name
            assert s['regs'][15]==0,(name,'RF changed')
    if not reference:
        assert states[0]['regs'][:15]==PLACE+[65,70,1,5,0],(name,states[0]['regs'])
    (folder/'states.json').write_text(json.dumps(states,indent=2)+'\n')
    return states


def compare(runner,case):
    name,cells,parts,health=case
    prefix=[21]*parts+[35]*(5-health)
    if prefix:prefix += [0]
    cells=prefix+cells
    old=run(runner,name,cells,True);new=run(runner,name,cells,False)
    project=lambda s:(s['x'],tuple(s['regs'][r] for r in list(range(10))+[13,14]))
    assert list(map(project,old))==list(map(project,new)),name
    hp=5;count=0
    places={0:0,3:1,6:2,9:3,12:4,15:5,18:6,26:7,29:8,32:9,38:1,41:2,53:4,56:5,59:6,67:7,70:8,76:9,79:1,85:2,88:3}
    for cell,s in zip([0]+cells,new):
        if cell in (21,44,62):count+=1;wanted=count
        elif cell in (35,73,82):hp-=1;wanted=hp
        elif cell==91:wanted=30 if count>=3 else 20
        elif cell in (49,50):wanted=13
        else:wanted=PLACE[places[cell]]
        assert s['x']==wanted,(name,cell,s['x'],wanted)
    return {'case':name,'stops':len(new),'setup_game_moves':len(prefix),'outputs':[s['x'] for s in new]}


def main(runner):
    rng=random.Random(20261001)
    cases=[('all-cells',list(CELL),0,5),('victory',[3,6,21,38,41,44,49,50,53,56,59,62,79,88,91],0,5),('defeat',[29,32,35,32,35,32,35,32,35,32,35],0,5)]
    for parts,health in product(range(5),(1,5)):cases.append((f'exit-{parts}-{health}',[91,21,91,35,91],parts,health))
    for i in range(40):cases.append((f'random-{i:02d}',[rng.choice(list(CELL)) for _ in range(20)],0,5))
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda c:compare(runner,c),cases))
    source=image();loaded=sum(len(line.split()[2])//2 for line in source.splitlines() if line.startswith('hin '))
    assert loaded==79<=82 and not any(line.startswith('R') or line.startswith('poke') for line in source.splitlines())
    (HERE/'psycho-selfextract.m61').write_text(source)
    (HERE/'packed-image.raw').write_bytes(packed_image())
    (HERE/'psycho-expanded.raw').write_bytes(EXPECTED+bytes(2)+TAIL)
    (HERE/'psycho-decoder.raw').write_bytes(KERNEL)
    report={'complete_native_code_and_data_bytes_including_initialization':loaded,'budget':82,'budget_remaining':82-loaded,'decoder_bytes':len(KERNEL),'expanded_game_bytes':86,'expanded_game_plus_decoder_bytes':105,'highest_address_written':104,'highest_code_address':104,'extra_banks':0,'uses_rf':False,'m61_register_assignments':0,'initialization':'native calculator commands before exchanges','entry':'run 8','game_entry_after_unpacking':0,'part_routine':65,'health_routine':70,'exit_cell':75,'scenarios':len(rows),'checked_game_stops':sum(r['stops'] for r in rows),'ms_bytes_generated':63,'text_m61_bytes':len(source.encode()),'requires_ms_enabled_mk61s_mode':True,'cell_map':CELL,'cases':rows}
    (HERE/'psycho-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases','cell_map')},indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
