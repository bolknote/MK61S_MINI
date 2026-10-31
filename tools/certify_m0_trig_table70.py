#!/usr/bin/env python3
"""Read-only rational verification of the existing Q94 table/Q70 sin-cos pass."""
import argparse,hashlib,json,re,sys
from pathlib import Path
from fractions import Fraction as F
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from generate_m0_trig_table import interval
from generate_m0_trig_checked_table import rounded

def certificate(root):
    h=F(1,1<<11)+F(1,1<<63);half=F(1,2);scale=1<<70
    square=half+F(1,1<<14)+F(1,4)
    cube=F(5,2)+square*h+F(1,1<<14)
    zr=half+square/F(1<<18)
    fourth=half+(2*(1<<30)*zr+zr*zr)/F(1<<34)
    fifth=half+fourth*h+F(1,1<<16)
    sine=cube/6+F(2,3)+fifth/120+half+scale*h**7/5040
    cosine=square/2+half+fourth/24+half+scale*h**6/720
    coefficients=256*h+128*h*h+(sine+cosine)/F(1<<62)
    total=1+sine+cosine+5+coefficients
    assert total<12
    text=(root/'code/native_eabi_m0_trig_checked_table.inc').read_text()
    start=text.index('trig94_table[806][6]={');end=text.index('};',start)
    rows=[tuple(map(int,r)) for r in re.findall(r'\{(\d+)U,(\d+)U,(\d+)U,(\d+)U,(\d+)U,(\d+)U\}',text[start:end])]
    assert len(rows)==806
    for j,row in enumerate(rows):
        for op in [0,1]:
            low,high=interval(F(j,1024),bool(op))
            value=sum(row[3*op+k]<<(32*k) for k in range(3))
            assert value==rounded(low,high,94)
    assert F(1,32)+half<1
    pins={n:hashlib.sha256((root/'code'/n).read_bytes()).hexdigest() for n in ['native_eabi_m0_trig_checked.inc','native_eabi_m0_trig_checked_table.inc']}
    return dict(status='PASS_RATIONAL_EXISTING_TRIG70',source_sha256=pins,checked_Q94_rows=806,total_Q70_error=str(total),total_Q70_error_float=float(total),guard=12,
                new_tables=0,new_static_RAM=0,argument='Same exact rational error propagation and table intervals as the existing generator, replayed without writing tables. The pre-existing argument error is added separately.',
                scope='Algebraic/table certificate, not a machine-checked C++ or compiler proof; actual public-function ARM tests remain required.')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();r=certificate(a.source_root);a.json.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status=r['status'],error=r['total_Q70_error_float'],rows=r['checked_Q94_rows'])))
if __name__=='__main__':main()
