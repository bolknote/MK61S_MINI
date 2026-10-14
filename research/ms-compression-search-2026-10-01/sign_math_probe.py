"""Check whether arithmetic can change order while retaining a native sign-digit."""
import json
from pathlib import Path
import sys

from writer_probe import run,digits

HERE=Path(__file__).resolve().parent


def main(runner):
    rows=[]
    operations={
        'recall':[], 'add-zero':[0x0E,0,0x10], 'subtract-zero':[0x0E,0,0x11],
        'multiply-one':[0x0E,1,0x12], 'divide-one':[0x0E,1,0x13],
        'multiply-1000':[0x0E,1,0x0C,3,0x12],
        'multiply-10000':[0x0E,1,0x0C,4,0x12],
        'square':[0x22], 'integer':[0x34], 'fraction':[0x35],
        'absolute':[0x31],
    }
    for donor in (1,5):
        seed=[1,donor,0x3A,0x35,0x49,0x0E]+digits(12030329)+[0x48,0x69,0x68,0x14,0x54,0x0C,0x44,0xD4,0x64]
        for label,tail in operations.items():
            row=run(runner,f'sign-math-{donor}-{label}',seed+tail,8)
            rows.append(row)
    (HERE/'sign-math-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
    for row in rows:print(json.dumps(row))


if __name__=='__main__':main(Path(sys.argv[1]).resolve())
