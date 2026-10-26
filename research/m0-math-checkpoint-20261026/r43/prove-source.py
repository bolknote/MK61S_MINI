"""R43 full source/ISA binding, separate ordinary/native contracts and paired paths."""
from pathlib import Path
import ast,hashlib,importlib.util,json,re,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-pow-rsqrt-seedreuse-r42-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_bytes())
assert not(W/'source-binding-proof.json').exists()
assert sha(P/'FROZEN.json')=='b5e0bf1e6316a2bc0924127f0b9564c025cb042842f4d3527ce1eef8fd48a676'
for n,pin in read(P/'FROZEN.json')['files'].items():assert(P/n).stat().st_size==pin['bytes']and sha(P/n)==pin['sha256'],n
parts={}
for n in ast.parse((W/'build.py').read_text()).body:
    if isinstance(n,ast.Assign)and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)and n.targets[0].id in('before','after'):parts[n.targets[0].id]=ast.literal_eval(n.value)
old=(P/'helper.S.inc').read_text();new=(W/'helper.S.inc').read_text();rev=new.replace(parts['after'],parts['before']).replace('.global mk61_m0_pow_rsqrt_local_q8_native\n.hidden mk61_m0_pow_rsqrt_local_q8_native\n.type mk61_m0_pow_rsqrt_local_q8_native,%function\n','').replace(' movs r1,#128\n lsls r1,r1,#2\n',' ldr r1,=512\n').replace('.size mk61_m0_pow_rsqrt_local_q8_native,.-mk61_m0_pow_rsqrt_local_q8_native\n','');assert rev==old
src='source/code/native_eabi_m0_pow_fast.inc';a,b=(P/src).read_text(),(W/src).read_text();assert b==a.replace('__asm__(R"ASM(\n'+old.replace('//','@')+')ASM");','__asm__(R"ASM(\n'+new.replace('//','@')+')ASM");')
src='source/code/native_eabi_m0_pow_rsqrt.inc';a,b=(P/src).read_text(),(W/src).read_text();assert b==a.replace(' bl mk61_m0_pow_rsqrt_local_q8\n',' // CMP r2,#1 above leaves C=0 for Fhigh7fffffff, C=1 for80000000.\n // BHI, three STR, MOV sp and BL preserve C until the private entry SBC.\n bl mk61_m0_pow_rsqrt_local_q8_native\n')
changed=[str(p.relative_to(P/'source'))for p in(P/'source').rglob('*')if p.is_file()and sha(p)!=sha(W/'source'/p.relative_to(P/'source'))];assert changed==['code/native_eabi_m0_pow_fast.inc','code/native_eabi_m0_pow_rsqrt.inc']or set(changed)=={'code/native_eabi_m0_pow_fast.inc','code/native_eabi_m0_pow_rsqrt.inc'}
link=read(W/'link-result.json');assert link['changed_allocated_sections']=={'RP-merged-cpp.o':['.m0_rsqrt_local_q8']}and link['relocation_only_objects']==['RP-merged-asm.o']and len(link['unchanged_objects'])==17
spec=importlib.util.spec_from_file_location('r43_fingerprint',ROOT/'research/m0-math-checkpoint-20261025-5/verify.py');fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)
for n,row in link['outputs'].items():assert sha(W/n)==row['sha256']and fp.image_fingerprint((W/n).read_bytes())==row['fingerprint']
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
images={n:ElfImage(p/'candidate.elf')for n,p in [('parent',P),('candidate',W)]}
parsefn=next(n for n in ast.parse((W/'verify-private-return.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse');env={'re':re};exec(compile(ast.Module(body=[parsefn],type_ignores=[]),'parser','exec'),env)
def norm(s):
    s=s.replace('ip','r12').replace('r14','lr').replace('r15','pc');s=re.sub(r'r(\d+)-r(\d+)',lambda m:','.join('r'+str(i)for i in range(int(m[1]),int(m[2])+1)),s);return re.sub(r'\s+','',s)
def bind(p,e):
    entry=e.symbols['mk61_m0_pow_rsqrt_local_q8']&~1;code=env['parse']((p/'candidate.dis').read_text());lines=[];labels={}
    for line in(p/'helper.S.inc').read_text().splitlines():
        line=line.split('//',1)[0].strip()
        if not line:continue
        if line.endswith(':'):labels[line[:-1]]=entry+2*len(lines)
        elif not line.startswith('.'):lines.append(line)
    for i,line in enumerate(lines):
        a=entry+2*i;r=code[a];op,args=line.split(None,1);assert r['bytes']==2 and r['mnemonic']==op,(line,r)
        if op.startswith('b'):assert int(r['operands'].split()[0],16)==labels[args],(line,r)
        elif ',='in args:
            reg,value=args.split(',=');assert r['operands'].startswith(reg+', [pc,');m=re.search(r'\[pc, #(\d+)\]',r['operands']);assert m;ptr=((a+4)&~3)+int(m[1]);sec=next(s for s in e.named_sections.values()if s[3]<=ptr and ptr+4<=s[3]+s[5]);assert struct.unpack_from('<I',e.bytes_at(sec),ptr-sec[3])[0]==int(value)
        else:assert norm(r['operands'])==norm(args),(line,r)
    assert not any(line.split()[0]in('bl','blx','bx','str','strb','strh')for line in lines)
    return dict(entry=entry,labels=labels,lines=lines,code=code)
bound={n:bind(p,images[n])for n,p in [('parent',P),('candidate',W)]}
assert bound['candidate']['labels']['mk61_m0_pow_rsqrt_local_q8_native']==(images['candidate'].symbols['mk61_m0_pow_rsqrt_local_q8_native']&~1)
assert not any(',=512'in s for s in bound['candidate']['lines'])and len([s for s in bound['candidate']['lines']if',=65535'in s])==1
conds={'beq','bne','bcc','bcs','bhi','bls','bpl','bmi','bge','blt','bgt','ble','bhs','blo','bvc','bvs'}
def paths(b,start):
    code=b['code'];condition_ids={b['entry']+2*i:j for j,(i,line)in enumerate((i,line)for i,line in enumerate(b['lines'])if line.split()[0]in conds)};todo=[(start,[],[])];out={}
    while todo:
        a,trace,dec=todo.pop();assert a not in trace;trace=trace+[a];r=code[a];op=r['mnemonic'];args=r['operands']
        if op=='pop'and'pc'in args:
            route='down'if b['labels']['.Lrq8_down']in trace else'up'if b['labels']['.Lrq8_up']in trace else'decline';key=(tuple(dec),route);assert key not in out;out[key]=trace;continue
        if op=='b':todo.append((int(args.split()[0],16),trace,dec))
        elif op in conds:
            for take,dst in[(True,int(args.split()[0],16)),(False,a+2)]:todo.append((dst,trace,dec+[(condition_ids[a],take)]))
        else:todo.append((a+2,trace,dec))
    return out
parentpaths=paths(bound['parent'],bound['parent']['entry']);paired=[]
for mode,start in [('generic',bound['candidate']['entry']),('native',bound['candidate']['labels']['mk61_m0_pow_rsqrt_local_q8_native'])]:
    current=paths(bound['candidate'],start);assert set(parentpaths)==set(current)
    for key,trace in parentpaths.items():
        newtrace=current[key];delta=len(newtrace)-len(trace);assert delta==(2 if mode=='generic'else-1)
        paired.append(dict(mode=mode,conditional_decisions=key[0],route=key[1],parent=trace,candidate=newtrace,parent_instructions=len(trace),candidate_instructions=len(newtrace),delta=delta))
(W/'paired-helper-CFG-cases.json').write_text(json.dumps(paired,indent=2)+'\n')
guard=read(W/'native-caller-proof.json');unit=read(W/'helper-unit-result.json');probe=read(W/'probe-result.json');bank=read(W/'bank-map.json')
assert len(guard['negative_controls_rejected'])==12 and guard['all_native_calls_guarded_unique']and guard['ordinary_entry_never_uses_incoming_flags']
assert unit['candidate_wrong']==0 and unit['generic_instruction_delta_histogram']=={'2':143384}and unit['native_fixture_instruction_delta_histogram']=={'-1':143384}and unit['actual_qualified_control_ARM_calls']==573536 and unit['explicit_carry_up_rows']==180
assert probe['candidate_wrong']==0 and not probe['new_correct_reference_loss_rows']and not probe['all_parent_instruction_increase_rows']and probe['all_actual_native_q_and_live_frame_and_Bh_R5_exact_parent']and probe['actual_private_C_contract_asserted_every_Q8_call']
assert(W/'controls.log').read_text().strip().splitlines()==['verify-private-return PASS','verify-guard-controls PASS','verify-loader PASS','verify-disabled PASS']
assert bank['all_changed_bytes_explained']and bank['changed_bytes']==13
flash=lambda e:sum(s[4]for s in e.segments if s[0]==1 and 0x10010000<=s[3]<0x10200000)
delta=flash(images['candidate'])-flash(images['parent']);helper=images['candidate'].sizes['mk61_m0_pow_rsqrt_local_q8'];native=images['candidate'].sizes['mk61_m0_pow_rsqrt_local_q8_native']
assert helper==232 and native==220 and delta==8
result=dict(status='PASS_R43_BOTH_ENTRY_CONTRACTS_FULL_SOURCE_ISA_AND_UNPRUNED_PAIRED_PATHS',candidate_ELF_sha256=sha(W/'candidate.elf'),parent_source_FROZEN_sha256=sha(P/'FROZEN.json'),source_edits_reversed_exactly_to_R42=True,only_RP_Q8_helper_allocated_section_changed=True,RPASM_allocated_bytes_exact_unique_BL_relocation_changed=True,other17_objects_M4default_exact=True,all_source_helper_instructions_branches_literals_bound=True,
    native_C_contract_proved_from_actual_unique_guard_and_unchanged_flag_chain=True,native_contract_requires_C_equal_Fhi_bit31=True,ordinary_entry_keeps_arbitrary_incoming_NZCV=True,separate_entry_preconditions_not_silently_applied_to_C_ABI=True,exact_mask_equivalence_2case_integer_truth=guard['integer_truth'],integer_formula_and_every_rounding_predicate_equal_R42=True,all_native_branch_paths_save1instruction=True,all_generic_branch_paths_add2instructions_retained=True,unpruned_paths_each_entry=len(parentpaths),paired_paths=len(paired),no_seed_domain_pruning_needed=True,
    no_new_calls_inside_helper=True,ordinary_APCS_R4_R11_SP_and_frame_readonly=True,full64_pack_carry_preserved=True,code_bytes_parent224_current232=True,native_entry_symbol_bytes220=True,code_Flash_delta_bytes=8,target512_literal_removed_replaced_by2ALU=True,no_new_lookup_tables_global_RAM_libgcc=True,bank13bytes_symbolically_mapped_not_identity=True,
    primitive_control_ARM_calls=573536,all_generic_control_parent_increase_rows143384=True,all_adverse_controls_retained_not_public_numeric_gold=True,explicit_carry_up_rows180=True,diagnostic_public_ARM_calls=probe['actual_diagnostic_ARM_calls'],diagnostic_MPFR_inputs=probe['actual_directed_MPFR_inputs'],diagnostic_not_fullqualification=True,
    mandatory_current_object_native_C_guard_and12negatives_each_changed_release=True,mandatory_exp_R12_17negative_normalized_ROMloader9disabled_guards_PASS=True,first_failed_disabled_report_missing_alias_preserved_no_binary_change=True,new_ARM_MPFR_calls_in_this_host_proof=0,selected=False,full_public_qualification_pending=True,universal_CR_generalpowtotality_floatFMA_stack_cycles_not_proved=True,independent_acceptance=False,performance_or_adoption_GO=False,hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False)
(W/'source-binding-proof.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
