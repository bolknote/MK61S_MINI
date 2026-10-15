#!/usr/bin/env python3
"""Compare decode cursor passing by reference vs value in a private APP."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from prepare_zx0_prototypes import ROOT,prepare,replace_once


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--corpus-manifest',type=Path,required=True)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=prepare(out/'variants');folder=out/'ZX0REG';folder.mkdir(exist_ok=True)
    source=(out/'variants/word.cpp').read_text();end=source.index('/*\n * ZX0 format:',source.index('} // namespace zx0'))
    source=source[:end]
    source=source.replace('zx0_private_word','zx0_private_register').replace('"word.hpp"','"register.hpp"')
    source='#include "zx0_register_candidate.hpp"\n'+source
    source=replace_once(source,'static bool copy_match(','static inline __attribute__((always_inline)) bool copy_match(')
    source=replace_once(source,'return zx0_candidates::copy_word(output, begin, end, offset, length);',
        'return zx0_register_candidate::copy_match(output, begin, end, offset, length);')
    source+='''
namespace zx0_prototypes {
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noipa,aligned(16)))
#else
__attribute__((noinline,aligned(16)))
#endif
bool decode_register(const zx0::Input& input,u32 size,u8* output,u32 capacity,u32& written) {
  const zx0_private_register::Input source={input.context,input.next};
  return zx0_private_register::decode(source,size,output,capacity,written);
}
}
'''
    (out/'variants/register.hpp').write_text((out/'variants/word.hpp').read_text().replace('zx0_private_word','zx0_private_register').replace('PRIVATE_WORD','PRIVATE_REGISTER'))
    (out/'variants/register.cpp').write_text(source)
    api='#include "zx0_prototypes.hpp"\nnamespace zx0_prototypes {bool decode_register(const zx0::Input&,u32,u8*,u32,u32&);}\n'
    (folder/'register_api.hpp').write_text(api)
    test=(ROOT/'tests/experimental/zx0_candidates_self_test.cpp').read_text()
    test='#include "register_api.hpp"\n#include "zx0_register_candidate.hpp"\n'+test
    test=test.replace('zx0_prototypes::decode_dsp','zx0_prototypes::decode_register').replace('k::copy_word(', 'zx0_register_candidate::copy_match(')
    (folder/'self_test.cpp').write_text(test)
    command=['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-fno-builtin','-fsanitize=address,undefined',
        '-fno-sanitize-recover=all','-fno-omit-frame-pointer','-I'+str(ROOT/'code'),'-I'+str(ROOT/'tests/experimental'),'-I'+str(folder),
        folder/'self_test.cpp',ROOT/'code/zx0.cpp',ROOT/'code/zx0_encode.cpp',
        *[out/'variants'/(v+'.cpp') for v in ('scalar','word','dsp','register')],'-o',folder/'self_test']
    subprocess.run(list(map(str,command)),check=True);subprocess.run([str(folder/'self_test')],check=True)
    base=json.loads(args.corpus_manifest.read_text());old=Path(base['jobs'][1]['app']).parents[1]/'zx0_bench_fixture.hpp'
    header=old.read_text();start=header.index('static const u8 source_fixture')
    cases=[dict(family=3,size=n,parameter=0,pattern=pattern) for n in (4,16,64,256,512) for pattern in range(6)]
    lines=['#define ZX0_BENCH_KIND 2','struct BenchCase {unsigned family,size,parameter,pattern;};','static const BenchCase bench_cases[]={']
    lines+=['{'+','.join(str(c[k]) for k in ('family','size','parameter','pattern'))+'},' for c in cases]
    lines+=['};',f'static constexpr unsigned bench_case_count={len(cases)};']
    (folder/'zx0_bench_fixture.hpp').write_text('\n'.join(lines)+'\n'+header[start:])
    bench=(ROOT/'tests/experimental/zx0_codec_hil.cpp').read_text()
    bench='#include "register_api.hpp"\n'+bench
    bench=replace_once(bench,'zx0_prototypes::decode_scalar,zx0_prototypes::decode_word};',
        'zx0_prototypes::decode_scalar,zx0_prototypes::decode_word,zx0_prototypes::decode_register};')
    bench=replace_once(bench,'zx0_prototypes::encode_scalar,zx0_prototypes::encode_word,zx0_prototypes::encode_dsp};',
        'zx0_prototypes::encode_scalar};')
    bench=replace_once(bench,'const unsigned count=c.family==3?2:3;','const unsigned count=3;')
    (folder/'benchmark.cpp').write_text(bench)
    command=[sys.executable,ROOT/'tools/build_portable_app.py','--name','ZX0REG','--shared-runtime',
        '--source',folder/'benchmark.cpp','--include',ROOT/'tests/experimental','--include',folder,
        '--arm-toolchain-bin',args.arm_toolchain_bin,'--output-dir',folder/'build']
    for variant in ('scalar','word','register'):command+=['--source',out/'variants'/(variant+'.cpp')]
    subprocess.run(list(map(str,command)),check=True)
    manifest.update(corpus=base['corpus'],jobs=[dict(name='ZX0REG',kind=2,app=str(folder/'build/ZX0REG.APP'),cases=cases,
        variants_by_family={'3':['scalar','word','register_word']})])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
