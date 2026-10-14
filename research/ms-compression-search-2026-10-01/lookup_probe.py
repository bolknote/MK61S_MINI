"""Use existing 2F 7r hex formatting as a native six-symbol dictionary read.

The lookup table is program data. R0..R3 receive normal packed 24-bit integers;
they are not machine-code words. This is a reader probe, not a byte writer.
"""
import json
from pathlib import Path
import subprocess
import sys

from branch_search import ALPHABET, SEQ, restore

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools/elite'))
from assembler import Assembler


def pack_six(fields):
    return sum(v*16**(5-i) for i,v in enumerate(fields))


def run(runner,name,groups):
    a=Assembler();m=a.module(0,name)
    for index,group in enumerate(groups):m.n(pack_six(group)).st(9+index)
    table_address=26*112
    m.n(table_address).st('F').op('cx').st(0).st(1).st(2).st(3)
    m.raw(0x2F,0)
    for index in range(len(groups)):m.raw(0x2F,0x79+index)
    m.op('stop')
    banks,info=a.link();code=banks[0][:info['banks']['0']['used']]
    folder=HERE/'lookup'/name;folder.mkdir(parents=True,exist_ok=True)
    (folder/'autoexec.m61').write_text(f'reinit\nhin 0000 {code.hex()}\nhin {table_address:04d} {bytes(ALPHABET).hex()}\nrun\n')
    result=subprocess.run([str(runner),str(folder)],input='dump\n',capture_output=True,text=True,check=True,timeout=20)
    state=json.loads(result.stdout.splitlines()[0])
    assert not state['running'] and not state['error'],state
    actual=[]
    for n in state['regs'][:4]:
        n=int(n);actual+=[(n>>(8*j))&255 for j in range(3)]
    expected=[ALPHABET[v] for g in groups for v in g]+[0]*(12-6*len(groups))
    assert actual==expected,(name,actual,expected)
    (folder/'state.json').write_text(json.dumps(state,indent=2)+'\n')
    return dict(name=name,input_words=[pack_six(g) for g in groups],
                groups=len(groups),native_lookup_bytes=2*len(groups),
                cursor_initialization_bytes=2,table_bytes=16,
                output=actual,steps=state['steps'])


def main(runner):
    fields=[ALPHABET.index(b) for b in SEQ]
    rows=[];decoded=[]
    for i in range(0,len(fields),12):
        block=fields[i:i+12]
        padded=block+[0]*(-len(block)%6)
        groups=[padded[j:j+6] for j in range(0,len(padded),6)]
        row=run(runner,f'block-{i//12}',groups);rows.append(row)
        decoded+=row['output'][:len(block)]
    restore(bytes(decoded))
    for index in range(16):rows.append(run(runner,f'index-{index}',[[index]*6]))
    report=dict(command='2F 7r',native_setup='numeric values entered by ordinary digit opcodes; extended lookup command',
                instruction_symbols=len(decoded),all_indices_verified=True,
                ordinary_source_words=(len(fields)+5)//6,
                command_bytes_for_six_symbols=2,table_bytes=16,
                returns_normal_24_bit_integers=True,full_native_self_extractor=False,
                rows=rows)
    (HERE/'lookup-probe.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))


if __name__=='__main__':main(Path(sys.argv[1]).resolve())
