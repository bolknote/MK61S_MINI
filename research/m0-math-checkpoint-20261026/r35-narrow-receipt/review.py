"""Static/saved-record R35 delta audit. No producer import or target execution."""
from pathlib import Path
from collections import Counter
import ast,gzip,hashlib,json,re,struct
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
S=R/'.build/m0-math-unified-exp-row0-reuse-r35-20261026'
Q=R/'.build/m0-math-unified-exp-row0-reuse-r35-qualification-20261026'
P=R/'.build/m0-math-unified-exp-positive-bridge-r33-20261026'
PQ=R/'.build/m0-math-unified-exp-positive-bridge-r33-qualification-20261026'
RQ=R/'.build/m0-math-unified-exp-bit62-r29-qualification-20261026'
M=R/'.build/m0-exp-row0-cold-shortcut-study-20261026'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_bytes())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
def seal(d,pin):
 assert sha(d/'FROZEN.json')==pin
 f=read(d/'FROZEN.json')
 for n,x in f['files'].items():
  p=d/n;assert p.is_file()and p.stat().st_size==x['bytes']and sha(p)==x['sha256'],p
 return len(f['files'])
pins=dict(source='545ce93e947599e5a1345e04c45aab8b979aa2f4d72dc9b11ed9437c12eb3a98',
 qualification='df92a59684a5c83363d598859797d03de312c001b6713a45c468c2ee5cf99258',
 author='6570b1a6a063a2adb06ff6f7db4ccd4129e4ec1ba40a56c6ba8bc06ac3aaaa2d',
 parent_review='cb914841a63f96fc90f3833b3f522e54ef4b5fcf5694d3bc66a78beb31fddea1',
 parent_source='ebdf17a90f34a7d2e5e7d49ac8fd49de47442f1509459bb10b3eb22633b89dd1',
 parent_qualification='6cc6994839b641b9496508dcf0181918089835a8327b3f71862ee5cd759c9fde',
 model='20a11b8f73f5173bd2963a961a09474260fc52709a9adf4f6e3d8deb6f63f413',
 ELF='af140ef43618ed582d01b5bfa67ee649f55e1b361580423e54a7fbaf286279be')
seals=dict(source=seal(S,pins['source']),qualification=seal(Q,pins['qualification']),model=seal(M,pins['model']))
assert sha(P/'FROZEN.json')==pins['parent_source']and sha(PQ/'FROZEN.json')==pins['parent_qualification']
assert sha(Q/'author-result.json')==pins['author']and sha(S/'candidate.elf')==pins['ELF']
assert sha(R/'.build/m0-math-unified-exp-positive-bridge-r33-independent-20261026/FINAL-REVIEW.json')==pins['parent_review']
assert sha(RQ/'FROZEN.json')=='c1629034ff342e7f7da22d246d360e4548506500a99450d42772107bea4012c5'
env=dict(Path=Path,hashlib=hashlib,struct=struct)
def defs(p,names):
 t=ast.parse((R/p).read_text());nodes=[x for x in t.body if isinstance(x,(ast.ClassDef,ast.FunctionDef))and x.name in names]
 assert len(nodes)==len(names);exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),env)
defs(Path('.build/m0-math-unified-pow-zero-r9-independent-20261025/audit.py'),{'ELF'})
defs(Path('.build/m0-math-unified-ln-isolated-r14-independent-20261025/review_r14.py'),{'relocs'})
defs(Path('.build/m0-math-unified-pow-rsqrt-upper4-r24-independent-20261026/audit.py'),{'at','bl','flash'})
ELF,relocs,at,bl,flash=[env[n]for n in ['ELF','relocs','at','bl','flash']]
e,ep=ELF(S/'candidate.elf'),ELF(P/'candidate.elf');o,op=ELF(S/'RP-merged-cpp.o'),ELF(P/'RP-merged-cpp.o')
sn={n[7:]for n in read(S/'FROZEN.json')['files']if n.startswith('source/')}
assert sn=={n[7:]for n in read(P/'FROZEN.json')['files']if n.startswith('source/')}
changed=[n for n in sorted(sn)if sha(S/'source'/n)!=sha(P/'source'/n)]
assert changed==['code/native_eabi_m0.cpp']
parts={a.targets[0].id:ast.literal_eval(a.value)for a in ast.parse((S/'build.py').read_text()).body
 if isinstance(a,ast.Assign)and len(a.targets)==1 and isinstance(a.targets[0],ast.Name)and a.targets[0].id in ['before','after','phase','row0','newrow']}
