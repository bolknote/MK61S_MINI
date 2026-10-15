#!/usr/bin/env python3
"""Near-limit saved sources for cache/IO HIL; no device access or budget changes."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess


def source(language, index, *, interactive=False, long=False, resource_pressure=False):
    tag=('LATB' if language=='basic' else 'LATF')+f'{index:02d}'
    rng=random.Random(6100+index+(100 if language=='focal' else 0))
    noise=''.join(rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(100+index*7))
    if language=='basic':
        rows=8+index if resource_pressure else 28+index*4
        lines=['10 A=0',f'20 FOR I=1 TO {100000 if long else 25}']
        if long:lines.insert(1,'15 PRINT "RUN ESCB"')
        for n in range(rows):
            lines.append(f'{30+n*10} A=A'+('+1-1'*12))
        lines+=['900 NEXT I']
        if interactive:lines+=['910 INPUT "LAT INPUT",B']
        lines+=['920 PRINT "'+tag+'"','930 END','1000 PRINT "'+noise+'"','1010 RETURN']
        limit=3584
    else:
        rows=4+index if resource_pressure else 18+index*2
        lines=['1.10 SET A=0',f'1.20 FOR I=1,{100000 if long else 25};DO 2']
        if long:lines.insert(1,'1.15 PRINT "RUN ESCF"')
        if interactive:lines+=['1.25 ASK "LAT INPUT",B']
        lines+=['1.30 PRINT "'+tag+'"','1.40 EXIT']
        for n in range(rows):
            lines.append(f'2.{10+n*2:02d} SET A=A'+('+1-1'*6))
        lines+=['2.99 RETURN','3.10 PRINT "'+noise+'"','3.20 RETURN']
        limit=1536
    if resource_pressure:
        # Unexecuted random PRINT resources make failed packing expensive too;
        # this is not just a best-case, highly repetitive arithmetic corpus.
        lines=lines[:-2]
        number=0
        while True:
            prefix=f'{1000+number*10} PRINT "' if language=='basic' else f'3.{10+number*2:02d} PRINT "'
            remaining=limit-32-len(('\n'.join(lines)+'\n').encode('ascii'))-len(prefix)-2
            if remaining<3:break
            payload=''.join(rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(min(96,remaining)))
            lines.append(prefix+payload+'"');number+=1
    data=('\n'.join(lines)+'\n').encode('ascii')
    assert len(data)<=limit,(language,index,len(data),limit)
    return data,tag,limit


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--probe',type=Path,required=True)
    ap.add_argument('--cycles',type=int,default=8)
    ap.add_argument('--resource-pressure',action='store_true')
    a=ap.parse_args();assert 1<=a.cycles<=32
    out=a.output_dir.resolve();assert not out.exists()
    out.mkdir(parents=True);(out/'sources').mkdir();(out/'images').mkdir()
    modules=[]
    for language in ('basic','focal'):
        for i in range(8):
            data,tag,limit=source(language,i,resource_pressure=a.resource_pressure)
            name=('B' if language=='basic' else 'F')+f'{i:02d}'
            filename=name+('.tbi' if language=='basic' else '.foc')
            src=out/'sources'/filename;src.write_bytes(data)
            image=out/'images'/(name+'-owned.bvm')
            facts=json.loads(subprocess.check_output([a.probe,language,src,image,'--owned-resources'],text=True))
            modules.append(dict(name=name,filename=filename,language=language,tag=tag,
                source_limit=limit,source_sha256=hashlib.sha256(data).hexdigest(),
                image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),**facts))
    # One foreground script avoids host think time between individual OPENs.
    # PROF is intentionally NOT allowed in scripts. Keep the permission policy
    # unchanged; the host starts/stops collection and correlates two VER marks.
    order=[m for pair in zip(modules[:8],modules[8:]) for m in pair]
    # The ordinary M61 text cap is 1536, not the larger BASIC source cap.
    # Relative OPEN is resolved against the caller's directory by M61. Use
    # one nested round rather than widening the cap or adding host think time.
    round_lines=['open "'+m['filename']+'"' for m in order]+['ret']
    round_data='\n'.join(round_lines)+'\n'
    assert len(round_data.encode('ascii'))<=1536
    (out/'sources'/'ROUND.m61').write_text(round_data)
    for script,cycles in (('PRIME',2),('STRESS',a.cycles)):
        lines=['loadfont "/Games/Turochamp/Turochamp.fmk"','ver']
        lines += ['open "ROUND.m61"' for _ in range(cycles)]
        lines+=['ver','ret']
        script_data='\n'.join(lines)+'\n'
        assert len(script_data.encode('ascii'))<=1536
        (out/'sources'/(script+'.m61')).write_text(script_data)
    auxiliary=[]
    for language in ('basic','focal'):
        for kind in ('INPUT','ESC'):
            data,tag,limit=source(language,7,interactive=kind=='INPUT',long=kind=='ESC')
            filename=kind+('B.tbi' if language=='basic' else 'F.foc')
            path=out/'sources'/filename;path.write_bytes(data)
            image=out/'images'/(path.stem+'-owned.bvm')
            facts=json.loads(subprocess.check_output([a.probe,language,path,image,'--owned-resources'],text=True))
            auxiliary.append(dict(filename=filename,language=language,kind=kind,tag=tag,source_limit=limit,**facts))
            launcher=path.stem+'.m61'
            (out/'sources'/launcher).write_text('loadfont "/Games/Turochamp/Turochamp.fmk"\nopen "'+filename+'"\nret\n')
            auxiliary[-1]['launcher']=launcher
    result=dict(cycles=a.cycles,window_requests=a.cycles*len(modules),modules=modules,
                resource_pressure=a.resource_pressure,
                auxiliary=auxiliary,order=[m['name'] for m in order],
                budgets_unchanged=True,source_scope='ASCII saved source at existing BASIC3584/FOCAL1536 limits')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('cycles','window_requests','budgets_unchanged')}))
    for m in modules:print(m['filename'],m['source_bytes'],m['bytecode_bytes'])


if __name__=='__main__':main()
