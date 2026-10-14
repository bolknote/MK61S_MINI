"""Twenty native bytes expand two seeds to nine real RCL/STOP code words."""
from decimal import Decimal
import json, subprocess
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools/elite'))
from assembler import Assembler
BANK=24
DECODER=bytes.fromhex('56 55 68 4f 67 08 40 14 60 4c 14 bc 6f 11 5d 71 40 55 56 52')
assert len(DECODER)==20

def pack(n):
 v=Decimal(str(n)); sign,digits,e=abs(v).normalize().as_tuple(); exponent=len(digits)+e-1
 if not v:return bytes(7)
 s=''.join(map(str,digits)).ljust(8,'0');assert len(s)==8
 t=list(map(int,s[::-1]))+[9 if v<0 else 0,exponent%10,exponent//10,0]
 return bytes([0]+[t[i]|t[i+1]<<4 for i in range(0,12,2)])

def run(runner,case='main',regs=None,ms=None):
 a=Assembler();m=a.module(0,case);m.op('cx','stop')
 if regs is not None:
  for r,v in enumerate(regs):m.set(r,v)
 if ms is not None:m.raw(0x1f,0x56,25)
 m.far(0x53,BANK*112+63)
 if ms is not None:m.raw(0x1f,0x56,25)
 m.op('cx','stop')
 banks,info=a.link();boot=bytes(banks[0][:info['banks']['0']['used']])
 head=bytearray(63);head[49:56]=pack('690050.68');head[56:63]=pack('10000.01')
 folder=HERE/'affine20-probes'/case;folder.mkdir(parents=True,exist_ok=True)
 (folder/'autoexec.m61').write_text('reinit\nhin 0000 '+boot.hex()+f'\nhin {BANK*112:04d} '+head.hex()+f'\nhin {BANK*112+63:04d} '+DECODER.hex()+'\n'+(f'hin {25*112:04d} '+b''.join(pack(n) for n in ms).hex()+'\n' if ms is not None else '')+'run\n')
 p=subprocess.run([str(runner),str(folder)],input='dump\nrun\n',capture_output=True,text=True,check=True,timeout=20)
 state=json.loads(p.stdout.splitlines()[-1]);(folder/'state.json').write_text(json.dumps(state,indent=2)+'\n')
 expected=b''.join(bytes([0,0x60+i,0x50,0,0x61+i,0x50,0]) for i in range(9))
 row={'case':case,'decoder':DECODER.hex(' '),'decoder_bytes':20,'seed_bytes':14,'boot_bytes':len(boot),'error':state['error'],'exact':state['output_code'][0]==expected.hex(),'expected':expected.hex(' '),'got':state['output_code'][0],'regs':state['regs']}
 if regs is not None:row['restored_regs']=state['regs'][:9]==regs
 if ms is not None:row['ms_restored']=state['output_code'][1]==b''.join(pack(n) for n in ms).hex()
 (folder/'expanded.raw').write_bytes(bytes.fromhex(state['output_code'][0]))
 return row
if __name__=='__main__':
 runner=Path(sys.argv[1]).resolve()
 rows=[run(runner),run(runner,'game-registers',[0,11,12,13,14,15,16,17,18]),run(runner,'signed-registers',[-1,23,-456,7890,-12,34,-56,78,-90]),run(runner,'nonempty-ms',list(range(9)),list(range(-4,5)))]
 (HERE/'affine20.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps(rows,indent=2))
