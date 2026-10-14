"""A 103-byte game bank and 20-byte affine unpacker using only R0..RE.

The map is relocated. The original catalog is read only. The saved .m61
contains literal seed records and native calculator instructions, not a host
compression routine or injected registers. Zero holes come from reinit.
"""
from concurrent.futures import ThreadPoolExecutor
from itertools import product
import json,subprocess,random
from pathlib import Path
import sys
from affine20 import pack,DECODER
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools/elite'))
from assembler import Assembler
BANK=24
START=83
KERNEL=bytearray(DECODER);KERNEL[15]=0x91;KERNEL=bytes(KERNEL)
assert len(KERNEL)==20
TAIL=bytes.fromhex('6e 01 10 4e 50 6d 01 11 4d 50 6e 03 11 59 80 6c 50 02 00 50')
assert len(TAIL)==20
SERVICES={7:0x8a,14:0x8b,21:0x54,28:0x8b,35:0x8a,42:0x8b,49:0x8a}
CELL={0:0,3:4,6:11,9:18,12:25,15:32,18:39,21:7,26:46,29:53,32:60,35:14,38:8,41:15,44:35,49:21,50:22,53:29,56:36,59:43,62:49,67:50,70:57,73:28,76:59,79:3,82:42,85:10,88:17,91:73}
VALUES=[0,11,12,13,14,15,16,17,18,19,30,20,0,5,0,0]
ORIGINAL=bytes.fromhex(next(p['raw'] for p in json.load(open(ROOT/'tmp/ms-compression-search-2026-10-01/catalog.json'))['programs'] if p['title']=='The Land of Psycho Lamers'))
EXPECTED=bytearray(b''.join(bytes([0,0x60+i,0x50,0,0x61+i,0x50,0]) for i in range(9)))
for i,v in SERVICES.items():EXPECTED[i]=v
EXPECTED=bytes(EXPECTED)

def image(name,reference=False,parts=0,health=5):
 a=Assembler();m=a.module(0,name)
 for r in list(range(12))+[13,14]:m.set(r,parts if r==14 else health if r==13 else VALUES[r])
 common=m.items.copy()
 if not reference:
  m.far(0x53,BANK*112+START)
  m.ld('A').st('C').set('A',63).set('B',68)
 m.far(0x51,BANK*112)
 banks,info=a.link();boot=bytes(banks[0][:info['banks']['0']['used']])
 lines=['reinit',f'hin 0000 {boot.hex()}']
 if reference:lines += [f'hin {BANK*112:04d} {ORIGINAL.hex()}']
 else:
  for offset,value in SERVICES.items():
   if offset!=49:lines.append(f'hin {BANK*112+offset:04d} {value:02x}')
  # Seven-byte records include both service bytes, as loaded on the device.
  seeds=bytearray(pack('690050.68')+pack('10000.01'));seeds[0]=SERVICES[49]
  j=0
  while j<len(seeds):
   if seeds[j]==0:j+=1;continue
   k=j+1
   while k<len(seeds) and seeds[k]!=0:k+=1
   lines.append(f'hin {BANK*112+49+j:04d} {seeds[j:k].hex()}');j=k
  lines.append(f'hin {BANK*112+63:04d} {(TAIL+KERNEL).hex()}')
 lines.append('run')
 return '\n'.join(lines)+'\n',boot

def run(runner,name,cells,reference=False,parts=0,health=5):
 folder=HERE/'psycho-probes'/('reference' if reference else 'selfextract')/name;folder.mkdir(parents=True,exist_ok=True)
 source,boot=image(name,reference,parts,health);(folder/'autoexec.m61').write_text(source)
 commands='dump\n'+''.join(f'{"jump" if reference else "goto"} {a if reference else CELL[a]:02d}\n' for a in cells)
 p=subprocess.run([str(runner),str(folder)],input=commands,capture_output=True,text=True,check=True,timeout=20)
 states=[json.loads(line) for line in p.stdout.splitlines()]
 assert len(states)==len(cells)+1,(folder,p.stdout)
 for s in states:
  assert not s['error'] and not s['running'],(folder,s)
  if not reference:
   assert s['regs'][15]==0,(folder,'RF changed',s['regs'][15])
   assert s['output_code'][0]==EXPECTED.hex(),(folder,s['output_code'][0])
   assert s['output_tail'][0]==(TAIL+KERNEL+bytes(112-START-len(KERNEL))).hex(),(folder,s['output_tail'][0])
 (folder/'states.json').write_text(json.dumps(states,indent=2)+'\n')
 return states,boot