assert set(parts)=={'before','after','phase','row0','newrow'}
oldsrc=(P/'source/code/native_eabi_m0.cpp').read_text()
for k in ['before','phase','row0']:assert oldsrc.count(parts[k])==1
assert oldsrc.replace(parts['before'],parts['after']).replace(parts['phase'],' mov r3,r12').replace(parts['row0'],parts['newrow'])==(S/'source/code/native_eabi_m0.cpp').read_text()
link=read(S/'link-result.json');oldlink=read(P/'link-result.json');assert len(link['unchanged_objects'])==18
assert [[a.replace(str(S)+'/',str(P)+'/')for a in argv]for argv in link['commands']]==oldlink['commands']
for n in link['unchanged_objects']:
 a,b=ELF(S/n),ELF(P/n);assert a.alloc()==b.alloc()and a.symbols_fp()==b.symbols_fp()and relocs(a)==relocs(b),n
sec='.m0_exp_positive_dispatch'
assert [x for x in o.alloc()if x[0]!=sec]==[x for x in op.alloc()if x[0]!=sec]
assert [x for x in o.symbols_fp()if x[-1]!=sec]==[x for x in op.symbols_fp()if x[-1]!=sec]
assert [x for x in relocs(o)if x[0]!=sec]==[x for x in relocs(op)if x[0]!=sec]
assert len(o.sections[sec]['data'])==140 and len(op.sections[sec]['data'])==104
assert len(o.sections['.m0_exp_core']['data'])==5192 and o.sections['.m0_exp_core']['data']==op.sections['.m0_exp_core']['data']
assert len(o.sections['.m0_exp_positive_upper']['data'])==108 and o.sections['.m0_exp_positive_upper']['data']==op.sections['.m0_exp_positive_upper']['data']
def bind(section,symbol):
 raw=bytearray(o.sections[section]['data']);base=(e.symbols[symbol]['value']&~1)-(o.symbols[symbol]['value']&~1);linked=bytearray(at(e,base,len(raw)));resolved=[]
 for sn,off,typ,target,value in relocs(o):
  if sn!=section:continue
  name=target.removeprefix('.rodata.');v=e.symbols[name]['value']
  if typ==2:assert struct.unpack_from('<I',linked,off)[0]==(v+struct.unpack_from('<I',raw,off)[0])&0xffffffff
  else:
   assert typ==10;got=bl(e,base+off)
   if got!=v&~1:
    b=at(e,got,16);assert b[:12].hex()=='01b40248844601bc604700bf'and struct.unpack_from('<I',b,12)[0]==v
  raw[off:off+4]=linked[off:off+4]=b'\0'*4;resolved.append([off,typ,name])
 assert raw==linked
 return dict(section=section,address=hex(base),bytes=len(raw),resolved=resolved)
bindings=[bind('.m0_exp_core','mk61_m0_exp'),bind('.m0_exp_positive_upper','mk61_m0_exp_positive_upper'),bind(sec,'mk61_m0_exp_positive_dispatch')]
assert flash(e)-flash(ep)==40
assert sorted(n for n in e.symbols if n.startswith('__aeabi'))==sorted(n for n in ep.symbols if n.startswith('__aeabi'))
assert [(s['name'],s['size'],s['data'])for s in e.ss if s['flags']&2 and s['address']>=0x20000000 and s['name']!='.scratch_y']==[(s['name'],s['size'],s['data'])for s in ep.ss if s['flags']&2 and s['address']>=0x20000000 and s['name']!='.scratch_y']
def instructions(d,x,name):
 a=x.symbols[name]['value']&~1;z=a+x.symbols[name]['size'];result={}
 for line in(d/'candidate.dis').read_text().splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)([a-z][a-z0-9.]*)\s*(.*)',line)
  if not m or not a<=int(m[1],16)<z:continue
  loc=int(m[1],16);b=b''.join(struct.pack('<H',int(h,16))for h in m[2].split());assert at(x,loc,len(b))==b
  result[loc]=dict(op=m[3].split('.')[0],args=m[4].split('@')[0].strip(),bytes=len(b))
 return result
