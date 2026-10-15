#!/usr/bin/env python3
"""Build ordinary ZX0 benchmark APPs and freeze their source/data provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from prepare_zx0_prototypes import ROOT,prepare


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True,help='uncompressed ARM APP .bin, used as a bounded data corpus')
    p.add_argument('--source',type=Path,default=ROOT/'programs/games/Turochamp/search.tbi')
    p.add_argument('--codec-scope',choices=('all','encode-focus'),default='all',
        help='focused encoder follow-up avoids repeating already measured kernels/decoders')
    args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    snapshot=prepare(out/'variants')
    sys.path.insert(0,str(ROOT/'tools'));import m8_codec
    source=m8_codec.encode(args.source.read_text(encoding='utf-8-sig'))[:512]
    image=args.image.read_bytes()[:512];assert len(image)==512 and source
    jobs=[]
    kernels=[]
    for n in (0,1,2,3,4,7,8,15,16,31,64,128,512):
        for offset in (1,2,3,4,7,16,31,256):kernels.append((0,n,offset,0))
    for n in (0,1,3,4,7,16,64,128,512):
        for pattern in range(4):kernels.append((1,n,256,pattern))
    for n in (0,1,2,3,4,7,16,31,127,128,129,255,256,511):
        for pattern in range(4):kernels.append((2,n,0,pattern))
    codecs=[]
    for family in (3,4):
        for n in (4,16,64,256,512):
            for pattern in range(6):codecs.append((family,n,0,pattern))
    for n in (256,512):
        for pattern in range(6):codecs.append((4,n,1,pattern))
    if args.codec_scope=='encode-focus':
        codecs=[(4,n,0,pattern) for n in (16,64) for pattern in (4,5)]
        codecs += [(4,512,0,pattern) for pattern in (3,4,5)]
        codecs += [(4,512,1,pattern) for pattern in (2,4,5)]
    for kind,name,cases,source_name in ((0,'ZX0KERN',kernels,'zx0_kernel_hil.cpp'),(1,'ZX0CODEC',codecs,'zx0_codec_hil.cpp')):
        folder=out/name;folder.mkdir(exist_ok=True)
        header=[f'#define ZX0_BENCH_KIND {kind}',
            'struct BenchCase {unsigned family,size,parameter,pattern;};',
            'static const BenchCase bench_cases[]={']
        header+=['{'+','.join(map(str,row))+'},' for row in cases]
        header+=['};',f'static constexpr unsigned bench_case_count={len(cases)};']
        if kind:
            for label,data in (('source',source),('image',image)):
                header.append('static const u8 '+label+'_fixture[]={'+','.join(map(str,data))+'};')
        (folder/'zx0_bench_fixture.hpp').write_text('\n'.join(header)+'\n')
        if kind:
            # The chosen greedy scratch size must accept this exact corpus;
            # a valid bounded encoder may reject an insufficient token plan.
            host=['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-fno-builtin',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'code'),'-I'+str(ROOT/'tests/experimental'),'-I'+str(folder),
                ROOT/'tests/experimental/zx0_corpus_self_test.cpp',ROOT/'code/zx0.cpp',ROOT/'code/zx0_encode.cpp',
                *[out/'variants'/(v+'.cpp') for v in ('scalar','word','dsp')],'-o',folder/'corpus-self-test']
            subprocess.run(list(map(str,host)),check=True)
            subprocess.run([str(folder/'corpus-self-test')],check=True)
        command=[sys.executable,ROOT/'tools/build_portable_app.py','--name',name,'--shared-runtime',
            '--source',ROOT/'tests/experimental'/source_name,'--include',ROOT/'tests/experimental','--include',folder,
            '--arm-toolchain-bin',args.arm_toolchain_bin,'--output-dir',folder/'build']
        if kind:
            for variant in ('scalar','word','dsp'):command+=['--source',out/'variants'/(variant+'.cpp')]
        subprocess.run(list(map(str,command)),check=True)
        jobs.append({'name':name,'kind':kind,'app':str(folder/'build'/(name+'.APP')),
            'cases':[dict(zip(('family','size','parameter','pattern'),row)) for row in cases]})
    snapshot.update(jobs=jobs,codec_scope=args.codec_scope,corpus={label:{'path':str(path.resolve()),'prefix_bytes':len(data),'prefix_sha256':hashlib.sha256(data).hexdigest()}
        for label,path,data in (('source',args.source,source),('image',args.image,image))})
    (out/'manifest.json').write_text(json.dumps(snapshot,indent=2)+'\n')


if __name__=='__main__':main()
