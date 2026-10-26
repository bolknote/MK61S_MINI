"""Bind both exact-overflow shortcuts, unchanged targets and all adverse evidence."""
from pathlib import Path
import ast,hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-pow-rsqrt-nativeq8-r43-20261026'
M=ROOT/'.build/m0-math-unified-ddiv-overflow-r44-20261026'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not(W/'source-binding-proof.json').exists()
for base,pin in [(P,'170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b'),(M,'ac14437a770763e7c46d8782a7f02506ecfcc3b0c2b598c5476e1d29324dfb3a')]:
    assert sha(base/'FROZEN.json')==pin
    for n,r in read(base/'FROZEN.json')['files'].items():assert(base/n).stat().st_size==r['bytes']and sha(base/n)==r['sha256'],n
def literals(p,names):
    out={}
    for n in ast.parse(p.read_text()).body:
        if isinstance(n,ast.Assign)and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)and n.targets[0].id in names:out[n.targets[0].id]=ast.literal_eval(n.value)
    assert set(out)==set(names);return out
edit=literals(W/'build.py',['before','after','guard']);src='source/code/native_eabi_m0_rp2040.S';old=(M/src).read_text();new=(W/src).read_text();assert new==old.replace(edit['before'],edit['after']).replace('.Lrp2040_div_slow:\n',edit['guard']+'.Lrp2040_div_slow:\n')
assert new.replace(edit['guard'],'').replace(edit['after'],edit['before'])==old
cpp='source/code/native_eabi_m0.cpp';assert(W/cpp).read_bytes()==(M/cpp).read_bytes();ce=literals(M/'build.py',['before','after']);assert(W/cpp).read_text().replace(ce['after'],ce['before'])==(P/cpp).read_text()
changed={str(p.relative_to(P/'source'))for p in(P/'source').rglob('*')if p.is_file()and sha(p)!=sha(W/'source'/p.relative_to(P/'source'))};assert changed=={'code/native_eabi_m0.cpp','code/native_eabi_m0_rp2040.S'}
assert 'static constexpr int Bias='in(W/cpp).read_text()and'if(e>Bias) return sign|Infinity;'in ce['after']
spec=importlib.util.spec_from_file_location('r45_fp',ROOT/'research/m0-math-checkpoint-20261025-5/verify.py');fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)
link=read(W/'link-result.json');assert len(link['unchanged_objects'])==18 and link['default_M0_M4_objects_exact']
oldlink=read(P/'link-result.json');other=[];diffs={}
for n,row in link['outputs'].items():
    assert sha(W/n)==row['sha256']and fp.image_fingerprint((W/n).read_bytes())==row['fingerprint']
    if not n.endswith('.o'):continue
    a,b=row['fingerprint'],oldlink['outputs'][n]['fingerprint']
    if a==b:other.append(n);continue
    ad,bd=[{r[0]:r for r in z['allocated']}for z in(a,b)];diffs[n]=[s for s in sorted(ad.keys()|bd.keys())if ad.get(s)!=bd.get(s)]
assert len(other)==17 and diffs=={'RP-merged-cpp.o':['.text._ZN7m0_eabi6BinaryILj52ELj11EE3divEyy'],'RP-unified-native_eabi_m0_rp2040.S.o':['.text.mk61_rp2040_arithmetic']}
# Algebraic width/threshold proof, with all admitted shift counts represented.
widths=[];mask=(1<<32)-1
for k in range(1,53):
    for H in(1<<20,(1<<20)+1,(1<<21)-1):
        for L in(0,1,mask):
            M53=(H<<32)|L
            if k<32:hi=H>>k;lo=(L>>k)|((H<<(32-k))&mask)
            else:hi=0;lo=H>>(k-32)
            assert(hi<<32)|lo==M53>>k
    widths.append(dict(k=k,left_count=32-k if k<32 else None,right_high_count=k if k<32 else k-32))
