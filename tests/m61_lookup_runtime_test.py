"""Generic unsigned table-read controls; no Runner rules or device calls."""
import json,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tools'));from program_pack import program_binary
temp=tempfile.TemporaryDirectory(prefix='m61-lookup-');D=Path(temp.name);image=bytearray(224)
image[10]=123;image[12]=45;image[20:23]=bytes.fromhex('563412');image[26:29]=bytes.fromhex('030201');image[111:114]=bytes.fromhex('a1b2c3');image[123]=171
packed=program_binary(image);(D/'table.bin').write_bytes(packed);(D/'invalid.bin').write_bytes(bytes([packed[0]^1])+packed[1:]);(D/'autoexec.m61').write_text('load 0000 table.bin\n:l\nwait 60000\nrun :l\n')
p=subprocess.Popen([str(Path(sys.argv[1]).resolve()),str(D)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(D/'stderr').open('w'),text=True)
state=json.loads(p.stdout.readline());rows=[]
def send(line):
 p.stdin.write(line+'\n');p.stdin.flush();raw=p.stdout.readline();assert raw,('exit',p.poll());return json.loads(raw)
def evaluate(command,expected_error=False,dest=None,value=None):
 global state
 before=state;state=send('eval 0 '+command)
 assert state['eval_failed']==expected_error,(command,state)
 if expected_error or dest is None:assert state['regs']==before['regs']
 else:
  expected=list(before['regs']);expected[dest]=value;assert state['regs']==expected,(command,before['regs'],state['regs'],expected)
 assert state['stack']==before['stack'],command
 rows.append(dict(command=command,error=state['eval_failed'],before_registers=before['regs'],after_registers=state['regs'],stack_unchanged=True))
try:
 state=send('eval 0 hin 9997 FFFFFF')
 for name,val in [('X',123456),('Y',234567),('Z',345678),('T',456789)]:state=send(f'eval 0 poke {name} {val}')
 evaluate('R5=17',dest=5,value=17)
 evaluate('if r5==17R5=21',dest=5,value=21)
 evaluate('@R5 10 0',dest=5,value=123)
 evaluate('lookup R5 10 0',dest=5,value=123)
 state=send('eval 0 R5= 2');evaluate('@ R5 10 R5',dest=5,value=45)
 state=send('eval 0 RF= 20');evaluate('LOOKUP R6 RF 0 u24',dest=6,value=0x123456)
 state=send('eval 0 R0= 2');state=send('eval 0 R1= 3');evaluate('@ R8 100 R0 R1 7',dest=8,value=171)
 evaluate('@ R8 20 1 1 1 u24',dest=8,value=0x010203)
 evaluate('@ R9 9997 0 u24',dest=9,value=16777215)
 evaluate('@ RA 9999 0',dest=10,value=255)
 evaluate('@ RB 111 0 u24',dest=11,value=0xC3B2A1)
 evaluate('if r4<0 @ R5 10 0')
 for command in ['@ X 10 0','@ R10 10 0','@ R5 -1 0','@ R5 10 -1','@ R5 10 0.1','@ R5 10 0 -1 1','@ R5 10 0 1 -1','@ R5 10000 0','@ R5 9999 0 u24','@ R5 10 10000 10000 10000 u24','@ R5 10','@ R5 10 0 extra','@ R5 10 0 u16','lookupjunk R5 10 0','R5=','R5=oops','R5=1 extra','R10=1','@R5']:
  evaluate(command,True)
 before=state;state=send('eval 2 @ R5 10 0');assert state['eval_failed'] and state['regs']==before['regs'] and state['stack']==before['stack'];rows.append(dict(command='unexpanded: @ R5 10 0',error=True,unchanged=True))
 before=state;state=send('eval 1 R5=17');assert state['eval_failed'] and state['regs']==before['regs'] and state['stack']==before['stack'];rows.append(dict(command='trap: R5=17',error=True,unchanged=True))
 before=state;state=send('eval 1 @ R5 10 0');assert state['eval_failed'] and state['regs']==before['regs'] and state['stack']==before['stack'];rows.append(dict(command='trap: @ R5 10 0',error=True,unchanged=True))
 state=send('block');evaluate('@ R5 10 0',True)
finally:
 p.stdin.close();code=p.wait(timeout=10)
 assert code==0,code
temp.cleanup();print(json.dumps(dict(status='PASS',cases=len(rows),unchanged_other_registers_and_stack=True,device_IO=0)))
