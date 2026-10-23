"""Compare isolated cache models with real ROM and both memory placements."""

import argparse
_checkpoint_parser = argparse.ArgumentParser(description=__doc__)
_checkpoint_parser.add_argument("--work", required=True, help="Existing private work directory; see README")
_checkpoint_args = _checkpoint_parser.parse_args()
from array import array
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

root=Path.cwd();work=Path(_checkpoint_args.work).resolve()
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ

parent=root/'.build/m0-stable-arena-v77-20261021'
tree=ast.parse((parent/'cache-probe-extended.py').read_text())
nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in ('Cache','check_model')]
namespace=dict(Counter=Counter)
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'validated-cache-model','exec'),namespace)
Cache=namespace['Cache'];namespace['check_model']()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
benchmark=root/'.build/m0-balanced-timing-v87-20261022/benchmark.json'
config=json.loads(benchmark.read_text())
bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
numeric_parent=root/'.build/m0-pow-final-parent-v110-20261023'
images=dict(V122=work/'firmware/mk61s-picocalc-pico-h.elf')
matrix=dict(V122=json.loads((work/'instruction-matrix.json').read_text()))
parent_report=numeric_parent/'cache-probe.json'
previous=json.loads(parent_report.read_text())
assert previous['model_source_sha256']==sha(parent/'cache-probe-extended.py')
parent_rows=[r for r in previous['groups'] if r['image']=='V110']
assert len(parent_rows)==19
for row in parent_rows:
    assert row['elf_sha256']==sha(numeric_parent/'firmware/mk61s-picocalc-pico-h.elf')
    assert sha(root/row['trace']['path'])==row['trace']['sha256']
rows=[]
for label,elf in images.items():
    machine=Machine(elf,True,stack_bytes=16384,instruction_budget=20000000,bootrom=bootrom)
    assert not machine.rom_models
    for index in sorted(set([18,47,115,116,117,118]+[c['index'] for c in config['chunks'] if c['operation'] in ('sqrt','ln','log10')])):
        chunk=config['chunks'][index]
        input_path=Path(chunk['input'])
        assert sha(input_path)==chunk['input_sha256']
        trace=array('I');counts=Counter()
        def access(address,size):
            if 0x10000000<=address<0x10200000:
                for word in range(address>>2,(address+size+3)>>2):trace.append(word)
        def code(_uc,address,size,_user):
            access(address,size)
            counts['instructions']+=1
        def read(_uc,_access,address,size,_value,_user):
            if 0x10000000<=address<0x10200000:counts['flash_data_reads']+=1
            access(address,size)
        hooks=[machine.uc.hook_add(UC_HOOK_CODE,code),machine.uc.hook_add(UC_HOOK_MEM_READ,read)]
        machine.uc.ctl_flush_tb()
        vectors=list(struct.iter_unpack('<3Q',input_path.read_bytes()[32:]))
        try:
            for a,b,expected in vectors:
                got=machine.call(chunk['own_symbol'],a,b)[0]
                assert got==expected,(label,index,hex(a),hex(b))
        finally:
            for hook in hooks:machine.uc.hook_del(hook)
        assert counts['instructions']/len(vectors)==matrix[label]['chunks'][index]['mean_instructions']['own'],(label,index,'Trace counter differs from independent matrix')
        trace_path=work/f'cache-final-trace-{label.lower()}-{index:03d}.zlib'
        trace_path.write_bytes(zlib.compress(trace.tobytes()))
        variants=[]
        for policy in ('LRU','FIFO'):
            for whole in (True,False):
                cache=Cache(policy,whole)
                for _ in range(2):
                    for word in trace:cache.access(word)
                cache.counts.clear()
                for word in trace:cache.access(word)
                variants.append(dict(policy=policy,fill='whole_8byte_line' if whole else 'requested_4byte_word',
                    **cache.counts,misses_per_call=cache.counts['misses']/len(vectors)))
        row=dict(image=label,elf_sha256=sha(elf),index=index,operation=chunk['operation'],stream=chunk['stream'],
                 cases=len(vectors),mean_instructions=counts['instructions']/len(vectors),
                 flash_data_reads_per_call=counts['flash_data_reads']/len(vectors),
                 trace=dict(path=str(trace_path.relative_to(root)),sha256=sha(trace_path)),models=variants)
        rows.append(row)
        print(label,index,chunk['operation'],[v['misses_per_call'] for v in variants],flush=True)
baseline={r['index']:r for r in parent_rows}
differences=[]
for row in rows:
    if row['image']=='V110':continue
    before=[v['misses_per_call'] for v in baseline[row['index']]['models']]
    after=[v['misses_per_call'] for v in row['models']]
    if before!=after:differences.append(dict(image=row['image'],index=row['index'],before=before,after=after))
report=dict(status='PASS_MODELED_NOT_HARDWARE',groups=rows,differences_vs_actual_ROM_V110=differences,baseline_report=dict(path=str(parent_report.relative_to(root)),sha256=sha(parent_report)),
    bootrom_sha256=sha(bootrom),sdk_rom_intrinsic_models=[],benchmark_sha256=sha(benchmark),
    model_source_sha256=sha(parent/'cache-probe-extended.py'),producer_sha256=sha(__file__),
    assumptions='Same previously checked 16 KiB / two-way / 8-byte-line cache geometry; LRU/FIFO replacement and whole-line/per-word fills are explicit model assumptions. These are not claims about undocumented prefetch or replacement.',
    scope='Exact ARM instruction/data traces and exact results on the recorded finite groups per image, including every ln/log10 stream and the three difficult pow streams, with actual ROM and linked memory code. Two warm passes then a measured third pass. Only XIP accesses enter the cache model. Excludes caller prefetch, IRQs, other-core traffic and Qfplib batches. Not measured XIP counters or physical speed evidence.',
    physical_timing_available=False,goal_complete=False)
(work/'cache-probe.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(rows),'exact-result traces; instruction totals match the independent matrix; modeled differences:',len(differences),flush=True)
