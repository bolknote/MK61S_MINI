#!/usr/bin/env python3
"""Four normal SDK packed APPs for the one complete eight-function campaign."""
import argparse,contextlib,importlib.util,io,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'tests')]
from prepare import pin,save,body,FUNCTIONS,ROUTES
from check_stm32_vectors import ElfImage
def build(template,tc,out):
    t=json.loads((template/'PLAN.json').read_text());out.mkdir(parents=True,exist_ok=False)
    assert pin(t['fixture']['path'])==t['fixture']
    spec=importlib.util.spec_from_file_location('m0_batch_app_builder',ROOT/'tools/apps/portable/build_portable_app.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    original=builder.run;products=[]
    for i,route in enumerate(ROUTES):
        folder=out/route;commands=[]
        def run(argv):
            argv=list(map(str,argv))
            if '-c' in argv:argv+=['-DMB_CODE_FLASH='+str(i&1),'-fno-lto']
            commands.append(argv);return original(argv)
        args=argparse.Namespace(target='picocalc-pico-h',name='BATCH0',source=[HERE/'carrier.c'],system=None,
            shared_runtime=i>=2,text_only=False,no_ui_fonts=False,local_float_math=False,local_float_math_mask=None,
            language_vm_compiler=False,split_language_vm=False,include=[template],library=['-lc'],output_dir=folder,
            arm_toolchain_bin=tc,packer=ROOT/'tools/apps/packer/mk61_module_pack.py',rustc=None,handled_magic=None,m0_libc_candidate=0)
        log=io.StringIO();builder.run=run
        try:
            with contextlib.redirect_stdout(log):report=builder.build(args)
        finally:
            builder.run=original;folder.mkdir(parents=True,exist_ok=True);(folder/'build.log').write_text(log.getvalue());save(folder/'COMMANDS.json',commands)
        e=ElfImage(folder/'BATCH0.elf')
        assert report['memory_bytes']<=20480,report
        publics={n:dict(entry=e.symbols[n],bytes=len(body(e,n)),sha256=__import__('hashlib').sha256(body(e,n)).hexdigest()) for n in FUNCTIONS}
        product=dict(route=route,route_index=i,shared_runtime=i>=2,code_Flash=bool(i&1),APP=pin(folder/'BATCH0.APP'),ELF=pin(folder/'BATCH0.elf'),report=report,publics=publics,commands=pin(folder/'COMMANDS.json'))
        products.append(product);print(route,report['memory_bytes'],'loaded bytes',flush=True)
    result=dict(status='FOUR_REAL_PACKED_APPS_ALL_EIGHT_HOST_BUILT_NOT_GO',physical_IO=0,plan=pin(template/'PLAN.json'),binding=pin(template/'binding.h'),products=products,
        source_pins=[pin(HERE/n) for n in ['carrier.c','build_apps.py','prepare.py']]+[pin(ROOT/n) for n in ['sdk/portable/memory.c','sdk/portable/start.c','sdk/portable/shared_runtime.c','sdk/portable/system/runtime.S','tools/apps/portable/build_portable_app.py']])
    save(out/'BUILD.json',result)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--template',type=Path,required=True);p.add_argument('--toolchain-bin',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.template,a.toolchain_bin,a.output)
