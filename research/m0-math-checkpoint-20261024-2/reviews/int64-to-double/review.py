"""Independent signed64 conversion entry review; bare ARM and integer RNE only."""
from pathlib import Path
from collections import Counter
import hashlib,importlib.util,json,re,subprocess,sys,struct
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
W=ROOT/'.build/m0-l2d-original-goal-20261024'
BASE=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
PREVIOUS=ROOT/'.build/m0-mixed-sign-top-normal-independent-20261023'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,note):
    if not v:raise AssertionError(note)
def ref(p):return {'path':str(p),'sha256':sha(p)}
require(sys.flags.optimize==0,'Machine assertions require normal Python')
require(sha(PREVIOUS/'FINAL-REVIEW.json')=='1fa5ec2420e2ddf1a8d8a1ca881976f4c0033f308d601dd7d99b12afad58b86f','Prior own RNE proof changed')
prior_receipt=json.loads((PREVIOUS/'FINAL-REVIEW.json').read_text())
require(sha(PREVIOUS/'review.py')==prior_receipt['review_script']['sha256'],'Prior integer rounding source changed')
spec=importlib.util.spec_from_file_location('prior_independent_rounding',PREVIOUS/'review.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
ElfImage=prior.ElfImage;Machine=prior.Machine;SP=prior.SP
commands=[]
def run(args):
    args=list(map(str,args));result=subprocess.run(args,check=True,capture_output=True,text=True);commands.append(args);return result.stdout
def undefined(e):return sorted({row[0]for sec in e.sections if sec[1]==2 for row in prior.symbols(e,sec)if row[0]and row[5]==0})


def source_proof():
    require(sha(W/'result.json')=='5c431f4ea3d6ca26545089209d8ce8c5b4b195dfc5b5ab59577817f725d4fed7','Wrong target')
    result=json.loads((W/'result.json').read_text())
    for name,digest in result['files'].items():require(sha(W/name)==digest,'Producer artifact changed '+name)
    for name,digest in json.loads((W/'input-pins.json').read_text())['files'].items():require(sha(ROOT/name)==digest,'Input changed '+name)
    source=(W/'native_eabi_m0_convert.inc').read_text();old=(BASE/'native_eabi_m0_convert.inc').read_text()
    section='.global __aeabi_ul2d\n';end=source.index(section);start=source.index('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n')
    entry=source[start:end];original_entry=entry.split('#else\n',1)[1].removesuffix('#endif\n')
    require(source[:start]+original_entry+source[end:]==old,'Delta extends beyond RP signed64 entry')
    require((W/'native_eabi_m0.S').read_bytes()==(BASE/'native_eabi_m0.S').read_bytes(),'Other uint32/native source merged')
    prefix=(W/'native_eabi_m0.S').read_text().split('#include "native_eabi_m0_convert.inc"',1)[0]
    conversion=source.split('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\nfunction __aeabi_f2d',1)[0]
    require(prefix+conversion+'\n#endif\n'==(W/'candidate.S').read_text(),'Public/private extraction mismatch')
    isolation=json.loads((W/'isolation.json').read_text())
    for index,name in ((0,'parent.o'),(1,'public.o')):
        args=list(isolation['commands'][index]);args[-1]=str(HERE/name);run(args)
    require(sha(HERE/'parent.o')==sha(W/'control-full.o')and sha(HERE/'public.o')==sha(W/'candidate-full.o'),'Own assembly differs')
    parent,public=ElfImage(HERE/'parent.o'),ElfImage(HERE/'public.o');a,b=prior.allocated(parent),prior.allocated(public)
    require(set(a)==set(b)and[n for n in a if a[n]!=b[n]]==['.text.__aeabi_i2d'],'Unexpected allocated delta')
    body=b['.text.__aeabi_i2d'];require(len(a['.text.__aeabi_i2d'])==876 and len(body)==884,'Wrong conversion section sizes')
    diagnostic=ElfImage(W/'candidate.elf');standalone=ElfImage(W/'candidate.o');raw=(W/'candidate.bin').read_bytes()
    require(body==raw==prior.allocated(diagnostic)['.text'],'Public/executed884-byte body differs')
    entries={}
    for op in ('l2d','ul2d','i2d','ui2d'):
        name='__aeabi_'+op;require(public.symbols[name]==diagnostic.symbols[name]-0x10185000,'Entry mismatch '+op)
        entries[op]=public.symbols[name]&~1
    require(not undefined(standalone)and not undefined(diagnostic),'Standalone dependency')
    require(not[sec for sec in standalone.sections if sec[1]in(4,9)and sec[5]],'Standalone relocation')
    require(undefined(parent)==undefined(public),'Full object dependency changed')
    nobits=lambda e:{name:sec[5]for name,sec in e.named_sections.items()if sec[1]==8 and sec[2]&2}
    require(nobits(parent)==nobits(public),'Global RAM allocation changed')
    contexts=[]
    for label in ('generic_M0','M4_soft','M4_hard'):
        before,after=(ElfImage(W/(label+'-'+suffix+'.o'))for suffix in ('control','candidate'))
        require(prior.allocated(before)==prior.allocated(after)and nobits(before)==nobits(after),'Off-target context changed '+label)
        contexts.append(dict(context=label,allocated_bytes=sum(map(len,prior.allocated(after).values())),equal=True))
    dis=run([Path(isolation['commands'][0][0]).with_name('arm-none-eabi-objdump'),'-dr',W/'candidate.elf']);(HERE/'bare.dis').write_text(dis)
    require(not re.search(r'\s(?:blx?|udf|svc|bkpt)\s',dis),'Standalone call/trap')
    new_entry=entry.split('#else\n',1)[0]
    require(not re.search(r'(?m)^\s*(?:ldr|str|strb|strh|push|pop|bl|blx|cpsid|cpsie)\b',new_entry),'Entry adds memory/call/IRQ path')
    proof=dict(status='PASS_EXACT_RP_SIGNED64_ENTRY_PUBLIC_EXECUTED_BODY',artifact_count=len(result['files']),
      own_full_objects_byte_exact=True,public_executed_body_bytes=884,exclusions=[],entry_offsets=entries,
      source_only_RP_signed_entry_changed=True,normalization_RNE_unsigned_and_32bit_sources_unchanged=True,
      standalone_undefined=[],standalone_relocations=[],BL_BLX_or_trap=False,full_dependencies_equal=True,
      unrelated_allocated_sections_equal=True,allocated_NOBITS_equal=nobits(public),contexts=contexts,
      extra_bytes=8,new_tables_literals_global_RAM=False,earlier_uint32_delta_merged=False,commands=commands,hardware_access=False)
    (HERE/'SOURCE-OBJECT-PROOF.json').write_text(json.dumps(proof,indent=2)+'\n')


def integer_to_binary64(raw,width,signed):
    raw&=(1<<width)-1;value=raw-(1<<width)if signed and raw>>(width-1)else raw
    if not value:return 0
    sign=(1<<63)if value<0 else 0;n=abs(value);bits=n.bit_length();exponent=bits-1
    mantissa=prior.round_even(n,bits-53)
    if mantissa==1<<53:mantissa>>=1;exponent+=1
    return sign|((exponent+1023)<<52)|(mantissa&((1<<52)-1))


def first_rows(path,count):
    text=path.read_text();at=text.index('"rows": [')+len('"rows": [');decoder=json.JSONDecoder();rows=[]
    while len(rows)<count:
        while text[at]in' \t\r\n,':at+=1
        row,at=decoder.raw_decode(text,at);rows.append(row)
    return rows


def selected():
    from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    operations={'l2d':(64,True,'qfp_int642double'),'ul2d':(64,False,'qfp_uint642double'),
                'i2d':(32,True,'qfp_int2double'),'ui2d':(32,False,'qfp_uint2double')}
    jobs={}
    def add(op,value,group):
        width,signed,_=operations[op]
        if not(-(1<<(width-1))<=value<(1<<(width-1))if signed else 0<=value<(1<<width)):return
        jobs.setdefault((op,value&((1<<width)-1)),group)
    old=first_rows(W/'qualification.json',16)
    require(all(row['group']=='old16_l2d_slower'for row in old),'Wrong historical16 selection')
    for row in old:jobs[('l2d',int(row['x'],16))]='old16'
    for n in (-(1<<63),-(1<<63)+1,(1<<63)-1,(1<<63)-2,0,-1,1,-(1<<32),-(1<<32)+1,-(1<<32)-1,(1<<32)-1,1<<32,(1<<32)+1):
        add('l2d',n,'INT64-endpoints-and-word-boundary')
    for high in (0,1,0x7fffffff,0x80000000,0xfffffffe,0xffffffff):
        for low in (0,1,2,0x7fffffff,0x80000000,0xffffffff):
            raw=(high<<32)|low;add('l2d',raw-(1<<64)if raw>>63 else raw,'complement-borrow-and-high-partition')
    for bit in range(1,64):
        n=(1<<bit)-1;add('l2d',n,'selected-every-bit-length');add('l2d',-n,'selected-every-bit-length')
    for shift in (1,2,9,10):
        for retained in (1<<52,(1<<52)+1,(1<<53)-1):
            mid=(retained<<shift)+(1<<(shift-1))
            for delta in (-1,0,1):
                for sign in (-1,1):add('l2d',sign*(mid+delta),'RNE-parity-midpoint-and-binade-carry')
    for n in (0,1,(1<<32)-1,1<<32,(1<<52)-1,1<<52,(1<<53)+1,(1<<63)-1,1<<63,(1<<64)-1):add('ul2d',n,'unsigned64-unchanged')
    for op in ('i2d','ui2d'):
        for n in (0,1,2,(1<<19)-1,1<<19,1<<20,(1<<21)-1,1<<31,(1<<32)-1,-1,-(1<<31),(1<<31)-1):add(op,n,'32bit-unchanged-with-upper-register-poison')
    require(len(jobs)<=350,'Selected replay expanded too far')
    base=0x10185000;candidate=Machine(W/'candidate.elf',True,stack_bytes=32)
    parent=Machine(prior.FIRMWARE,True,stack_bytes=4096,bootrom=prior.ROM);reference=Machine(prior.REFERENCE,True,stack_bytes=4096)
    require(candidate.bootrom_sha256 is None and not candidate.rom_models and not candidate.rom_initializers,'Bare candidate has ROM assistance')
    def code(uc,pc,size,user):require(base<=pc and pc+size<=base+884,'Candidate escaped its884-byte body')
    def read(uc,access,address,size,value,user):require(base<=address and address+size<=base+884,'Candidate read outside its own literal/code body')
    def write(uc,access,address,size,value,user):raise AssertionError('Candidate stack/global/MMIO write')
    candidate.uc.hook_add(UC_HOOK_CODE,code);candidate.uc.hook_add(UC_HOOK_MEM_READ,read);candidate.uc.hook_add(UC_HOOK_MEM_WRITE,write)
    states=[struct.pack('<7I',17,3,17,3,5,2,flag)for flag in (1,3)];rows=[]
    for index,((op,raw),group)in enumerate(jobs.items()):
        width,signed,refname=operations[op];expected=integer_to_binary64(raw,width,signed)
        value=raw-(1<<width)if signed and raw>>(width-1)else raw
        argument=raw if width==64 else raw|(0xdeadbeef<<32)
        values={};cost={}
        for label,symbol,engine in (('candidate','__aeabi_'+op,candidate),('parent','__aeabi_'+op,parent),('Qfplib',refname,reference)):
            state=states[index%2];engine.uc.mem_write(0xd0000060,state);engine.stack_lowest=SP
            got,_,instructions=engine.call(symbol,argument,count=True)
            require(bytes(engine.uc.mem_read(0xd0000060,28))==state,'SIO READY/DIRTY/context changed')
            require(got==expected,'Integer RNE mismatch '+str((op,hex(raw),label,hex(got),hex(expected))))
            if label=='candidate':require(engine.stack_lowest==SP,'Candidate wrote a stack frame')
            values[label]=got;cost[label]=instructions
        if op!='l2d'or value>=0:require(cost['candidate']==cost['parent'],'Positive/unsigned/32bit path cost changed')
        else:require(cost['parent']-cost['candidate']==(5 if -(1<<32)<value<0 else 1),'Signed entry savings do not match the source partition')
        if group=='old16':require(cost['candidate']<=cost['Qfplib'],'Historical correct-Qfplib loss remains')
        rows.append(dict(operation=op,x=f'{raw:016x}',group=group,expected=f'{expected:016x}',
                         outputs={label:f'{v:016x}'for label,v in values.items()},instructions=cost))
    old_rows=[r for r in rows if r['group']=='old16']
    report=dict(status='PASS_SELECTED_BARE_ARM_SIGNED64_AND_INTEGER_RNE',cases=len(rows),ARM_calls=3*len(rows),
      groups=dict(Counter(row['group']for row in rows)),rows=rows,old16=dict(cases=len(old_rows),strict_faster=sum(r['instructions']['candidate']<r['instructions']['Qfplib']for r in old_rows),equal=sum(r['instructions']['candidate']==r['instructions']['Qfplib']for r in old_rows)),
      all_Qfplib_results_bit_correct=True,oracle='Own unbounded signed/unsigned integer magnitude, bit length and exact nearest-even quotient; no host float/MPFR/author oracle',
      reused_round_even_source=ref(PREVIOUS/'review.py'),candidate_firmware_or_ROM=False,candidate_stack_bytes_written=0,
      candidate_PC_and_reads_inside884_only=True,candidate_no_writes_of_any_kind=True,PCS_SP_and_READY_DIRTY_preserved_all_calls=True,
      positive_l2d_ul2d_i2d_ui2d_costs_equal=True,negative_l2d_source_partition_savings_exact=True,upper_R1_poison_for32bit_ABI=True,
      candidate_ELF=ref(W/'candidate.elf'),parent_firmware=ref(prior.FIRMWARE),parent_ROM=ref(prior.ROM),reference_ELF=ref(prior.REFERENCE),
      hardware_access=False,physical_cycles_measured=False)
    require(report['old16']['strict_faster']==12 and report['old16']['equal']==4,'Historical16 instruction partition differs')
    (HERE/'SELECTED-ARM-INTEGER.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    source_proof();report=selected();print(json.dumps({k:v for k,v in report.items()if k!='rows'},indent=2))
