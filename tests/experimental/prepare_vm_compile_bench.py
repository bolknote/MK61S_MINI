#!/usr/bin/env python3
"""Prepare source-matched full compiler APPs, without modifying firmware code."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zlib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'tests/experimental'))
import m8_codec
from prepare_vm_scan_bench import SOURCES, replace_once

PROBE=r'''
#include <cstdio>
#include <vector>
#include "language_bytecode.hpp"
int main(int argc,char** argv) {
  if(argc!=4) return 2;
  FILE* file=std::fopen(argv[2],"rb");if(!file) return 2;
  std::vector<uint8_t> source(3585),image(8192);
  const size_t n=std::fread(source.data(),1,source.size(),file);std::fclose(file);
  if(n>=source.size()) return 2;
  const auto language=argv[1][0]=='b' ? language_vm::Language::BASIC : language_vm::Language::FOCAL;
  language_vm::ResourceSource resources={42,1};resources.mode=language_vm::ResourceMode::EMBEDDED;
  const auto sized=language_vm::compile(language,(const char*)source.data(),(uint16_t)n,
      nullptr,(uint16_t)image.size(),true,&resources);
  if(sized.error!=language_vm::Error::NONE) return 3;
  const auto emitted=language_vm::compile(language,(const char*)source.data(),(uint16_t)n,
      image.data(),(uint16_t)image.size(),true,&resources);
  if(emitted.error!=language_vm::Error::NONE) return 4;
  FILE* output=std::fopen(argv[3],"wb");if(!output) return 2;
  const size_t written=std::fwrite(image.data(),1,emitted.size,output);std::fclose(output);
  return written==emitted.size ? 0 : 5;
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--arm-toolchain-bin',type=Path,required=True)
    args=parser.parse_args()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    original=(ROOT/'code/language_bytecode.cpp').read_text()
    (out/'host_probe.cpp').write_text(PROBE)
    variants=('scalar','line_word','line_dsp')
    cases=[]
    for language,name in SOURCES:
        data=m8_codec.encode((ROOT/name).read_text(encoding='utf-8-sig'))
        path=out/(Path(name).stem+'.m8');path.write_bytes(data)
        cases.append({'language':language,'source':name,'data':data,'path':path})
    manifest=[]
    for variant_index,variant in enumerate(variants):
        folder=out/variant;folder.mkdir(exist_ok=True)
        text=original
        if variant_index:
            text=replace_once(text,
                "      while (cursor < source_ + length_ && *cursor != '\\r' && *cursor != '\\n') ++cursor;",
                f'      cursor+=vm_scan_candidates::line_{"word" if variant_index==1 else "dsp"}((const uint8_t*)cursor,(size_t)(source_+length_-cursor));')
        text='#define MK61_MATH_BACKEND 1\n#include "vm_scan_candidates.hpp"\n'+text
        # Match the shipped System compiler optimization; ordinary APP entry
        # and its transport are separate translation units built by the SDK.
        text='#if defined(__GNUC__) && !defined(__clang__)\n#pragma GCC optimize ("Oz")\n#endif\n'+text
        for language in ('basic','focal'):
            text=text.replace('CompileResult compile_'+language+'(',
                              '__attribute__((noinline)) CompileResult compile_'+language+'(')
        compiler=folder/'compiler.cpp';compiler.write_text(text)
        subprocess.run([shutil.which('clang++') or 'c++','-std=c++17','-O1',
            '-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',
            '-I'+str(ROOT/'code'),'-I'+str(ROOT/'tests/experimental'),
            out/'host_probe.cpp',compiler,'-o',folder/'host_probe'],check=True)
        for case in cases:
            image=folder/(Path(case['source']).stem+'.bvm')
            subprocess.run([folder/'host_probe',case['language'],case['path'],image],check=True)
            data=image.read_bytes()
            if variant_index:
                assert data==(out/'scalar'/image.name).read_bytes(), 'bytecode differs'
            else:
                case.update(image_bytes=len(data),image_sha256=hashlib.sha256(data).hexdigest(),
                            image_crc=zlib.crc32(data)&0xffffffff)
        for language in ('basic','focal'):
            app_dir=folder/language;app_dir.mkdir(exist_ok=True)
            selected=[case for case in cases if case['language']==language]
            header=[f'#define VM_COMPILE_FOCAL {int(language=="focal")}',
                f'#define VM_COMPILE_VARIANT {variant_index}',
                f'#define VM_COMPILE_IMAGE_CAPACITY {1024 if language=="focal" else 2304}',
                'struct CompileSource { const char* data; uint16_t length,image_bytes; uint32_t image_crc; };']
            for index,case in enumerate(selected):
                header.append(f'static const char compile_source_{index}[]={{'+','.join(str(x) for x in case['data'])+'};')
            header.append('static const CompileSource compile_sources[]={')
            for index,case in enumerate(selected):
                header.append('{compile_source_'+str(index)+','+
                    ','.join(str(x) for x in (len(case['data']),case['image_bytes'],case['image_crc']))+'},')
            header+=['};',f'static constexpr unsigned compile_source_count={len(selected)};']
            (app_dir/'vm_compile_fixture.hpp').write_text('\n'.join(header)+'\n')
            subprocess.run([sys.executable,ROOT/'tools/build_portable_app.py',
                '--name','VMCOMP','--shared-runtime','--source',ROOT/'tests/experimental/vm_compile_hil.cpp',
                '--source',compiler,'--source',ROOT/'tests/experimental/vm_compile_support.c',
                '--include',ROOT/'tests/experimental','--include',app_dir,
                '--arm-toolchain-bin',args.arm_toolchain_bin,'--output-dir',app_dir/'build'],check=True)
            manifest.append({'variant':variant,'language':language,
                'app':str(app_dir/'build/VMCOMP.APP'),
                'cases':[{k:v for k,v in case.items() if k not in ('data','path')} for case in selected]})
    (out/'manifest.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(original.encode()).hexdigest(),
        'apps':manifest,'scope':'full sizing+owned EMIT, compiler Oz/LTO in SRAM; excludes file/app loading, interpreter execution and USB'},indent=2)+'\n')


if __name__=='__main__': main()
