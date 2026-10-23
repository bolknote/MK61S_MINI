"""Independent bounded E0 delta review; bare ARM candidate, no device APIs."""
from pathlib import Path
from collections import Counter
import hashlib,importlib.util,json,re,struct,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
W=ROOT/'.build/m0-add-subnormal-input-20261023';PARENT=ROOT/'.build/m0-add-cold-normal-20261023'
PREVIOUS=ROOT/'.build/m0-add-cold-normal-independent-20261023'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,note):
    if not v:raise AssertionError(note)
def ref(p):return {'path':str(p),'sha256':sha(p)}
require(sys.flags.optimize==0,'Legacy Machine asserts require default nonoptimized Python')
require(sha(PREVIOUS/'FINAL-REVIEW.json')=='1266ecde350f8eb7662cc335da11ad7aece6e2cb18d36ed9d723bbac3c9edd2d','Previous independent result changed')
proof=json.loads((PREVIOUS/'FINAL-REVIEW.json').read_text())
require(sha(PREVIOUS/'review.py')==proof['review_script']['sha256'],'Independent oracle source changed')
spec=importlib.util.spec_from_file_location('independent_low_oracle',PREVIOUS/'review.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
ElfImage=prior.ElfImage;Machine=prior.Machine;SP=prior.SP
SIGN=1<<63;H=1<<52;FRAC=H-1;INF=0x7ff0000000000000;QUIET=1<<51
commands=[]
def run(args):
    args=list(map(str,args));completed=subprocess.run(args,check=True,capture_output=True,text=True);commands.append(args);return completed.stdout
def undefined(e):return sorted({row[0]for sec in e.sections if sec[1]==2 for row in prior.prior.symbols(e,sec)if row[0]and row[5]==0})


def source_proof():
    require(sha(W/'result.json')=='4cbf5c03c4846ca4f653700d293801d6234fe79ec5459994d7aabe0a671136fe','Wrong result')
    result=json.loads((W/'result.json').read_text())
    for name,digest in result['files'].items():require(sha(W/name)==digest,'Producer artifact changed '+name)
    for name,digest in json.loads((W/'input-pins.json').read_text())['files'].items():require(sha(ROOT/name)==digest,'Pinned input changed '+name)
    source=(W/'native_eabi_m0_rp2040.S').read_text();old=(PARENT/'native_eabi_m0_rp2040.S').read_text()
    extracted=source.split('mk61_m0_dadd_end:',1)[0].replace('__aeabi_dadd','sub_candidate_dadd').replace('__aeabi_dsub','sub_candidate_dsub').replace('.text.mk61_rp2040_arithmetic','.text.m0_subnormal_trial')+'\n#endif\n'
    require(extracted==(W/'candidate.S').read_text(),'Public/private extraction differs')
    marker='\n.align 2\n\n.ltorg\nmk61_m0_dadd_end:'
    reduced=source[:source.index('\n.macro da_zero_cell')]+source[source.index(marker):]
    stubs='.Lda_zero_a_stub:\n b .Lda_zero_a\n.Lda_zero_b_stub:\n b .Lda_zero_b'
    slow='.Lda_slow:\n // Save the volatile R3 in the previously reserved alignment word.\n // A six-register pop restores the identical24-byte frame in one step.\n push {r3}\n bl mk61_m0_dadd_slow\n pop {r3-r7,pc}'
    reduced=reduced.replace(stubs,slow).replace('beq .Lda_zero_a_stub','beq .Lda_slow').replace('beq .Lda_zero_b_stub','beq .Lda_slow')
    require([x for x in reduced.splitlines()if x.strip()]==[x for x in old.splitlines()if x.strip()],
            'Prior normal/low/top/nonfinite code changed beyond E0 entry/fallback replacement')
    compiler=Path(json.loads((W/'build.json').read_text())['commands'][0][0]);include=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
    common=[compiler,'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-I',include,'-c']
    run(common+[W/'native_eabi_m0_rp2040.S','-o',HERE/'public.o']);run(common+[PARENT/'native_eabi_m0_rp2040.S','-o',HERE/'parent.o'])
    require(sha(HERE/'public.o')==sha(W/'candidate-full.o')and sha(HERE/'parent.o')==sha(W/'control-full.o'),'Own full assembly is not byte exact')
    parent,public=ElfImage(HERE/'parent.o'),ElfImage(HERE/'public.o');a,b=prior.prior.allocated(parent),prior.prior.allocated(public)
    require(set(a)==set(b)and[n for n in a if a[n]!=b[n]]==['.text.mk61_rp2040_arithmetic'],'Unexpected allocated delta')
    name='.text.mk61_rp2040_arithmetic';require(parent.symbols['mk61_m0_dadd_end']==1204 and public.symbols['mk61_m0_dadd_end']==1472,'Body size mismatch')
    require(a[name][1204:]==b[name][1472:],'Following multiply/divide kernel changed')
    standalone=ElfImage(W/'candidate.o');diagnostic=ElfImage(W/'candidate.elf');binary=(W/'candidate.bin').read_bytes()
    require(not undefined(standalone)and not undefined(diagnostic),'Standalone has an external dependency')
    require(not[sec for sec in standalone.sections if sec[1]in(4,9)and sec[5]],'Standalone has relocations')
    require(b[name][:1472]==binary and len(binary)==1472,'Public/executed bytes differ without a BL exception')
    require(prior.prior.allocated(diagnostic)['.text']==binary,'Executed ELF text differs from loaded binary')
    for op in ('dadd','dsub'):require((public.symbols['__aeabi_'+op]&~1)==(diagnostic.symbols['sub_candidate_'+op]&~1)-0x10184000,'Public/diagnostic entry mismatch')
    removed=set(undefined(parent))-set(undefined(public));added=set(undefined(public))-set(undefined(parent))
    require(removed=={'mk61_m0_dadd_slow'}and not added,'Unexpected full-object dependency delta')
    contexts=[]
    for label in ('M4_soft','M4_hard','generic_M0'):
        before,after=(ElfImage(W/(label+'-'+suffix+'.o'))for suffix in ('control','candidate'))
        require(prior.prior.allocated(before)==prior.prior.allocated(after),'M4/generic contribution changed')
        contexts.append(dict(label=label,equal=True,allocated_bytes=sum(map(len,prior.prior.allocated(after).values()))))
    disassembly=run([compiler.with_name('arm-none-eabi-objdump'),'-dr',W/'candidate.elf']);(HERE/'bare.dis').write_text(disassembly)
    require(not re.search(r'\sblx?\s',disassembly),'Standalone still contains a BL/BLX')
    report=dict(status='PASS_FINAL_SOURCE_PUBLIC_BODY_EXECUTED_WITHOUT_EXCLUSIONS',artifact_count=len(result['files']),body_bytes=1472,
      parent_body_bytes=1204,extra_bytes=268,own_full_assembly_exact=True,full1472_bytes_equal=True,entry_offsets_equal=True,
      standalone_undefined=[],standalone_relocations=[],standalone_BL_BLX=False,removed_dependencies=sorted(removed),added_dependencies=[],
      no_new_tables_literal_words_or_global_RAM=True,prior_normal_low_top_NF_source_unchanged=True,
      following_kernels_and_other_allocated_sections_equal=True,M4_generic_controls=contexts,M4_full_firmware_rebuilt=False,
      commands=commands,hardware_access=False)
    (HERE/'SOURCE-OBJECT-PROOF.json').write_text(json.dumps(report,indent=2)+'\n')


def first_rows(path,count):
    # Read only the explicitly requested head vectors, not the author's corpus replay.
    text=path.read_text();at=text.index('"rows": [')+len('"rows": [');decoder=json.JSONDecoder();rows=[]
    while len(rows)<count:
        while text[at]in' \r\n\t,':at+=1
        value,at=decoder.raw_decode(text,at);rows.append(value)
    return rows


def selected():
    from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    jobs={}
    def sem(a,b,tag):
        for op in ('dadd','dsub'):jobs.setdefault((op,a,b^(SIGN if op=='dsub'else 0)),tag)
    for a,b in ((0,0),(SIGN,0),(0,SIGN),(SIGN,SIGN),(1,1),(FRAC,1),(FRAC,FRAC),(FRAC,FRAC-1),
                (1,H),(1,2*H-2),(1,2*H-1),(2,2*H-1),(3,2*H-1),(4,2*H-1),
                (1,H+1),(1,H+2),(FRAC,H),(FRAC,H+1)):
        sem(a,b,'raw-E0-E1-sum-rounding-and-smallest-normal');sem(b,a^SIGN,'raw-E0-E1-opposite-sign-difference')
    descriptors=((2,0,True),(2,1,False),(3,0,False),(3,1,True),(33,1,False),
                 (34,0,False),(34,1,False),(34,0,True),(54,0,True),(55,0,False))
    for number,(e,fraction,toward_zero)in enumerate(descriptors):
        k=e-2-(toward_zero and fraction==0);radius=1<<k if k>=0 else 0
        values=sorted({n for n in(radius-1,radius,radius+1)if 0<n<H})or[FRAC]
        for n in values:
            normal=(e<<52)|fraction;sub=n^(SIGN if toward_zero else 0)
            if number&1:normal^=SIGN;sub^=SIGN
            sem(normal,sub,'normal-cell-k31-k32-power-two-and-parity');sem(sub,normal,'normal-cell-k31-k32-power-two-and-parity')
    for e in (2,3,54,55,1023,2046):
        sem(e<<52,FRAC|SIGN,'virtual-unpack-and-large-exponent-shortcut');sem(FRAC,(e<<52)|SIGN,'virtual-unpack-and-large-exponent-shortcut')
    for a,b in ((0,INF),(SIGN,INF|SIGN),(1,INF|1),(INF|SIGN|1,0),(FRAC,INF|QUIET|7),(INF|QUIET|9,SIGN)):
        for op in ('dadd','dsub'):jobs[(op,a,b)]='E0-special-and-first-NaN-policy'
    old18=first_rows(W/'qualification.json',18)
    require(all(row['group']=='old18_subnormal_slower'for row in old18),'Wrong old18 vector selection')
    for row in old18:jobs[(row['operation'],int(row['x'],16),int(row['y'],16))]='old18'
    for e in (1,2,54,55,1023,2045,2046,2047):
        a=(e<<52)|FRAC;b=(max(1,e-1)<<52)|1
        sem(a,b,'unchanged-normal-low-top-NF-controls');sem(a,b^SIGN,'unchanged-normal-low-top-NF-controls')
    old17=json.loads((ROOT/'.build/m0-mixed-sign-original-goal-20261023/edges.json').read_text())['rows']
    for row in old17:
        if row['group']=='known_slower':jobs[(row['operation'],int(row['x'],16),int(row['y'],16))]='old17-control'
    require(len(jobs)<=300,'Bounded selected replay grew too far')
    base=0x10184000;candidate=Machine(W/'candidate.elf',True,stack_bytes=32)
    firmware=prior.prior.FIRMWARE;rom=prior.prior.ROM;reference_path=prior.prior.REFERENCE
    parent=Machine(firmware,True,stack_bytes=4096,bootrom=rom);reference=Machine(reference_path,True,stack_bytes=4096)
    pe=ElfImage(PARENT/'candidate.elf');parent.uc.mem_write(0x10183000,(PARENT/'candidate.bin').read_bytes())
    for op in ('dadd','dsub'):parent.elf.symbols['parent_'+op]=pe.symbols['cold_candidate_'+op]
    require(candidate.bootrom_sha256 is None and not candidate.rom_models and not candidate.rom_initializers,'Candidate reused ROM/firmware helper')
    def code(uc,pc,size,user):require(base<=pc and pc+size<=base+1472,'Candidate escaped its standalone body')
    def read(uc,access,address,size,value,user):require((base<=address and address+size<=base+1472)or(SP-32<=address and address+size<=SP),'Candidate read outside body/32-byte stack')
    def write(uc,access,address,size,value,user):require(SP-32<=address and address+size<=SP,'Candidate made an MMIO/global write')
    candidate.uc.hook_add(UC_HOOK_CODE,code);candidate.uc.hook_add(UC_HOOK_MEM_READ,read);candidate.uc.hook_add(UC_HOOK_MEM_WRITE,write)
    state=struct.pack('<7I',17,3,17,3,5,2,3);rows=[]
    for(op,a,b),group in jobs.items():
        expected=prior.expected_policy(a,b,op=='dsub');values={};cost={}
        for label,symbol,engine in (('candidate','sub_candidate_'+op,candidate),('parent','parent_'+op,parent),('Qfplib','qfp_'+op,reference)):
            engine.uc.mem_write(0xd0000060,state);engine.stack_lowest=SP
            got,_,count=engine.call(symbol,a,b,count=True)
            require(bytes(engine.uc.mem_read(0xd0000060,28))==state,'SIO READY/DIRTY/context changed')
            if label!='Qfplib':require(got==expected,'Independent RNE/NaN mismatch '+str((group,op,hex(a),hex(b),label,hex(got),hex(expected))))
            if label=='candidate':require(engine.stack_lowest==SP-20,'Candidate used a frame other than20 bytes')
            values[label]=got;cost[label]=count
        if group in('old17-control','unchanged-normal-low-top-NF-controls'):require(cost['candidate']==cost['parent'],'Unaffected path instruction cost changed')
        else:require(cost['candidate']<=cost['parent'],'E0 path regressed against parent')
        if group=='old18':require(values['Qfplib']==expected and cost['candidate']<cost['Qfplib'],'Old18 not improved versus correct Qfplib')
        rows.append(dict(group=group,operation=op,x=f'{a:016x}',y=f'{b:016x}',expected=f'{expected:016x}',
          outputs={label:f'{value:016x}'for label,value in values.items()},instructions=cost))
    report=dict(status='PASS_SELECTED_BARE_ARM_E0_AND_INDEPENDENT_INTEGER_RNE',cases=len(rows),ARM_calls=3*len(rows),groups=dict(Counter(row['group']for row in rows)),rows=rows,
      oracle='Reused independently reviewed exact binary-lattice integer RNE plus explicit first-NaN quiet/payload/sign policy; no author oracle/host float/MPFR',
      independent_oracle_source=ref(PREVIOUS/'review.py'),bare_candidate_ELF=ref(W/'candidate.elf'),candidate_maps_firmware_or_ROM=False,
      candidate_allowed_stack_bytes=32,candidate_observed_written_stack_bytes=20,candidate_PC_data_read_and_write_boundaries_checked=True,
      candidate_ROM_callbacks=[],candidate_helper_or_MMIO_access=False,PCS_SP_and_READY_DIRTY_preserved_all_calls=True,
      old18_all_faster_than_bit_correct_Qfplib=True,normal_low_top_NF_and_old17_results_and_counts_equal=True,
      parent_firmware=ref(firmware),parent_ROM=ref(rom),reference_ELF=ref(reference_path),
      hardware_access=False,physical_cycles_measured=False)
    (HERE/'SELECTED-ARM-INTEGER.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    source_proof();report=selected()
    print(json.dumps({key:value for key,value in report.items()if key!='rows'},indent=2))