bs=e.symbols['mk61_m0_exp_positive_dispatch']['value']&~1;bc=instructions(S,e,'mk61_m0_exp_positive_dispatch')
pair=lambda a:(bc[a]['op'],bc[a]['args'])
assert pair(bs)==('cmp','r1, #0')and bc[bs+2]['op']=='bmi'and pair(bs+4)==('lsls','r3, r2, #23')and bc[bs+6]['op']=='beq'
row=int(bc[bs+6]['args'].split()[0],16);slow=int(bc[row+4]['args'].split()[0],16)
expected=[('ldr','r3, [sp, #28]'),('lsrs','r3, r3, #21'),None,('lsls','r3, r6, #22'),None,('mov','r0, r6'),('mov','r1, r7'),('lsrs','r0, r0, #10'),('lsls','r3, r1, #22'),('orrs','r0, r3'),('lsrs','r1, r1, #10'),('ldr','r3, [sp, #8]'),None,('adds','r3, r3, r2'),('lsls','r3, r3, #20'),('adds','r1, r1, r3'),('bx','lr')]
for i,x in enumerate(expected):
 if x is not None:assert pair(row+2*i)==x
assert bc[row+4]['op']=='bne'and bc[row+8]['op']=='bmi'and int(bc[row+8]['args'].split()[0],16)==slow
assert bc[row+24]['op']=='ldr';m=re.fullmatch(r'r2, \[pc, #(\d+)\]',bc[row+24]['args']);assert m
literal=((row+24+4)&~3)+int(m[1]);assert struct.unpack('<I',at(e,literal,4))[0]==1022
assert [pair(slow+i)for i in [0,2,4]]==[('movs','r3, #128'),('lsls','r3, r3, #23'),('mov','ip, r3')]
assert bc[slow+6]['op']=='b'and int(bc[slow+6]['args'].split()[0],16)==bs+8
fast=[bs+i for i in [0,2,4,6]]+[row+i for i in range(0,34,2)];assert len(fast)==21
for a in fast:
 opx,args=pair(a);assert opx not in ['bl','blx','str','strb','strh','push','pop']
 if opx not in ['cmp','beq','bne','bmi','bx']:assert not re.match(r'(sp|r[4-9]|ip|r1[012])\b',args)
assert sum(v['op']=='bl'for v in bc.values())==1
core=instructions(S,e,'mk61_m0_exp');oldcore=instructions(P,ep,'mk61_m0_exp')
cs=e.symbols['mk61_m0_exp']['value']&~1;ps=ep.symbols['mk61_m0_exp']['value']&~1
assert len(core)==len(oldcore)
conditional={'beq','bne','bcs','bcc','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble'}
for (a,u),(b,v)in zip(sorted(core.items()),sorted(oldcore.items()),strict=True):
 assert a-cs==b-ps and u['op']==v['op']and u['bytes']==v['bytes']
 if u['op']in conditional|{'b'}:
  assert int(u['args'].split()[0],16)-cs==int(v['args'].split()[0],16)-ps
 elif u['op']not in ['bl']and not(u['op']=='ldr'and'[pc,'in u['args']):assert u['args']==v['args']
marker=e.symbols['mk61_m0_exp_fraction_capture']['value']&~1
call=[a for a,v in core.items()if v['op']=='bl'and int(v['args'].split()[0],16)==bs];assert len(call)==1
assert [(core[call[0]-i]['op'],core[call[0]-i]['args'])for i in [6,4,2]]==[('ldr','r2, [sp, #32]'),('ldr','r0, [sp, #0]'),('ldr','r1, [sp, #4]')]
guard=read(S/'private-caller-proof.json');assert guard['candidate_ELF_sha256']==pins['ELF']and guard['eligible_live_instructions']==86
assert guard['current_unique_bridge_call']==hex(call[0])and guard['capture_marker']==hex(marker)
# No new theorem: prove this stricter row0 subset implies the already accepted R33 decision.
Dmax=(1<<53)-1;Pmax=(Dmax+2)>>2;head=((1<<62)+Pmax)>>48;g=((1<<21)-1+1024)>>10
curve=(3*g*g+65535)>>16;D8=513+curve;effect=(D8*(head+1)+65535)>>16;upper=effect+66+2
assert (Pmax,head,g,curve,D8,effect,upper)==(1<<51,16392,2048,192,705,177,245)
assert upper<256 and [t for t in range(509,516)if not t&512]==[509,510,511]
for fragment,size,first in [('exp_table',4096,1<<62),('refine_exp_table',6144,1<<94)]:
 sy=next(s for s in e.syms if fragment in s['name']and s['size']==size);data=at(e,sy['value'],size)
 assert data==at(ep,ep.symbols[sy['name']]['value'],size)
 assert int.from_bytes(data[:8 if size==4096 else 12],'little')==first
