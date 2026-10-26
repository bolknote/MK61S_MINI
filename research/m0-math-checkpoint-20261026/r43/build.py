"""Private R43: explicit carry-contract native Q8 entry; ordinary entry retained."""
from pathlib import Path
import difflib,hashlib,importlib.util,json,shutil,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-pow-rsqrt-seedreuse-r42-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='b5e0bf1e6316a2bc0924127f0b9564c025cb042842f4d3527ce1eef8fd48a676'
assert not(W/'source').exists()
shutil.copytree(P/'source',W/'source');shutil.copytree(P/'timing-control',W/'timing-control')
for n in ['unified.ld','harness.py','verify-private-return.py','verify-guard-controls.py','verify-loader.py','verify-disabled.py','run-controls.py','verify-private-caller.py','verify-normalized-caller.py']:
    shutil.copyfile(P/n,W/n)
before='''mk61_m0_pow_rsqrt_local_q8:
 push {r4-r7,lr}
 mov r4,r0
 ldr r5,[r4,#24]             // seed
 ldr r6,[r4,#20]             // Flow
 ldr r0,[r4,#28]
 asrs r0,r0,#31
 mvns r0,r0
'''
after='''mk61_m0_pow_rsqrt_local_q8:
 push {r4-r7,lr}
 mov r4,r0
 ldr r0,[r4,#28]
 asrs r0,r0,#31
 mvns r0,r0
 b .Lrq8_mask_ready
// Private native entry: incoming C=(Fhigh==0x80000000), established by
// the unique CMP-delta,1/BHI caller guard. PUSH/MOV preserve that C.
// This is NOT the ordinary entry's arbitrary-NZCV contract.
.thumb_func
mk61_m0_pow_rsqrt_local_q8_native:
 push {r4-r7,lr}
 mov r4,r0
 sbcs r0,r0
.Lrq8_mask_ready:
 ldr r5,[r4,#24]             // seed
 ldr r6,[r4,#20]             // Flow
'''
body=(P/'helper.S.inc').read_text();assert body.count(before)==1
newbody=body.replace(before,after).replace('.type mk61_m0_pow_rsqrt_local_q8,%function\n','.type mk61_m0_pow_rsqrt_local_q8,%function\n.global mk61_m0_pow_rsqrt_local_q8_native\n.hidden mk61_m0_pow_rsqrt_local_q8_native\n.type mk61_m0_pow_rsqrt_local_q8_native,%function\n').replace(' ldr r1,=512\n',' movs r1,#128\n lsls r1,r1,#2\n').replace('.size mk61_m0_pow_rsqrt_local_q8,.-mk61_m0_pow_rsqrt_local_q8\n','.size mk61_m0_pow_rsqrt_local_q8,.-mk61_m0_pow_rsqrt_local_q8\n.size mk61_m0_pow_rsqrt_local_q8_native,.-mk61_m0_pow_rsqrt_local_q8_native\n')
assert newbody!=body and newbody.count(' movs r1,#128\n lsls r1,r1,#2\n')==1
(W/'helper.S.inc').write_text(newbody)
p=W/'source/code/native_eabi_m0_pow_fast.inc';old=p.read_text();oldasm='__asm__(R"ASM(\n'+body.replace('//','@')+')ASM");';newasm='__asm__(R"ASM(\n'+newbody.replace('//','@')+')ASM");'
assert old.count(oldasm)==1;new=old.replace(oldasm,newasm);p.write_text(new)
(W/'helper-entry.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='R42/native_eabi_m0_pow_fast.inc',tofile='R43/native_eabi_m0_pow_fast.inc')))
p=W/'source/code/native_eabi_m0_pow_rsqrt.inc';old=p.read_text();assert old.count(' bl mk61_m0_pow_rsqrt_local_q8\n')==1
new=old.replace(' bl mk61_m0_pow_rsqrt_local_q8\n',' // CMP r2,#1 above leaves C=0 for Fhigh7fffffff, C=1 for80000000.\n // BHI, three STR, MOV sp and BL preserve C until the private entry SBC.\n bl mk61_m0_pow_rsqrt_local_q8_native\n');p.write_text(new)
(W/'native-caller.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='R42/native_eabi_m0_pow_rsqrt.inc',tofile='R43/native_eabi_m0_pow_rsqrt.inc')))
spec=importlib.util.spec_from_file_location('r43_fingerprint',ROOT/'research/m0-math-checkpoint-20261025-5/verify.py');fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)
parent=json.loads((P/'link-result.json').read_text());commands=[];outputs={};unchanged=[];changed={};relocation_only=[]
for recorded in parent['commands']:
    command=[v.replace(str(P)+'/',str(W)+'/')for v in recorded];subprocess.run(command,cwd=W,check=True);commands.append(command)
    out=Path(command[command.index('-o')+1]);current=fp.image_fingerprint(out.read_bytes());outputs[out.name]=dict(sha256=sha(out),fingerprint=current)
    if '-c'not in command:continue
    previous=fp.image_fingerprint((P/out.name).read_bytes())
    if out.name=='RP-merged-asm.o':
        assert current['allocated']==previous['allocated']
        expected=[]
        for r in previous['relocations']:expected.append(r[:-1]+['mk61_m0_pow_rsqrt_local_q8_native']if r[-1]=='mk61_m0_pow_rsqrt_local_q8'else r)
        assert current['relocations']==expected and current['relocations']!=previous['relocations']
        strip=lambda a:[r for r in a if r[0]not in ('mk61_m0_pow_rsqrt_local_q8','mk61_m0_pow_rsqrt_local_q8_native')]
        assert strip(current['symbols'])==strip(previous['symbols']);relocation_only.append(out.name);continue
    if out.name!='RP-merged-cpp.o':assert current==previous,out.name;unchanged.append(out.name);continue
    a,b=[{r[0]:r for r in v['allocated']}for v in [current,previous]];diff=[n for n in sorted(a.keys()|b.keys())if a.get(n)!=b.get(n)];assert diff==['.m0_rsqrt_local_q8'],diff
    assert[r for r in current['symbols']if r[-1]not in diff]==[r for r in previous['symbols']if r[-1]not in diff]
    assert[r for r in current['relocations']if r[0]not in diff]==[r for r in previous['relocations']if r[0]not in diff];changed[out.name]=diff
assert len(unchanged)==17 and relocation_only==['RP-merged-asm.o']and changed=={'RP-merged-cpp.o':['.m0_rsqrt_local_q8']}
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
tc=Path(commands[0][0]).parent;images={}
for label in ['candidate','zero-control']:
    p=W/(label+'.elf');e=ElfImage(p);assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(p)])
    assert e.named_sections['.scratch_y'][5]==4080 and e.sizes['mk61_m0_div_seed_table']==256 and e.sizes['mk61_m0_public_div_seed8_table']==32
    images[label]=dict(ELF_sha256=sha(p),scratch_y_bytes=4080,all_undefined_symbols_resolved=True)
    with(W/(label+'.dis')).open('w')as f:subprocess.run([str(tc/'arm-none-eabi-objdump'),'-dr',str(p)],stdout=f,check=True)
result=dict(status='BUILT_R43_PRIVATE_NATIVE_CARRY_ENTRY_PENDING_PROOF_TESTS',images=images,commands=commands,outputs=outputs,parent_source_FROZEN_sha256=sha(P/'FROZEN.json'),unchanged_objects=unchanged,relocation_only_objects=relocation_only,changed_allocated_sections=changed,all17_other_objects_M4default_exact=True,default_M0_M4_objects_exact=True,RPASM_allocated_bytes_exact_and_unique_helper_relocation_changed=True,new_lookup_tables_RAM_libgcc_bytes=0,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'link-result.json').write_text(json.dumps(result,indent=2)+'\n');print('R43 built',images['candidate'],'changed',changed,'reloconly',relocation_only,'unchanged',len(unchanged),flush=True)