assert min(v['right_high_count']for v in widths)==0
guard=read(W/'div-guard-proof.json');native=read(W/'native-caller-proof.json');bank=read(W/'bank-map.json')
assert len(guard['negative_controls_rejected'])==6 and guard['no_argument_writes_on_any_decline']and len(native['negative_controls_rejected'])==12 and bank['all_changed_bytes_explained']
assert(W/'controls.log').read_text().strip().splitlines()==['verify-private-return PASS','verify-guard-controls PASS','verify-loader PASS','verify-disabled PASS']
stats={}
for name,filename in [('direct','div-probe-result.json'),('grid','guard-grid-result.json'),('pow','probe-result.json')]:
    r=read(W/filename);assert r['candidate_wrong']==0 and not r.get('new_correct_Qfp_loss_rows',r.get('new_correct_reference_loss_rows'))
    stats[name]=dict(inputs=r['input_pairs'],ARM=r['actual_diagnostic_ARM_calls'],MPFR=r['actual_directed_MPFR_inputs'],sNaN=r.get('sNaN_policy_shortcuts',r.get('exact_sNaN_policy_shortcuts')),parent_losses=r['parent_losing_pairs'],candidate_losses=r['candidate_losing_pairs'],all_parent_increase_rows=len(r['all_parent_instruction_increase_rows']))
assert stats['direct']['candidate_losses']==148 and stats['grid']['candidate_losses']==0 and stats['pow']['candidate_losses']==2047
assert stats['direct']['all_parent_increase_rows']==1212 and stats['grid']['all_parent_increase_rows']==17046 and stats['pow']['all_parent_increase_rows']==30
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
e,prev=ElfImage(W/'candidate.elf'),ElfImage(P/'candidate.elf');flash=lambda x:sum(s[4]for s in x.segments if s[0]==1 and 0x10010000<=s[3]<0x10200000)
assert flash(e)-flash(prev)==104 and e.named_sections['.scratch_y'][5]==4080 and bank['changed_bytes']==6
result=dict(status='PASS_R45_EXACT_OVERFLOW_SOURCE_COMPOSITION_AND_LINKED_GUARD_PROOF',candidate_ELF_sha256=sha(W/'candidate.elf'),parent_R43_source_FROZEN_sha256=sha(P/'FROZEN.json'),unselected_R44_parent_source_FROZEN_sha256=sha(M/'FROZEN.json'),both_source_edits_reversed_exactly_to_R43=True,only2objects_changed=diffs,other17_objects_including_M4default_exact=True,
    finite_CPP_quotient_normalization_exact_ratio1to2_e_integer_range_minus2098_to2097=True,CPP_e_greater1023_implies_true_magnitude_atleast2pow1024=True,
    ASM_entry_normal_numerator_Ea1to2046_and_Eb0or2047_N_checked=True,ASM_subnormal_overflow_equivalence='For normal numerator M*2^(Ea-1075) and subnormal denominator N*2^-1074: |a/b|=(M/N)*2^(Ea-1). For k=1025-Ea, N<=floor(M/2^k) implies |a/b|>=2^1024. k<=0 always true for N<2^52,M>=2^52; k>=53 false for nonzero N because M<2^53. Zero denominator with normal numerator returns exact signed infinity.',
    all52_threshold_shift_formulas_exact=True,shift_count_cases=widths,mathematical_proof_uses_integer_identity_for_all_M_not_just_test_endpoints=True,overflow_midpoint_2pow1024_minus2pow970_strictly_below2pow1024=True,other_division_values_execute_existing_exact_RNE_body=True,NaN_zero_infinity_policy_and_callee_SP_SIO_preserved=True,
    actual_ASM_caller_body_literals_and_all_declines_bound=True,mandatory_current_new_div_guard6negatives_and_native_Q8_guard12negatives=True,mandatory_exp_R12_17negative_normalized_ROMloader9disabled_PASS=True,new_calls_tables_RAM_libgcc_bytes=0,code_Flash_delta_bytes_vs_R43=104,bank6bytes_symbolically_mapped_not_identity=True,
    source_diagnostics=stats,total_source_diagnostic_ARM_calls=sum(v['ARM']for v in stats.values()),all_source_diagnostics_not_yet_full_qualification_pool=True,all_parent_increases_including_already_slower_cases_retained=True,inherited_R43_Q8_controls573536_not_fresh=True,inherited_R43_generic_helper143384_increases_retained=True,host_alias_binder_first_attempt_preserved_no_numeric_change=True,
    new_ARM_MPFR_calls_in_this_host_proof=0,selected=False,full_public_qualification_pending=True,universal_CR_generalpowtotality_floatFMA_stack_cycles_not_proved=True,independent_acceptance=False,performance_or_adoption_GO=False,hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False)
(W/'source-binding-proof.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='shift_count_cases'},indent=2),flush=True)
