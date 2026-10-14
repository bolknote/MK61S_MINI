"""32 input bits in a normal positive MK61 number: 26 in mantissa, 6 in order."""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools/elite'))
sys.path.insert(0, str(HERE))
from assembler import Assembler, bcd
from search import RAW, greedy_pairs, prefix_codes, prefix_decode, byte_round_trip, branch_stream


def recover_code(keep_mantissa=False):
    a = Assembler()
    m = a.module(0,'unpack numeric mantissa and order')
    m.ld(9).raw(0x17).op('int').st('C')
    m.ld(9).ld('C').raw(0x15).op('/')
    m.n(10000000).op('*')
    if not keep_mantissa:m.n(20000000).op('-')
    m.st(9).op('stop')
    banks,info = a.link()
    return banks[0][:info['banks']['0']['used']]


def recover(runner, name, payload, exponent, keep_mantissa=False):
    mantissa = payload+(2**25 if keep_mantissa else 20000000)
    init = list(map(int,str(mantissa)))
    shift = exponent-7
    if shift:
        init += [0x0C]+list(map(int,str(abs(shift))))+([0x0B] if shift<0 else [])
    init += [0x49,0x50,0x1F,0x51,*bcd(24*112)]
    folder = HERE/'exponent'/name
    folder.mkdir(parents=True,exist_ok=True)
    code = recover_code(keep_mantissa)
    (folder/'autoexec.m61').write_text(f'reinit\nhin 0000 {bytes(init).hex()}\nhin {24*112:04d} {code.hex()}\nrun\n')
    result = subprocess.run([str(runner),str(folder)],input='dump\nrun\n',text=True,
                            capture_output=True,check=True,timeout=20)
    states=[json.loads(s) for s in result.stdout.splitlines()]
    assert len(states)==2 and not states[-1]['error'] and not states[-1]['running'],states
    final=states[-1]
    expected=mantissa if keep_mantissa else payload
    assert final['regs'][9]==expected and final['regs'][12]==exponent,(name,payload,exponent,final)
    (folder/'states.json').write_text(json.dumps(states,indent=2)+'\n')
    return dict(name=name,payload=payload,exponent=exponent,normal_mantissa=mantissa,
                recovered_payload=final['regs'][9],recovered_order=final['regs'][12],
                core_steps=final['steps'])


def main(runner):
    results=[]
    groups={}
    for label,data,merges in [('huffman',RAW[:-1],0),('branch-huffman',branch_stream(RAW)[0],1)]:
        tokens=greedy_pairs(data,merges)
        codes=prefix_codes(tokens,2)
        bits=[b for t in tokens for b in codes[t]]
        recovered=[]
        words=[]
        for i in range(0,len(bits),32):
            low=sum(b<<j for j,b in enumerate(bits[i:i+26]))
            exponent=sum(b<<j for j,b in enumerate(bits[i+26:i+32]))
            row=recover(runner,f'{label}-{i//32}',low,exponent)
            results.append(row); words.append(row)
            recovered += [(int(row['recovered_payload'])>>j)&1 for j in range(26)]
            recovered += [(int(row['recovered_order'])>>j)&1 for j in range(6)]
        assert recovered[:len(bits)]==bits
        assert byte_round_trip(prefix_decode(recovered[:len(bits)],codes))==data
        groups[label]=dict(bits=len(bits),numeric_records=len(words),numeric_record_bytes=7*len(words))
    for exponent in (0,63):
        for payload in (0,2**26-1):
            results.append(recover(runner,f'boundary-{exponent}-{payload}',payload,exponent))
    optimized=[];optimized_groups={}
    # Sacrifice one payload bit so its fixed high bit can be discarded by
    # the bit reader. This removes the five-byte subtraction of the bias.
    # Both measured streams still need the same number of numeric records.
    for label,data,merges in [('huffman',RAW[:-1],0),('branch-huffman',branch_stream(RAW)[0],1)]:
        tokens=greedy_pairs(data,merges);codes=prefix_codes(tokens,2)
        bits=[b for t in tokens for b in codes[t]];actual=[];words=[]
        for i in range(0,len(bits),31):
            low=sum(b<<j for j,b in enumerate(bits[i:i+25]))
            exponent=sum(b<<j for j,b in enumerate(bits[i+25:i+31]))
            row=recover(runner,f'optimized-{label}-{i//31}',low,exponent,True)
            optimized.append(row);words.append(row)
            m=int(row['recovered_payload'])
            assert m>>25==1
            actual += [(m>>j)&1 for j in range(25)]
            actual += [(int(row['recovered_order'])>>j)&1 for j in range(6)]
        assert byte_round_trip(prefix_decode(actual[:len(bits)],codes))==data
        optimized_groups[label]=dict(bits=len(bits),numeric_records=len(words),
                                     numeric_record_bytes=7*len(words))
    for exponent in (0,63):
        for payload in (0,2**25-1):
            optimized.append(recover(runner,f'optimized-boundary-{exponent}-{payload}',payload,exponent,True))
    report=dict(recover_bytes=len(recover_code()),recover_hex=recover_code().hex(' '),
                payload_bits=26,order_bits=6,groups=groups,results=results,
                optimized_31=dict(recover_bytes=len(recover_code(True)),
                                  recover_hex=recover_code(True).hex(' '),
                                  payload_bits=25,order_bits=6,
                                  discard_bit_25=True,groups=optimized_groups,
                                  results=optimized),
                full_native_self_extractor=False)
    (HERE/'exponent-probe.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve())
