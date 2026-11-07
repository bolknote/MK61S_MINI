#!/usr/bin/env python3
"""Freeze the complete eight-function matrix. HOST only; no device discovery."""
import argparse,collections,hashlib,json,struct,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(HERE)]
from check_stm32_vectors import ElfImage
from cases import FUNCTIONS,ALIGNMENTS,registry

PROFILES=(0,1,2,4,8,16)
ROUTES=('standalone-sram','standalone-flash','shared-sram','shared-flash')
ROWS=210
BASE=0x10182000
LIMIT=0x101c0000
NONCE=0x202611070b000001
NAMESPACE='/M0LIBC-N7B1'
def pin(p):
    p=Path(p).resolve();raw=p.read_bytes()
    return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def save(p,j):
    with p.open('x') as f:json.dump(j,f,indent=2);f.write('\n')
def body(e,name):
    at=e.symbols[name]&~1;n=e.sizes[name]
    return next(e.data[o+at-v:o+at-v+n] for k,o,v,pa,size,mem,fl,a in e.segments if k==1 and v<=at and at+n<=v+size)
def request(t,route,batch,context=None):
    qualification=batch is None
    first=0 if qualification else batch*ROWS
    count=0 if qualification else min(ROWS,len(t['cases'])-first)
    assert 0<=route<4 and (qualification or 0<=first<len(t['cases']))
    if qualification:context=[0]*6
    assert context is not None and len(context)==6
    keys=b'' if qualification else b''.join(bytes.fromhex(c['key_hex']) for c in t['cases'][first:first+count])
    raw=struct.pack('<15I',0x38424c4d,1,0xffffffff if qualification else batch,route,first,count,NONCE&0xffffffff,NONCE>>32,*context,zlib.crc32(keys))
    return raw+struct.pack('<I',zlib.crc32(raw))+keys