def compare(runner,case):
 name,cells,parts,health=case
 old,oldboot=run(runner,name,cells,True,parts,health)
 new,newboot=run(runner,name,cells,False,parts,health)
 project=lambda s,reference:(s['x'],tuple(s['regs'][r] for r in list(range(10))+([10] if reference else [12])+[13,14]))
 # The failure message is now literal 20, with no register backing it.
 oldp=[project(s,True) for s in old];newp=[project(s,False) for s in new]
 assert oldp==newp,(name,cells,oldp,newp)
 # Independent game rules for each screen, including all duplicated map cells.
 count=parts;hp=health
 for cell,s in zip([0]+cells,new):
  if cell in (21,44,62):count+=1;wanted=count
  elif cell in (35,73,82):hp-=1;wanted=hp
  elif cell==91:wanted=30 if count>=3 else 20
  elif cell in (49,50):wanted=13
  else:wanted=VALUES[{0:0,3:1,6:2,9:3,12:4,15:5,18:6,26:7,29:8,32:9,38:1,41:2,53:4,56:5,59:6,67:7,70:8,76:9,79:1,85:2,88:3}[cell]]
  assert s['x']==wanted,(name,cell,s['x'],wanted)
 return {'case':name,'cells':cells,'parts':parts,'health':health,'stops':len(new),'reference_boot_bytes':len(oldboot),'sfx_boot_bytes':len(newboot),'outputs':[s['x'] for s in new]}

def main(runner):
 rng=random.Random(20261001)
 cases=[('all-cells',list(CELL),0,5),('victory',[3,6,21,38,41,44,49,50,53,56,59,62,79,88,91],0,5),('defeat',[29,32,35,32,35,32,35,32,35,32,35],0,5)]
 for parts,health in product(range(5),(1,5)):
  cases.append((f'exit-{parts}-{health}',[91,21,91,35,91],parts,health))
 for i in range(40):cases.append((f'random-{i:02d}',[rng.choice(list(CELL)) for _ in range(20)],0,5))
 assert len(set(CELL.values()))==len(CELL)
 assert START+len(KERNEL)<=105
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda c:compare(runner,c),cases))
 source,boot=image('playable')
 (HERE/'psycho-selfextract.m61').write_text(source)
 (HERE/'psycho-expanded.raw').write_bytes(EXPECTED+TAIL)
 (HERE/'psycho-decoder.raw').write_bytes(KERNEL)
 oldsource,oldboot=image('reference',True)
 seed_loaded=sum(v!=0 for v in pack('690050.68')+pack('10000.01'))+1
 input_payload=6+seed_loaded+len(TAIL)+len(KERNEL)+(len(boot)-len(oldboot))
 loaded=sum(len(line.split()[2])//2 for line in source.splitlines() if line.startswith('hin '))
 assert loaded-len(oldboot)==input_payload,(loaded,len(oldboot),input_payload)
 report={'decoder_bytes':20,'seed_records_bytes':14,'seed_nonzero_loaded_bytes':seed_loaded,'separate_service_bytes':6,'resident_game_bytes':len(TAIL),'extra_bootstrap_bytes':len(boot)-len(oldboot),'native_payload_with_all_setup_overhead':input_payload,'original_program_bytes':len(ORIGINAL),'original_nonzero_bytes':sum(v!=0 for v in ORIGINAL),'payload_saving_against_zero_omitted_reference':sum(v!=0 for v in ORIGINAL)-input_payload,'payload_if_seed_records_stored_in_full':input_payload+14-seed_loaded,'expanded_game_bytes':len(EXPECTED)+len(TAIL),'initial_memory_span':START+20,'first_head_bytes_written':63,'loaded_m61_file_bytes':len(source.encode()),'contiguous_reference_m61_file_bytes':len(oldsource.encode()),'size_excludes_text_transport_and_clear_zero_holes':True,'entry_method_sfx':'native BP address keys and C/P','entry_method_reference':'controlled IP, then native C/P','relocated_registers':{'end_success':'A -> C','end_failure':'literal 20','part_jump':'A = 63','health_jump':'B = 68'},'scenarios':len(rows),'checked_game_stops':sum(r['stops'] for r in rows),'map_relocated':True,'all_map_addresses_unique':len(set(CELL.values()))==len(CELL),'fits_105_addresses':START+len(KERNEL)<=105,'requires_expanded_mode_for_ms_and_banks':True,'uses_rf':False,'decoder_delta_register':'B','last_local_address':START+len(KERNEL)-1,'removed_duplicate_code_bytes':8,'reference_file':'/Users/bolk/Projects/MK-61/games/adventure/the-land-of-psycho-lamers.txt','cell_map':CELL,'cases':rows}
 (HERE/'psycho-report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('cases','cell_map')},indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
