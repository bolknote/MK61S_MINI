#!/usr/bin/env python3
"""Build one source-independent linked VM image from a JSON member manifest.

Example: {"entry":1,"members":[{"symbol":1,"language":"basic","path":"a.tbi"}]}.
Paths are relative to the manifest. Aliases of the same file share its image.
The image is experimental: stock firmware does not open LVP1 files yet.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest',type=Path)
    p.add_argument('-o','--output',type=Path,required=True)
    p.add_argument('--compiler',default=os.environ.get('CXX','c++'))
    a=p.parse_args()
    try:
        data=json.loads(a.manifest.read_text())
        members=data['members']
        if not isinstance(members,list) or not 1<=len(members)<=64:raise ValueError('members must contain 1..64 entries')
        arguments=[];sources={};symbols=set()
        for member in members:
            symbol=member['symbol'];language=member['language'];path=(a.manifest.parent/member['path']).resolve(strict=True)
            if type(symbol) is not int or not 0<symbol<=0xffffffff or symbol in symbols:raise ValueError('symbols must be unique positive uint32 values')
            if language not in ('basic','focal'):raise ValueError('language must be basic or focal')
            symbols.add(symbol);key=(language,path)
            if key not in sources:sources[key]=len(sources)+1
            arguments.extend((str(symbol),str(sources[key]),language,str(path)))
        entry=data['entry']
        if type(entry) is not int or entry not in symbols:raise ValueError('entry must name a member')
        protected=[a.manifest.resolve(),*(path for _,path in sources)]
        if any(a.output.resolve()==path or (a.output.exists() and a.output.samefile(path)) for path in protected):
            raise ValueError('output must not overwrite the manifest or a source file')
        with tempfile.TemporaryDirectory(prefix='mk61-linked-builder-') as temporary:
            tool=Path(temporary)/'builder'
            subprocess.run([a.compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-I'+str(ROOT/'code'),'-I'+str(ROOT/'tools'),str(ROOT/'tools/build_vm_program.cpp'),
                str(ROOT/'code/language_linked_program.cpp'),str(ROOT/'code/language_bytecode.cpp'),
                str(ROOT/'code/language_vm.cpp'),'-o',str(tool)],check=True)
            subprocess.run([str(tool),str(a.output),str(entry),*arguments],check=True)
    except (KeyError,TypeError,ValueError,OSError) as error:p.error(str(error))

if __name__=='__main__':main()