def prepare(build_path,out,resident):
    out.mkdir(parents=True,exist_ok=False)
    build=json.loads(build_path.read_text())
    assert build['status']=='COMPILED_ALL_EIGHT_CANDIDATES_NOT_SEMANTICALLY_RUN'
    semantics=json.loads(build_path.with_name('RESULT.json').read_text())
    assert semantics['status']=='PASS_ALL_EIGHT_GROUPED_SEMANTICS'
    image=ElfImage(resident/'mk61s-picocalc-pico-h.elf')
    firmware=(resident/'mk61s-picocalc-pico-h.bin').read_bytes()
    manifest=json.loads((resident/'manifest.json').read_text())
    assert hashlib.sha256(firmware).hexdigest()==manifest['bin_sha256']
    table=body(image,'_ZN8picocalc14native_runtimeE');assert len(table)==104
    native=[]
    for i,name in enumerate(FUNCTIONS):
        raw=body(image,name)
        native.append(dict(entry=image.symbols[name]|1,bytes=len(raw),crc32=zlib.crc32(raw),sha256=hashlib.sha256(raw).hexdigest()))
    slots={'strlen':20,'strncmp':19,'strncat':21,'memcmp':25}
    for name,slot in slots.items():assert struct.unpack('<26I',table)[slot]==native[FUNCTIONS.index(name)]['entry']
    fixture=bytearray(b'\xff'*256);leaves=[]
    for op,name in enumerate(FUNCTIONS):
        group=[]
        for profile in PROFILES:
            product=next(p for p in build['products'] if p['profile']==profile and p['route']==('control' if not profile else 'core'))
            assert pin(product['ELF']['path'])==product['ELF']
            e=ElfImage(Path(product['ELF']['path']));raw=body(e,name)
            fixture.extend(b'\xff'*((-len(fixture))%16));offset=len(fixture);fixture.extend(raw)
            group.append(dict(profile=profile,offset=offset,bytes=len(raw),crc32=zlib.crc32(raw),sha256=hashlib.sha256(raw).hexdigest()))
        arena=sum((c['bytes']+15)&~15 for c in group)
        assert arena<=1536,(name,arena)
        leaves.append(group)
    pool={};pool_records=[]
    def operand(blob,alignment):
        key=(blob,alignment)
        if key not in pool:
            fixture.extend(b'\xa5'*16)
            fixture.extend(b'\xa5'*((alignment-len(fixture))%4))
            offset=len(fixture);fixture.extend(blob+b'\0');fixture.extend(b'\xa5'*16)
            pool[key]=dict(offset=offset,length=len(blob),alignment=alignment,crc32=zlib.crc32(blob+b'\0'))
            pool_records.append(pool[key])
        return pool[key]
    unique={};cases=[];logical=[]
    for row in registry(full_alignments=True):
        name=row['function'];aa,ba=row['alignment']
        if name in ('strlen','strnlen'):
            if ba:continue
        elif (aa,ba) not in ALIGNMENTS:continue
        a=bytes.fromhex(row['left_hex']);b=bytes.fromhex(row['right_hex']);n=row['count']
        if n is not None:a=a[:n];b=b[:n]
        key=(name,a,b,n,aa,ba,row['banks'],row['seed_hex'])
        if key not in unique:
            left,right=operand(a,aa),operand(b,ba)
            op=FUNCTIONS.index(name);banks={'SS':0,'SF':1,'FS':2,'FF':3}[row['banks']]
            seed=len(bytes.fromhex(row['seed_hex']));seed_index=(0,7,31).index(seed)
            repeats=max(16,min(4096,8192//(row['work']+16)))
            flags=op|(banks<<3)|(aa<<5)|(ba<<7)|(seed_index<<9)|(repeats<<16)
            expected=0 if row['expected']=='destination' else row['expected']
            descriptor=struct.pack('<8I',flags,0xffffffff if n is None else n,left['offset'],right['offset'],len(a)|(len(b)<<16),left['crc32'],right['crc32'],expected&0xffffffff)
            case=dict(row,index=len(cases),logical_indexes=[],left_hex=a.hex(),right_hex=b.hex(),left=left,right=right,key_hex=descriptor.hex(),repeats=repeats)
            unique[key]=len(cases);cases.append(case)
        physical=unique[key];cases[physical]['logical_indexes'].append(row['index']);logical.append(dict(logical_index=row['index'],physical_index=physical,length=row['length'],work=row['work'],function=name,mode=row['mode']))
    fixture.extend(b'\xff'*((-len(fixture))%256))
    assert BASE+((len(fixture)+4095)&~4095)<=LIMIT,(hex(BASE),len(fixture),hex(LIMIT))
    footer_at=manifest['firmware_integrity']['footer_offset'];footer=firmware[footer_at:footer_at+40]
    struct.pack_into('<4s7I',fixture,0,b'MLB8',1,len(fixture),BASE,len(cases),7,16,zlib.crc32(table))
    fixture[64:96]=bytes.fromhex(pin(build_path)['sha256'])
    fixture[96:128]=hashlib.sha256(firmware).digest()
    (out/'fixture.bin').write_bytes(fixture)
    fixture_pin=pin(out/'fixture.bin')
    plan=dict(status='HOST_COMPLETE_EIGHT_FUNCTION_MATRIX_NOT_HARDWARE_GO',physical_IO=0,functions=list(FUNCTIONS),profiles=list(PROFILES),routes=list(ROUTES),rounds=7,rows_per_APP=ROWS,
        metric='complete checked indirect-call loop in raw RP2040 1us ticks; no subtraction; strncat terminator reset in loop',
        repeats='max(16,min(4096,8192//(logical work+16))) fixed before timing; seven raw groups',
        effective_operand_dedup='truncate bounded inputs at count; preserve every byte within the count and every declared alignment/bank/seed; retain logical-to-physical weighting, not independent samples',
        workload='per-function inverse (logical length+1), normalize align/bank/pattern cases inside each length; sensitivity equal length and inverse work; no cross-function time score',
        selected_alignment_pairs=list(ALIGNMENTS),unary_source_alignments=[0,1,2,3],
        cases=cases,logical_map=logical,case_count=len(cases),logical_cases=len(logical),cases_by_function=dict(collections.Counter(c['function'] for c in cases)),
        fixture=fixture_pin,fixture_base=BASE,fixture_crc32=zlib.crc32(fixture),fixture_erase=[BASE,BASE+((len(fixture)+4095)&~4095)],
        prior_owned_strchr_erase=[0x10182000,0x10197000],extension_requires_independent_root_disposable_acceptance=[0x10197000,BASE+((len(fixture)+4095)&~4095)],protected_ranges=[[0x10180000,0x10182000],[0x101c0000,0x101e0000],[0x101fe000,0x10200000]],
        leaves=leaves,pool=pool_records,namespace=NAMESPACE,run_nonce=hex(NONCE),native=native,runtime_address=image.symbols['_ZN8picocalc14native_runtimeE']&~1,runtime_words=list(struct.unpack('<26I',table)),runtime_slots=slots,
        candidate_firmware=pin(resident/'mk61s-picocalc-pico-h.bin'),candidate_ELF=pin(resident/'mk61s-picocalc-pico-h.elf'),candidate_manifest=pin(resident/'manifest.json'),candidate_build=manifest['build_id'],candidate_crc=manifest['firmware_integrity']['crc32'],
        baseline_is_historical_only=True,fresh_handoff_required=True,footer_address=0x10000000+footer_at,footer_hex=footer.hex(),semantic_build=pin(build_path),semantic_result=pin(build_path.with_name('RESULT.json')),
        timed_APP_runs=4*((len(cases)+ROWS-1)//ROWS),qualified_routes=4,first_fault='save all previous and partial groups; never replay a failed case/job; stop',hardware_winner=None)
    save(out/'PLAN.json',plan)
    header=['/* Historical ELF binding only; requires fresh exact Root handoff/Go. */','#ifndef MB_BINDING_H','#define MB_BINDING_H','#include <stdint.h>',f'#define MB_NAMESPACE "{NAMESPACE}"']
    for k,v in dict(MB_FIXTURE_BASE=BASE,MB_FIXTURE_BYTES=len(fixture),MB_FIXTURE_CRC=zlib.crc32(fixture),MB_FOOTER=plan['footer_address'],MB_RUNTIME=plan['runtime_address'],MB_CASES=len(cases),MB_TOKEN_A=NONCE&0xffffffff,MB_TOKEN_B=NONCE>>32).items():header.append('#define %s 0x%xu'%(k,v))
    def array(ty,name,values,shape=''):
        header.append('static const '+ty+' '+name+shape+'='+values+';')
    array('uint32_t','mb_runtime','{'+','.join(hex(v)+'u' for v in plan['runtime_words'])+'}','[26]')
    array('uint8_t','mb_footer','{'+','.join(str(v) for v in footer)+'}','[40]')
    for field in ('entry','bytes','crc32'):array('uint32_t','mb_native_'+field,'{'+','.join(str(v[field])+'u' for v in native)+'}','[8]')
    for field in ('offset','bytes','crc32'):array('uint32_t','mb_leaf_'+field,'{'+','.join('{'+','.join(str(v[field])+'u' for v in group)+'}' for group in leaves)+'}','[8][6]')
    array('int8_t','mb_slots','{'+','.join(str(slots.get(name,-1)) for name in FUNCTIONS)+'}','[8]')
    header.append('#endif');(out/'binding.h').write_text('\n'.join(header)+'\n')
    jobs=out/'jobs';jobs.mkdir()
    for route in range(4):
        (jobs/('q%d.bin'%route)).write_bytes(request(plan,route,None))
        # Context is deliberately unbound until actual qualification.
    save(out/'SUMMARY.json',dict(status=plan['status'],physical_IO=0,plan=pin(out/'PLAN.json'),fixture=fixture_pin,binding=pin(out/'binding.h'),cases=len(cases),logical_cases=len(logical),pool_bytes=len(fixture),timed_APP_runs=plan['timed_APP_runs']))
    print(json.dumps(json.loads((out/'SUMMARY.json').read_text()),indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--resident',type=Path,required=True);a=p.parse_args();prepare(a.build,a.output,a.resident)
