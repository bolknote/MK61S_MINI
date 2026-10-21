#!/usr/bin/env python3
"""Qualify a saved CORE-MATH pow.wc corpus against directed MPFR bounds."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from native_eabi_m0_arm_self_test import Machine, ROOT, bits, nan
from m0_mpfr_oracle import Oracle


def parse_token(token):
    token=token.strip().lower()
    if token in ('snan','+snan','-snan'):
        return 0x7FF0000000000001 | (0x8000000000000000 if token.startswith('-') else 0)
    return bits(float.fromhex(token) if '0x' in token else float(token))


def signaling_nan(value):
    return nan(value) and not value&(1<<51)


def verify_prefix(prefix, cases, elf_sha, corpus_sha):
    assert prefix['status']=='PASS_VERIFIED_PREFIX' and prefix['cases']==cases
    assert prefix['elf_sha256']==elf_sha and prefix['corpus_sha256']==corpus_sha
    assert prefix['audited_tokens']==2*cases
    assert prefix['unchanged_cases']+prefix['corrected_cases']==cases
    files={}
    for key in ('prefix_audit','original_log','original_runner','corrected_cases_report'):
        record=prefix[key];path=Path(record['path'])
        if not path.is_absolute():path=ROOT/path
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256'],key
        files[key]=path
    audit=json.loads(files['prefix_audit'].read_text())
    corrected=json.loads(files['corrected_cases_report'].read_text())
    assert audit['confirmed_cases']==cases and audit['audited_tokens']==2*cases
    assert audit['unchanged_cases']==prefix['unchanged_cases']
    assert audit['changed_cases']==prefix['corrected_cases']==len(audit['changes'])
    assert corrected['status']=='PASS' and corrected['complete_corpus']
    assert corrected['cases']==prefix['corrected_cases'] and corrected['elf_sha256']==elf_sha
    correction_text='\n'.join(row['source'] for row in audit['changes'])+'\n'
    assert hashlib.sha256(correction_text.encode()).hexdigest()==corrected['corpus_sha256']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--json',type=Path,required=True)
    p.add_argument('--max-cases',type=int,default=0,help='Zero tests every remaining entry; a positive limit is reported as partial.')
    p.add_argument('--start-case',type=int,default=0,help='Resume after this many cases, with a verified prefix report.')
    p.add_argument('--prefix-report',type=Path)
    a=p.parse_args();assert a.max_cases>=0 and a.start_case>=0
    elf_sha=hashlib.sha256(a.elf.read_bytes()).hexdigest();corpus_sha=hashlib.sha256(a.corpus.read_bytes()).hexdigest()
    prefix=None
    if a.start_case:
        assert a.prefix_report,'A resumed run requires a verified prefix'
        prefix=json.loads(a.prefix_report.read_text())
        verify_prefix(prefix,a.start_case,elf_sha,corpus_sha)
    else:assert not a.prefix_report
    m=Machine(a.elf,True);oracle=Oracle();digest=hashlib.sha256();count=a.start_case;position=0;complete=True;snan_cases=0
    for line_number,line in enumerate(a.corpus.read_text().splitlines(),1):
        line=line.split('#',1)[0].strip()
        if not line:continue
        position+=1
        if position<=a.start_case:continue
        if a.max_cases and count-a.start_case>=a.max_cases:complete=False;break
        pair=line.split(',');assert len(pair)==2,(line_number,line)
        try:x,y=(parse_token(v) for v in pair)
        except ValueError as error:raise ValueError((line_number,line)) from error
        snan=signaling_nan(x) or signaling_nan(y)
        # MPFR's NaN does not encode an IEEE signaling payload. Its numeric
        # reference is supplemented by pow's explicit sNaN -> quiet NaN rule.
        expected=0x7FF8000000000000 if snan else oracle.reference('pow',x,y)
        try:
            got=m.call('_ZN12compact_math3powEdd',x,y)[0]
            assert (nan(got) if nan(expected) else got==expected),(hex(got),hex(expected))
            if snan:assert got&(1<<51),('Signaling NaN was not quieted',hex(got))
        except Exception as error:
            raise AssertionError(dict(line=line_number,x=f'{x:016X}',y=f'{y:016X}',error=str(error))) from error
        count+=1;snan_cases+=snan;digest.update(struct.pack('<4Q',x,y,expected,got))
        if count%1000==0:print('PASS',count,'cases; corpus line',line_number,flush=True)
    assert position>=a.start_case
    report=dict(status='PASS',cases=count,complete_corpus=complete,wrong_rounding=0,mpfr=oracle.version,
        elf_sha256=elf_sha,corpus_sha256=corpus_sha,
        checked_this_run=count-a.start_case,start_case=a.start_case,signaling_nan_cases=snan_cases,
        prefix_report=prefix,new_cases_result_sha256=digest.hexdigest(),
        oracle='Directed MPFR bounds must round to the same binary64; signaling NaNs separately require a quiet NaN result.',
        abi='Every ARM call verifies R4-R11, SP and bounded stack writes.',
        scope='Saved worst-case corpus; not a totality proof over all binary64 pairs.',
        known_limitations=[
            'The owned 512/1024-bit fallback preserves a final undecided-interval trap; totality is unproved.'
            if 'mk61_m0_pow_rescue' in m.elf.symbols else
            'The upstream final 256-bit pow guard remains.'
        ])
    a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