bank=read(S/'bank-map.json');ba=bank['bank_address'];before,after=at(ep,ba,4080),at(e,ba,4080);diff={i for i,(a,b)in enumerate(zip(before,after))if a!=b};assert len(diff)==5
covered=set()
for v in bank['veneer_mapping']:
 for x,label in [(ep,'old'),(e,'new')]:
  t=v[label];b=at(x,t['entry'],16);assert b[:12].hex()=='01b40248844601bc604700bf'and struct.unpack_from('<I',b,12)[0]==x.symbols[v['target_symbol']]['value']==t['literal_target']
  covered.update(range(t['entry']-ba,t['entry']-ba+16))
for v in bank['all_BL_calls_to_veneer_mapping']:
 for x,label in [(ep,'old'),(e,'new')]:assert bl(x,v['callsite'])==v[label]['veneer']
 assert before[v['callsite']-ba:v['callsite']-ba+4]==after[v['callsite']-ba:v['callsite']-ba+4]
for v in bank['relocated_pointer_fields']:
 off=v['offset'];n=v['target_symbol'];assert struct.unpack_from('<I',before,off)[0]==ep.symbols[n]['value']and struct.unpack_from('<I',after,off)[0]==e.symbols[n]['value'];covered.update(range(off,off+4))
assert diff<=covered
for v in bank['unchanged_target_origin_evidence']:
 n=v['symbol']
 if n in o.symbols:
  sn=o.ss[o.symbols[n]['index']]['name'];assert o.body(n)==op.body(n)and[x for x in relocs(o)if x[0]==sn]==[x for x in relocs(op)if x[0]==sn]
 else:assert any(n in ELF(S/f).symbols and ELF(S/f).body(n)==ELF(P/f).body(n)for f in link['unchanged_objects'])
control=read(S/'bridge-control-result.json');assert control['candidate_ELF_sha256']==pins['ELF']
assert 512*7*2+4*4*5*2==control['input_cases']==7328
assert control['actual_threeSIO_control_ARM_calls']==7328*3==21984
assert control['actual_selected16NZCV_ARM_calls']==29*16*3==1392
assert control['actual_qualified_control_ARM_calls']==23376
assert sha(S/'bridge-control-fixture.elf')==control['fixture_ELF_sha256']
for n in ['verify-private-return.py','verify-guard-controls.py','verify-loader.py','verify-disabled.py','verify-private-caller.py']:
 assert (S/n).read_bytes()==(P/n).read_bytes()
for n in ['private-return-proof.json','private-guard-controls.json']:
 x=read(S/n);assert x['candidate_ELF_sha256']==pins['ELF']and x['actual_fresh_disassembly_sha256']==sha(S/'candidate.dis')
save('STATIC.json',dict(status='PASS',pins=pins,seal_counts=seals,source_file_count=len(sn),changed_source=changed,
 source_delta_inverse_exact=True,other18_objects_exact=True,old_core5192_helper108_exact_object=True,
 only_changed_allocated_section=sec,bridge_bytes=140,parent_bridge_bytes=104,code_delta=36,
 linked_flash_bytes=flash(e),parent_linked_flash_bytes=flash(ep),linked_flash_delta=40,
 no_new_table_RAM_libgcc=True,bank_bytes=4080,bank_changed_bytes=5,all_bank_changes_symbolic=True,
 bindings=bindings,actual_callsite=hex(call[0]),marker=hex(marker),same_private_86node_CFG_from_exact_object_and_current_disassembly=True,
 leaf_address=hex(row),fast_instructions=21,no_calls_stack_R12_or_callee_saved_write=True,
 row0_decline_sets_caller_clobbered_R12_constant=True,nonzero_general_path_keeps_original_R12=True,
 proof=dict(Dmax=Dmax,Pmax=Pmax,qhead_max=head,gmax=g,curvature_max=curve,D8max=D8,effect_max=effect,U8max=upper,minimum_midpoint_Q8=256,tail_domain=[509,510,511]),
 caller_and_theorem_inherited_R33_not_portable_generic_ABI=True,control_calls=23376,control_stubs_not_numerical_gold=True,new_ARM_MPFR_builds=0))

def records(p):
 with gzip.open(p,'rt')as f:
  for s in f:yield json.loads(s)
