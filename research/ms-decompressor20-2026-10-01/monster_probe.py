"""Native 0C-monster experiments; only executable calculator code is loaded."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def run(runner, name, body):
    folder = HERE / 'monster-probes' / name
    folder.mkdir(parents=True, exist_ok=True)
    code = bytes(body)+bytes.fromhex('0d 50')
    (folder/'autoexec.m61').write_text(f'reinit\nhin 0000 {code.hex()}\nrun\n')
    p = subprocess.run([str(runner),str(folder)],input='dump\n',
                       capture_output=True,text=True,timeout=20)
    row = dict(name=name, producer=bytes(body).hex(' '), bytes=len(body), exit=p.returncode)
    if p.returncode:
        row['stderr']=p.stderr[-200:]
    else:
        state=json.loads(p.stdout.splitlines()[0])
        row.update(error=state['error'],steps=state['steps'],words=state['reg_words'])
        (folder/'state.json').write_text(json.dumps(state,indent=2)+'\n')
    return row


def seed(lead, lower, exponent, negative=False):
    body=[lead,0x0a,*map(int,lower)]
    shift=exponent-400
    if shift:
        body += [0x0c,*map(int,str(abs(shift)))]+([0x0b] if shift<0 else [])
    if negative:
        body += [0x0b]
    body += [0x0e,5,0,0x15,0x22,0x22,0x22,0x12,0x49,0x69]
    return body


def main(runner):
    cases=[]
    for lead in (1,2,5,8):
        for exponent in range(400,500):
            cases.append((f'positive-{lead}-e{exponent}',seed(lead,'2030330',exponent)))
    for lead in (1,2,5,8):
        for exponent in (400,407,410,411,417,471,499):
            cases.append((f'negative-{lead}-e{exponent}',seed(lead,'2030330',exponent,True)))
    for tail,ops in [('recall',[0x6c,0x40]),('fraction',[0x6c,0x35,0x40]),
                     ('leading-6',[6,0x6c,0x14,0x54,0x0c,0x40]),
                     ('leading-0',[0,0x6c,0x14,0x54,0x0c,0x40])]:
        for exponent in (400,407,410,411,417,471):
            cases.append((f'{tail}-e{exponent}',seed(1,'2030330',exponent)+ops))
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(lambda c:run(runner,*c),cases))
    (HERE/'monster-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(dict(cases=len(rows),stopped=sum(r['exit']==0 for r in rows),
                         errors=sum(r.get('error',False) for r in rows))))
    for r in rows:
        if r['exit']==0 and (r['name'].startswith('positive-1-') and r['name'][-3:] in ('400','407','410','411','417','471','499') or not r['name'].startswith(('positive','negative'))):
            print(json.dumps(dict(name=r['name'],rc=r['words'][12],r0=r['words'][0],error=r['error'])))


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve())
