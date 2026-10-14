"""Native pointer-carry producers over orders on both sides of the 7-digit case."""
import json
from pathlib import Path
import sys

from writer_probe import run,digits

HERE=Path(__file__).resolve().parent


def main(runner):
    rows=[]
    for donor in (1,5):
        for exponent in range(18):
            body=[1,donor,0x3A,0x35,0x49,0x0E]+digits(12030329)
            shift=exponent-7
            if shift:body += [0x0C]+digits(abs(shift))+([0x0B] if shift<0 else [])
            body += [0x48,0x69,0x68,0x14,0x54,0x0C,0x44,0xD4]
            rows.append(run(runner,f'order-sweep-{donor}-{exponent}',body,4,True))
    (HERE/'order-sweep.json').write_text(json.dumps(rows,indent=2)+'\n')
    for row in rows:print(json.dumps(row))


if __name__=='__main__':main(Path(sys.argv[1]).resolve())