def exact_parent_record(r,p,phase):
 if phase=='full':
  assert r['operation']==p['operation']and r['index']==p['index']
  fields=['expected_inherited_directed_MPFR','inherited_Qfplib_output','inherited_Qfplib_instructions','inherited_Qfplib_correct']
  for k in fields:assert r[k]==p[k]
  po,pc=p['candidate_output'],p['candidate_instructions']
 else:
  assert r['expected_inherited_directed_MPFR']==p['expected']
  assert r['inherited_Qfplib_output']==p['outputs']['Qfplib']and r['inherited_Qfplib_instructions']==p['instructions']['Qfplib']and r['inherited_Qfplib_correct']==p['correct']['Qfplib']
  po,pc=p['outputs']['candidate'],p['instructions']['candidate']
 for k in ['x','group','SIO']:assert r[k]==p[k]
 assert r['candidate_output']==r['inherited_R33_output']==po and r['inherited_R33_instructions']==pc
 return pc
details={};oldxs=set();xs=set();pl=set();cl=set();overlap={};tie=[];fullR29=Counter();fullR29sum=0
boundary_targets=set(read(PQ/'boundary-inputs.json')['groups'])
for phase,parentname in [('full','exp-records.jsonl.gz'),('boundary','boundary-records.jsonl.gz')]:
 hist=Counter();routes=Counter();plocal=set();clocal=set();incpart=Counter();wrong=0;count=0;overlap_rows=0;cum=Counter();cumsum=0
 assert sha(PQ/parentname)==read(PQ/'FROZEN.json')['files'][parentname]['sha256']
 stream=zip(records(Q/(phase+'-records.jsonl.gz')),records(PQ/parentname),strict=True)
 r29stream=records(RQ/'exp-records.jsonl.gz')if phase=='full'else None
 cumstream=records(Q/'cumulative-R29-full-records.jsonl.gz')if phase=='full'else None
 for r,p in stream:
  count+=1;pc=exact_parent_record(r,p,phase);cc=r['candidate_instructions'];d=cc-pc;hist[d]+=1;routes[r['actual_bridge_route']]+=1;x=r['x'];xs.add(x)
  if phase=='full':
   oldxs.add(x)
   # Retain compact overlap record only; boundary target set is saved separately.
   if x in boundary_targets:overlap[x,r['SIO']]=r
   a=next(r29stream);z=next(cumstream)
   assert a['x']==x and a['SIO']==r['SIO']and a['candidate_output']==r['candidate_output']
   assert a['inherited_Qfplib_output']==r['inherited_Qfplib_output']and a['inherited_Qfplib_instructions']==r['inherited_Qfplib_instructions']and a['inherited_Qfplib_correct']==r['inherited_Qfplib_correct']
   rc=a['candidate_instructions'];change=cc-rc;cum[change]+=1;cumsum+=change
   assert z==dict(operation='exp',x=x,y=None,SIO=r['SIO'],R29=rc,R35=cc,delta=change,references=dict(instructions=r['inherited_Qfplib_instructions'],correct=r['inherited_Qfplib_correct']))
  elif x in oldxs and r['SIO']in ['READY','DIRTY']:
   a=overlap[x,r['SIO']];overlap_rows+=1
   for k in ['candidate_output','candidate_instructions','inherited_R33_output','inherited_R33_instructions','inherited_Qfplib_output','inherited_Qfplib_instructions','inherited_Qfplib_correct']:assert a[k]==r[k]
  if x=='3FD2D8152348013D':tie.append(dict(phase=phase,SIO=r['SIO'],candidate=cc,Qfp=r['inherited_Qfplib_instructions'],parent=pc))
  if d>0:incpart['wrong_reference'if not r['inherited_Qfplib_correct']else'parent_already_slower'if pc>r['inherited_Qfplib_instructions']else'parent_not_slower']+=1
  if not r['inherited_Qfplib_correct']:wrong+=1;continue
  ref=r['inherited_Qfplib_instructions']
  if pc>ref:plocal.add(x);pl.add(x)
  if cc>ref:clocal.add(x);cl.add(x)
 if phase=='full':
  assert next(r29stream,None)is None and next(cumstream,None)is None
  assert len(oldxs)==494961 and len(plocal)==401 and len(clocal)==377
  assert cumsum==222314 and sum(v for k,v in cum.items()if k>0)==166432 and sum(v for k,v in cum.items()if k<0)==564 and cum[0]==822926
  fullR29=cum;fullR29sum=cumsum
 else:assert len(plocal)==584 and len(clocal)==559 and overlap_rows==15568
 assert not clocal-plocal and not cl-pl
 result=read(Q/(phase+'-result.json'))
 assert count==result['state_rows']and dict(hist)=={int(k):v for k,v in result['instruction_delta_histogram'].items()}
 assert sum(incpart.values())==len(result['all_parent_increases'])and wrong==result['wrong_inherited_Qfplib_rows_retained']
 details[phase]=dict(rows=count,parent_losses=len(plocal),candidate_losses=len(clocal),fixed=len(plocal-clocal),new_losses=0,wrong_Qfp_rows=wrong,
   delta_histogram=dict(sorted(hist.items())),net_parent_instruction_delta=sum(k*v for k,v in hist.items()),increase_partition=dict(incpart),routes=dict(routes),overlap_rows=overlap_rows)
