#!/usr/bin/env python3
"""Compile and verify ALL eight candidates in one HOST package, never device IO."""
from pathlib import Path
import argparse,collections,hashlib,importlib.util,json,subprocess,sys,struct
ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'research/m0-libc-batch-2026-11-07'
sys.path[:0]=[str(ROOT/'tests'),str(R)]
from check_stm32_vectors import ElfImage
from cases import FUNCTIONS,registry

def pin(p):p=Path(p);return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def save(p,j):p.write_text(json.dumps(j,indent=2)+'\n')
def body(e,name):
    at=e.symbols[name]&~1;n=e.sizes[name]
    return next(e.data[o+at-v:o+at-v+n] for kind,o,v,pa,size,mem,fl,align in e.segments if kind==1 and v<=at and at+n<=v+size)
def compile_package(tc,out):
    out.mkdir(parents=True,exist_ok=False);commands=[];cc=tc/'arm-none-eabi-gcc'
    flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-builtin','-fno-lto','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-I'+str(ROOT/'code')]
    def run(argv):
        argv=list(map(str,argv));p=subprocess.run(argv,capture_output=True,text=True);commands.append(dict(argv=argv,EXIT=p.returncode,stdout=p.stdout,stderr=p.stderr));save(out/'COMMANDS.json',commands);assert p.returncode==0,p.stdout+p.stderr
    core=out/'core.c';core.write_text('#include "memory_libc_m0.h"\n')
    products=[]
    for profile in (0,1,2,4,8,16):
        for route in (('control','sdk-baseline') if profile==0 else ('core','sdk','native')):
            folder=out/('%s-%d'%(route,profile));folder.mkdir();obj=folder/'body.o';elf=folder/'body.elf'
            source=R/'control.c' if route=='control' else core if route=='core' else ROOT/('sdk/portable/memory.c' if route in ('sdk','sdk-baseline') else 'ports/picocalc/memory.c')
            extra=['-DMK61_M0_LIBC_UNROLL='+str(profile)]+(['-DPICO_ON_DEVICE=1'] if route=='native' else [])
            # Keep the historical SDK control after production defaults change.
            if route=='sdk-baseline':
                extra+=['-DMK61_M0_'+name.upper()+'_IMPL=0' for name in FUNCTIONS]
            run([cc,*flags,*extra,'-c',source,'-o',obj])
            run([cc,*flags,'-nostdlib','-Wl,--gc-sections,--build-id=none,-Ttext=0x10002000,-e,strlen',*['-Wl,-u,'+name for name in FUNCTIONS],obj,'-lc','-lgcc','-o',elf])
            e=ElfImage(elf);bodies={name:dict(entry=e.symbols[name],bytes=len(body(e,name)),sha256=hashlib.sha256(body(e,name)).hexdigest()) for name in FUNCTIONS}
            run([tc/'arm-none-eabi-objdump','-d',elf]);(folder/'body.dis').write_text(commands[-1]['stdout'])
            products.append(dict(profile=profile,route=route,ELF=pin(elf),functions=bodies))
    for profile in (1,2,4,8,16):
        equal=[p for p in products if p['profile']==profile]
        for name in FUNCTIONS:assert len({p['functions'][name]['sha256'] for p in equal})==1,(profile,name,'native/SDK/core body drift')
    # Verify the actual production roles against independently forced leaves.
    # This does not repeat the semantic campaign: the selected bytes must be
    # exactly the bytes already covered by those candidate tests.
    default_policy=[]
    for role,source in [('native',ROOT/'ports/picocalc/memory.c'),('SDK',ROOT/'sdk/portable/memory.c')]:
        folder=out/('default-'+role);folder.mkdir();obj=folder/'body.o';elf=folder/'body.elf'
        extra=['-DMK61_M0_LIBC_UNROLL=0']+(['-DPICO_ON_DEVICE=1'] if role=='native' else [])
        run([cc,*flags,*extra,'-c',source,'-o',obj])
        run([cc,*flags,'-nostdlib','-Wl,--gc-sections,--build-id=none,-Ttext=0x10002000,-e,strlen',*['-Wl,-u,'+name for name in FUNCTIONS],obj,'-lc','-lgcc','-o',elf])
        e=ElfImage(elf);checked={}
        for name in FUNCTIONS:
            selected=16 if name=='memcmp' or role=='native' and name=='strlen' else 4
            reference=next(v for v in products if v['profile']==selected and v['route']=='core')['functions'][name]
            raw=body(e,name)
            assert raw and len(raw)==reference['bytes'] and hashlib.sha256(raw).hexdigest()==reference['sha256'],(role,name,'production role/default drift')
            checked[name]=dict(selected=selected,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        default_policy.append(dict(role=role,ELF=pin(elf),functions=checked))
    baseline=Path('/Users/bolk/Projects/MK61S_MINI/.build/spectrum-lcd-app-20261107/firmware/mk61s-picocalc-pico-h.elf')
    e=ElfImage(baseline)
    products.append(dict(profile=0,route='actual-native-baseline',ELF=pin(baseline),functions={name:dict(entry=e.symbols[name],bytes=len(body(e,name)),sha256=hashlib.sha256(body(e,name)).hexdigest()) for name in FUNCTIONS}))
    pointer=out/'pointer.c';pointer.write_text('#include <stdint.h>\nuintptr_t* batch_runtime;\n')
    run([cc,*flags,'-DMK61_RUNTIME_POINTER=batch_runtime','-nostdlib','-Wl,--gc-sections,--build-id=none,-Ttext=0x20024000,--section-start=.bss=0x20026000,-e,strlen',*['-Wl,-u,'+name for name in ['strlen','strncmp','strncat','memcmp']],ROOT/'sdk/portable/system/runtime.S',pointer,'-o',out/'runtime.elf'])
    result=dict(status='COMPILED_ALL_EIGHT_CANDIDATES_NOT_SEMANTICALLY_RUN',physical_IO=0,hardware_winner=None,functions=list(FUNCTIONS),profiles=[0,1,2,4,8,16],products=products,default_policy=default_policy,runtime=pin(out/'runtime.elf'),source_pins=[pin(ROOT/p) for p in ['code/memory_libc_m0.h','code/libc_m0_byte.inc','code/libc_m0_strlen_word.inc','code/libc_m0_memcmp_word.inc','code/libc_m0_compare.h','code/libc_m0_copy_words.h','ports/picocalc/memory.c','sdk/portable/memory.c','sdk/portable/system/runtime.S','code/loadable_system_runtime.def','tests/m0_libc_batch_self_test.py']]+[pin(R/n) for n in ['generate.py','control.c','cases.py']])
    save(out/'BUILD.json',result);return result

def run_semantics(build,out,smoke=False,reuse=None):
    from unicorn_runtime import Uc
    from unicorn import UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    import unicorn.arm_const as arm
    rows=registry(full_alignments=not smoke);save(out/'CASES.json',rows)
    if smoke:
        reduced=[]
        for name in FUNCTIONS:
            subset=[r for r in rows if r['function']==name]
            reduced+=subset[:12]+subset[len(subset)//2:len(subset)//2+12]+subset[-12:]
        rows=reduced
    grouped={name:[r for r in rows if r['function']==name] for name in FUNCTIONS}
    cached={}
    if reuse:
        prior=json.loads(reuse.read_text());data=(reuse.parent/'grouped-build-004/CASES.json').read_bytes()
        assert hashlib.sha256(data).hexdigest()==prior['cases_sha256'] and json.loads(data)==registry(full_alignments=True)
        assert hashlib.sha256((reuse.parent/'grouped-semantics-004.log').read_bytes()).hexdigest()==prior['log_sha256']
        for r in prior['passed']:
            assert pin(r['ELF']['path'])==r['ELF'];cached[(r['function'],r['body_sha256'])]=r
    seen=set();results=[];total=0;reused=0;progress=[]
    for product in build['products']:
        e=ElfImage(Path(product['ELF']['path']));u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_M0)
        u.mem_map(0x10000000,0x200000);u.mem_map(0x20000000,0x42000);e.load(u)
        if product['route']=='actual-native-baseline':
            rom=Path('/Users/bolk/Projects/MK61S_MINI/.build/strchr-m0-hil-20261107-v1/runs-002/000-fixture-install/factory-rom.bin').read_bytes()
            assert hashlib.sha256(rom).hexdigest()=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
            u.mem_map(0,0x4000);u.mem_write(0,rom)
            u.reg_write(arm.UC_ARM_REG_SP,0x20041ff0);u.reg_write(arm.UC_ARM_REG_LR,0x101cfff1);u.reg_write(arm.UC_ARM_REG_XPSR,0x01000000)
            u.emu_start(e.symbols['__aeabi_mem_init']|1,0x101cfff0,count=100000)
        pages=[0x20030000,0x20032000,0x101d0000,0x101d2000,0x20034000];stop=0x101cfff0;sp=0x20041ff0
        tail=ElfImage(Path(build['runtime']['path']));tail.load(u)
        table=0x20027000;values=[0]*26
        for name,slot in [('strlen',20),('strncmp',19),('strncat',21),('memcmp',25)]:values[slot]=e.symbols[name]|1
        u.mem_write(table,struct.pack('<26I',*values));u.mem_write(tail.symbols['batch_runtime'],struct.pack('<I',table))
        state={};checks=collections.Counter()
        def access(uc,kind,address,size,value,user):
            if kind==17: # UC_MEM_WRITE
                assert any(lo<=address and address+size<=hi for lo,hi in state['writes']),('write envelope',hex(address),size,state['row'])
            else:
                if size in (2,4,8):assert address%min(size,4)==0,('unaligned M0 read',hex(address),size)
                if any(page<=address<page+4096 for page in pages):assert any(lo<=address and address+size<=hi for lo,hi in state['reads']),('read envelope',hex(address),size,state['row'])
        for page in pages:u.hook_add(UC_HOOK_MEM_READ,access,begin=page,end=page+4095)
        u.hook_add(UC_HOOK_MEM_WRITE,access)
        runtime_checks=collections.Counter();zero_checks=collections.Counter()
        def invoke(entry,args):
            saved={getattr(arm,'UC_ARM_REG_R'+str(i)):0xa1700000+i*0x1111 for i in range(4,12)}
            for reg,val in saved.items():u.reg_write(reg,val)
            for i,value in enumerate(args):u.reg_write(getattr(arm,'UC_ARM_REG_R'+str(i)),value)
            for reg,val in [(arm.UC_ARM_REG_SP,sp),(arm.UC_ARM_REG_LR,stop|1),(arm.UC_ARM_REG_XPSR,0x01000000),(arm.UC_ARM_REG_PRIMASK,0),(arm.UC_ARM_REG_CONTROL,0)]:u.reg_write(reg,val)
            u.emu_start(entry|1,stop,count=1000000)
            assert u.reg_read(arm.UC_ARM_REG_PC)==stop and u.reg_read(arm.UC_ARM_REG_SP)==sp
            assert all(u.reg_read(reg)==val for reg,val in saved.items()),('AAPCS',state['row'])
            assert u.reg_read(arm.UC_ARM_REG_PRIMASK)==u.reg_read(arm.UC_ARM_REG_CONTROL)==0
            return u.reg_read(arm.UC_ARM_REG_R0)
        for name in FUNCTIONS:
            key=(name,product['functions'][name]['sha256'])
            if key in seen:continue
            seen.add(key)
            if key in cached:
                reused+=cached[key]['ARM_calls'];progress.append(dict(function=name,profile=product['profile'],body_sha256=key[1],reused_prior_function_PASS=True,cases=cached[key]['cases']));save(out/'PROGRESS.json',progress);continue
            word=product['profile']>=8 or product['route'] in ('sdk-baseline','actual-native-baseline')
            for rownum,row in enumerate(grouped[name]):
                a=bytes.fromhex(row['left_hex']);b=bytes.fromhex(row['right_hex']);seed=bytes.fromhex(row['seed_hex']);n=row['count'];aa,ba=row['alignment'];banks=row['banks']
                ap=(0x20030000 if banks[0]=='S' else 0x101d0000)+64+aa;bp=(0x20032000 if banks[1]=='S' else 0x101d2000)+64+ba;dest=0x20034000+64+ba
                ab=a+(b'\0' if name!='memcmp' else b'');bb=b+(b'\0' if name!='memcmp' else b'')
                for page in pages:u.mem_write(page,b'\xa5'*4096)
                u.mem_write(ap,ab);u.mem_write(bp,bb)
                u.mem_write(dest,seed+b'\0')
                expected=bytes.fromhex(row['output_hex']) if row['output_hex'] is not None else None
                before=bytes(u.mem_read(dest-32,1600));want=bytearray(before)
                if expected is not None:want[32:32+len(expected)]=expected
                decisive=len(a)+1
                if name in ('strcmp','strncmp','memcmp'):
                    limit=n if name!='strcmp' else max(len(a),len(b))+1
                    decisive=next((i+1 for i,(x,y) in enumerate(zip(ab,bb)) if x!=y or (name!='memcmp' and x==0)),min(len(ab),len(bb)))
                    decisive=min(decisive,limit)
                    if name=='memcmp' and word:decisive=n
                elif name in ('strnlen','strncpy','strncat'):decisive=min(len(a)+1,n)
                def span(pointer,count,granule=False):
                    end=pointer+count
                    if granule and count:end=(end+3)&~3
                    return pointer,min(end,pointer+n) if granule and name in ('strncmp','memcmp','strncpy','strncat','strnlen') else end
                reads=[span(ap,decisive,word)]
                if name in ('strcmp','strncmp','memcmp'):reads+=[span(bp,decisive,word)]
                if name=='strncat':reads+=[(dest,((dest+len(seed)+4)&~3) if word else dest+len(seed)+1)]
                writes=[(sp-256,sp+8)]
                if expected is not None:
                    if name=='strncat':writes+=[(dest+len(seed),dest+len(expected))]
                    else:writes+=[(dest,dest+len(expected))]
                state.update(reads=reads,writes=writes,row=(product['profile'],name,row['index']))
                args=[ap,bp,n or 0] if name in ('strcmp','strncmp','memcmp') else [ap,n or 0,0] if name in ('strlen','strnlen') else [dest,ap,n or 0]
                wanted=dest if row['expected']=='destination' else row['expected']
                got=invoke(e.symbols[name],args)
                def normalized(x):return (x>0 and x<0x80000000)-(x>=0x80000000) if name in ('strcmp','strncmp','memcmp') else x
                assert normalized(got)==wanted,('return',state['row'],normalized(got),wanted)
                assert bytes(u.mem_read(ap,len(ab)))==ab and bytes(u.mem_read(bp,len(bb)))==bb,('input changed',state['row'])
                assert bytes(u.mem_read(dest-32,len(want)))==want,('destination/padding/canary',state['row'])
                checks[name]+=1;total+=1
                if name in ('strlen','strncmp','strncat','memcmp') and (rownum<8 or rownum>=len(grouped[name])-8):
                    if name=='strncat':u.mem_write(dest,seed+b'\0')
                    assert normalized(invoke(tail.symbols[name],args))==wanted,('runtime tail',state['row'])
                    assert bytes(u.mem_read(dest-32,len(want)))==want
                    runtime_checks[name]+=1;total+=1
            if name in ('strnlen','strncmp','memcmp','strncpy','strncat') and (name!='strncat' or product['profile']):
                state.update(reads=[],writes=[(sp-256,sp+8)],row=('unmapped-zero-count',product['profile'],name))
                opaque=0x70001000
                args=[opaque,0,0] if name=='strnlen' else [opaque,0x70002000,0]
                wanted=opaque if name in ('strncpy','strncat') else 0
                assert invoke(e.symbols[name],args)==wanted,('zero count touched pointer',state['row'])
                zero_checks[name]+=1;total+=1
            print(product['profile'],name,checks[name],'PASS',flush=True)
            progress.append(dict(function=name,profile=product['profile'],body_sha256=key[1],reused_prior_function_PASS=False,cases=checks[name]));save(out/'PROGRESS.json',progress)
        results.append(dict(profile=product['profile'],route=product['route'],calls=dict(checks),actual_runtime_tail_checks=dict(runtime_checks),unmapped_zero_count_checks=dict(zero_checks)))
    result=dict(status='PASS_GROUPED_SMOKE' if smoke else 'PASS_ALL_EIGHT_GROUPED_SEMANTICS',physical_IO=0,hardware_winner=None,ARM_calls=total+reused,new_ARM_calls=total,reused_prior_ARM_calls=reused,reuse=pin(reuse) if reuse else None,unique_function_bodies=len(seen),case_count=len(rows),results=results,runner=pin(Path(__file__)))
    save(out/('SMOKE.json' if smoke else 'RESULT.json'),result);return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain-bin',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--build-only',action='store_true');p.add_argument('--run-existing',action='store_true');p.add_argument('--smoke',action='store_true');p.add_argument('--reuse-passed',type=Path);a=p.parse_args()
    b=json.loads((a.output/'BUILD.json').read_text()) if a.run_existing else compile_package(a.toolchain_bin.resolve(),a.output.resolve())
    if not a.build_only:run_semantics(b,a.output,a.smoke,a.reuse_passed)
if __name__=='__main__':main()
