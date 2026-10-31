#!/usr/bin/env python3
"""Freeze the concrete source controls and generate isolated full-function probes."""
from pathlib import Path
import hashlib,json,re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=ROOT/'.build/picocalc-apps-lcd-chain-20261021/source/code'
V3=ROOT/'.build/rp2040-interpolator-20261023/combined-v3-v1/math/source'

def extract(text,name):
    match=re.search(r'(?m)^[^\n]*\b'+re.escape(name)+r'\([^;{}]*\)\s*\{',text)
    assert match,name
    begin=match.start();p=text.index('{',match.start());depth=1;q=p+1
    while depth:
        depth+=(text[q]=='{')-(text[q]=='}');q+=1
    return text[begin:q]+'\n'

def main():
    refs={}
    for source in (OLD/'native_eabi_m0.cpp',OLD/'native_eabi_m0_kernels.inc',
                   ROOT/'code/native_eabi_m0.S',OLD/'native_eabi_m0_log_table.inc',
                   ROOT/'code/native_eabi_m0_pow_fast.inc',V3/'kernels.cpp',V3/'tables.inc',
                   V3/'kernels.h',V3/'baseline_sqrt_table.inc',V3/'divide.S'):
        refs[str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
    (HERE/'source-pins.json').write_text(json.dumps(refs,indent=2)+'\n')
    for name in ('tables.inc','kernels.h','baseline_sqrt_table.inc','divide.S'):
        (HERE/name).write_bytes((V3/name).read_bytes())
    (HERE/'native_eabi_m0_log_table.inc').write_bytes((OLD/'native_eabi_m0_log_table.inc').read_bytes())
    native=(OLD/'native_eabi_m0.cpp').read_text()
    common='#pragma once\n#include <stdint.h>\nusing U=uint64_t;\n'
    common+='struct D {static constexpr U Hidden=U(1)<<52,Fraction=Hidden-1,Sign=U(1)<<63,Magnitude=Sign-1,Infinity=U(0x7ff)<<52,Quiet=U(1)<<51;};\n'
    common+='static inline U bits(double d){U v;__builtin_memcpy(&v,&d,8);return v;}\nstatic inline double real(U v){double d;__builtin_memcpy(&d,&v,8);return d;}\n'
    common+='struct Product {U high,low;};\n'
    for name in ('clz32','clz64','wide32','multiply','exp_high_product'):
        common+=extract(native,name)
    common=common.replace('unsigned clz32(','static inline unsigned clz32(').replace('unsigned clz64(','static inline unsigned clz64(')
    (HERE/'integer.inc').write_text(common)
    seed=(V3/'kernels.cpp').read_text().replace('#define ENTRY extern "C" __attribute__((noipa))',
        '#define ENTRY extern "C" __attribute__((always_inline)) inline')
    (HERE/'seed-inline.inc').write_text(seed)
    kernel=(OLD/'native_eabi_m0_kernels.inc').read_text()
    lookup='#include "api.h"\n#include "integer.inc"\n#include "native_eabi_m0_log_table.inc"\n'
    for name in ('math62_product','math62_right','math62_third','math62_pack',
                 'math62_log_near_one','math62_log_correction','math62_pack96','math62_log_interval'):
        lookup+=extract(kernel,name)
    lookup+='extern "C" void fo_lookup_setup(void) {auto p=(volatile uint32_t*)0xd00000c0;p[11]=8U|(4U<<5)|(11U<<10);p[2]=(uint32_t)(uintptr_t)log_table;}\n'
    ln=extract(kernel,'mk61_m0_ln')
    ln=ln.replace('__attribute__((optimize("Os"))) double mk61_m0_ln(double x)',
        'template<bool HW> __attribute__((always_inline)) inline double ln_core(double x)')
    ln=ln.replace('const U b=bits(x);','U b=bits(x);int adjustment=0;\n'
        '  if(!(b&D::Magnitude))return real(D::Sign|D::Infinity);\n'
        '  if((b&D::Magnitude)>D::Infinity)return real(b|D::Quiet);\n'
        '  if(b&D::Sign)return real(D::Infinity|D::Quiet);\n'
        '  if(b==D::Infinity)return x;\n'
        '  if(!(b>>52)){const unsigned shift=clz64(b)-11;b=((b<<shift)&D::Fraction)|D::Hidden;adjustment=-int(shift);}')
    ln=ln.replace('const int k=int((b>>52)&0x7FFU)-1023;',
                  'const int k=int((b>>52)&0x7FFU)-1023+adjustment;')
    ln=ln.replace('const Product product=multiply(m,log_table[j][0]);',
        'const U* row;\n  if constexpr(HW){auto p=(volatile uint32_t*)0xd00000c0;p[0]=uint32_t(b>>32);row=(const U*)(uintptr_t)p[8];}\n'
        '  else row=log_table[j];\n  const Product product=multiply(m,row[0]);')
    ln=ln.replace('log_table[j][1]','row[1]')
    lookup+=ln
    lookup+='extern "C" __attribute__((noipa)) U fo_ln_cpu(U x,U){return bits(ln_core<false>(real(x)));}\n'
    lookup+='extern "C" __attribute__((noipa)) U fo_ln_interp(U x,U){return bits(ln_core<true>(real(x)));}\n'
    (HERE/'lookup.cpp').write_text(lookup)
    asm=(ROOT/'code/native_eabi_m0.S').read_text()
    assert (ROOT/'code/native_eabi_m0_sqrt64_table.inc').read_bytes()==(V3/'baseline_sqrt_table.inc').read_bytes()
    macros=asm[asm.index('.macro sqrt64_polynomial'):asm.index('function mk61_m0_sqrt\n')]
    body=asm[asm.index('function mk61_m0_sqrt\n'):asm.index('end mk61_m0_sqrt\n')]
    rootasm='.syntax unified\n.cpu cortex-m0plus\n.thumb\n'+macros
    for suffix in ('base','new_cpu','new_interp','skip_refine'):
        name='fo_sqrt_'+suffix
        part=body.replace('function mk61_m0_sqrt\n',f'.section .text.{name},"ax",%progbits\n.global {name}\n.type {name},%function\n.thumb_func\n{name}:\n')
        part=part.replace('bl mk61_m0_sqrt_slow','bl '+name+'_slow')
        if suffix!='base':
            part=part.replace('mov lr,r4\n','sub sp,#4\n str r4,[sp]\n',1)
            begin=part.index(' // Both polynomials preserve')
            end=part.index(' sqrt64_square32 r1',begin)
            part=part[:begin]+f''' // The complete original correction and rounding tail follows this seed.
 adds r2,r3,#1
 movs r3,#1
 ands r2,r3
 movs r3,#0
 lsls r1,#12
 lsrs r1,#12
 movs r7,#1
 lsls r7,#20
 orrs r1,r7
 bl fo_sqrt_seed_{'interp' if suffix=='new_interp' else 'cpu'}
 mov r7,r1
 mov r12,r0
 ldr r2,[sp]
 mov lr,r2
 add sp,#4
 mov r0,r12
'''+part[end:]
            table=part.index('\n.align 5\n.Lsqrt64_coefficients:')
            part=part[:table]+'\n'
            if suffix=='skip_refine':
                begin=part.index(' sqrt64_square32 r1')
                end=part.index(' sqrt64_square32 r7',begin)
                part=part[:begin]+' lsrs r1,r0,#11\n lsls r0,#21\n'+part[end:]
        part=part.replace('.Lsqrt64_','.Lfo_'+suffix+'_')
        rootasm+=part+f'.size {name},.-{name}\n'
    (HERE/'sqrt-full.S').write_text(rootasm.replace('native_eabi_m0_sqrt64_table.inc','baseline_sqrt_table.inc'))
    roots='#include "api.h"\n#include "integer.inc"\n#include "seed-inline.inc"\n'
    roots+='extern "C" void fo_root_setup(void){interp_blend_setup();}\n'
    roots+='extern "C" U fo_sqrt_seed_cpu(U m,U parity){return cpu_sqrt_seeds(m,parity);}\n'
    roots+='extern "C" U fo_sqrt_seed_interp(U m,U parity){return interp_sqrt_seeds(m,parity);}\n'
    roots+='template<U(*F)(U,U)> static U sqrt_slow(U a){const U m=a&D::Magnitude;if(!m)return a;if(m>=D::Infinity)return m==D::Infinity && !(a&D::Sign)?a:a|D::Infinity|D::Quiet;if(a&D::Sign)return D::Infinity|D::Quiet;const unsigned shift=clz64(m)-11;const int e=-1022-int(shift);const unsigned odd=unsigned(e)&1U;const U s=m<<shift;const U result=F((s&D::Fraction)|(U(1023+odd)<<52),0);return result-(U(-(e-int(odd))/2)<<52);}\n'
    for suffix in ('base','new_cpu','new_interp','skip_refine'):
        roots+=f'extern "C" U fo_sqrt_{suffix}_slow(U a){{return sqrt_slow<fo_sqrt_{suffix}>(a);}}\n'
    powtext=(ROOT/'code/native_eabi_m0_pow_fast.inc').read_text()
    boundary=extract(powtext,'pow_rsqrt_boundary')
    boundary=boundary.replace(',section(".m0_pow_extension")','')
    roots+=boundary
    fn=extract(powtext,'pow_rsqrt')
    start=fn.index('  const unsigned parity=')
    end=fn.index('  const U argument=',start)
    fn=fn[:start]+'''  const unsigned parity=unsigned(e)&1U;
  const uint32_t seed=SEED==0?uint32_t(current_rsqrt_seed(m,parity)):
    SEED==1?uint32_t(cpu_rsqrt_seed(m,parity)):
    SEED==2?uint32_t(interp_rsqrt_seed(m,parity)):
    uint32_t(linear_seed<false>(m,parity,linear_rsqrt_seeds))<<1;
'''+fn[end:]
    fn=re.sub(r'__attribute__\(\(.*?\)\) double pow_rsqrt\(double x\)',
              'template<unsigned SEED> __attribute__((always_inline)) inline double rsqrt_core(double x)',fn,count=1)
    fn=fn.replace('const U b=bits(x);U m=',
        'const U b=bits(x);\n  if(!(b&D::Magnitude))return real((b&D::Sign)|D::Infinity);\n'
        '  if((b&D::Magnitude)>D::Infinity)return real(b|D::Quiet);\n'
        '  if(b&D::Sign)return real(D::Infinity|D::Quiet);\n'
        '  if(b==D::Infinity)return 0.0;\n  U m=')
    fn=fn.replace('if(compare==2) return mk61_m0_cr_pow(x,-0.5);',
                  'if(compare==2) return real(D::Infinity|D::Quiet); // Outside the proved normalized boundary range.')
    roots+=fn
    for i,suffix in enumerate(('base','new_cpu','new_interp','skip_refine')):
        roots+=f'extern "C" __attribute__((noipa)) U fo_rsqrt_{suffix}(U x,U){{return bits(rsqrt_core<{i}>(real(x)));}}\n'
    (HERE/'roots.cpp').write_text(roots)

if __name__=='__main__':main()