assert len(xs)==546161 and len(pl)==584 and len(cl)==559
assert all(t['candidate']==t['Qfp']==t['parent']==642 for t in tie)and len(tie)==5
assert details['full']['rows']==989922 and details['boundary']['rows']==176952
primary={}
for name in ['original507','broad']:
 hist=Counter();count=0;net=0
 astream=records(RQ/(name+'-records.jsonl.gz'));cstream=records(Q/('cumulative-R29-'+name+'-records.jsonl.gz'))
 for a,p in zip(records(Q/(name+'-records.jsonl.gz')),records(PQ/(name+'-records.jsonl.gz')),strict=True):
  assert a==p;count+=1;r=next(astream);c=next(cstream)
  for k in ['operation','x','SIO']:assert r[k]==a[k]
  assert r['outputs']==a['outputs']and r['correct']==a['correct']
  rc,cc=r['instructions']['candidate'],a['instructions']['candidate'];d=cc-rc;hist[d]+=1;net+=d
  refs={k:dict(instructions=v,correct=a['correct'][k])for k,v in a['instructions'].items()if k not in ['candidate','zero-control']}
  assert c==dict(operation=a['operation'],x=a['x'],y=a.get('y'),SIO=a['SIO'],R29=rc,R35=cc,delta=d,references=refs)
 assert next(astream,None)is None and next(cstream,None)is None
 primary[name]=dict(rows=count,net_vs_R29=net,increases_vs_R29=sum(v for k,v in hist.items()if k>0),histogram=dict(sorted(hist.items())),all_current_records_exact_R33=True,ARM=read(Q/(name+'.json'))['actual_qualified_math_ARM_calls'])
assert primary['original507']['increases_vs_R29']==18 and primary['broad']['increases_vs_R29']==2080
assert sum(v['ARM']for v in primary.values())==196714
boundary=read(Q/'boundary-result.json');assert boundary['actual_fresh_public_index0_poison16NZCV_calls']==37*3*5*16==8880
public=989922+176952+8880+196714;assert public==1372468 and public+23376==1395844
save('COUNTS.json',dict(status='PASS_FROZEN_RECORDS_ONLY',per_campaign=details,
 union=dict(inputs=546161,parent_losses=584,candidate_losses=559,fixed=25,new_losses=0,new_inputs_this_round=0),
 exact_tie642_retained=tie,primary=primary,
 cumulative_R29_full=dict(rows=989922,net=fullR29sum,increased=166432,decreased=564,same=822926,histogram=dict(sorted(fullR29.items())),all_saved_cumulative_rows_independently_matched=True),
 new51200_inputs_have_no_R29_baseline=True,primary_2098_R30_regressions_retained=True,
 fresh_author_ARM=dict(full_candidate=989922,boundary_candidate=176952,boundary_poison=8880,primary=196714,public=public,bridge_marker_controls=23376,total=1395844),
 full_boundary_fresh_MPFR_Qfp_parent=0,inherited_real_helper_ARM_not_fresh=921901,
 diagnostic_ARM=70056,diagnostic_MPFR=7784,failed_syntax_ARM_MPFR=0,loader_ARM=2,not_pooled=True,
 finite_losses=dict(ln_inherited=0,pow_inherited=2501,exp_current=559,total=3060),new_numeric_runs_in_review=0))
print(json.dumps(dict(status='PASS',seals=seals,ELF=pins['ELF'],common_R29_net=fullR29sum,union_losses=559),indent=2))
