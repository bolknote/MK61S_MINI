#!/usr/bin/env python3
"""Select all saved pow inputs affected by integer/dyadic/binomial paths."""
import argparse
from fractions import Fraction
import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tests'))
from qualify_m0_pow_worst import parse_token
from native_eabi_m0_arm_self_test import real


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args()
    one=0x3FF0000000000000;cache={};rows=[];ranges=[];total=integer=dyadic=binomial=0
    for number,line in enumerate(args.corpus.read_text().splitlines(),1):
        text=line.split('#',1)[0].strip()
        if not text:continue
        a,b=(parse_token(token) for token in text.split(','));total+=1
        if b not in cache:
            magnitude=b&0x7FFFFFFFFFFFFFFF
            if magnitude and magnitude<0x7FF0000000000000:
                y=abs(Fraction(real(b)))
                supported=y.numerator<=32 and y.denominator<=128
                cache[b]=(supported,supported and y.denominator==1)
            else:cache[b]=(False,False)
        supported,whole=cache[b]
        tiny=one-64<=a<=one+32 and a!=one and b&0xFFFFFFFF!=0
        if not(supported or tiny):continue
        integer+=whole;dyadic+=supported and not whole;binomial+=bool(tiny)
        rows.append(text)
        if ranges and number==ranges[-1][1]+1:ranges[-1][1]=number
        else:ranges.append([number,number])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text('\n'.join(rows)+'\n')
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    report=dict(status='PASS_EXHAUSTIVE_SELECTOR',full_corpus_cases=total,
        selected_cases=len(rows),integer_exponent_cases=integer,noninteger_dyadic_cases=dyadic,
        binomial_dispatch_gate_cases=binomial,selected_source_line_ranges=ranges,
        full_corpus_sha256=sha(args.corpus),subset_sha256=sha(args.output),selector_sha256=sha(__file__),
        selection='Union of all saved entries with |y|=p/q, p<=32 and q<=128, and all new tiny-binomial dispatch gates. Selection places no restriction on base encodings and includes both exponent signs. These cover every potentially accepted new numerical path in the saved corpus; unsupported cases provably decline and remain on existing paths. Line ranges refer to the unchanged full corpus.',
        scope='Deterministic exact binary64 exponent-domain selection, not numerical qualification. The complete resulting subset must independently pass the ARM/MPFR runner.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print('Selected',len(rows),'of',total,'entries;',integer,'integer;',dyadic,'noninteger dyadic;',binomial,'binomial gates.')


if __name__=='__main__':main()
