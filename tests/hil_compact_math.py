#!/usr/bin/env python3
"""Numerical/performance HIL for a prepared binary64 resident; never flashes.

Installs one reserved diagnostic APP and 4-KiB oracle blocks, removes all its
files in finally, and verifies original files/program/registers/stack/pwd.
Run on the current device before flashing, then on the candidate with the
same APP and fixtures. Time is wall-clock micros averaged over call batches.
"""
from pathlib import Path
import sys,json,struct,statistics,argparse,hashlib
ROOT=Path(__file__).resolve().parents[1]
from hil_c5_stack import read_file,write_file
from hil_packbits_firmware import fingerprint
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
NAMES=('sin','cos','tan','asin','acos','atan','ln','log10','exp','sqrt','pow')
records=[]
for line in (ROOT/'tests/fixtures/compact_math_binary64.tsv').read_text().splitlines():
    if not line or line.startswith('#'):continue
    n,a,b,c=line.split();records.append(struct.pack('<IIQQQ',NAMES.index(n),0,int(a,16),int(b,16),int(c,16)))
chunks=[struct.pack('<4I',0x5641544d,len(records[i:i+127]),i,len(records))+b''.join(records[i:i+127]) for i in range(0,len(records),127)]
vectors=b''.join(chunks)
paths=('/MATHCHK.APP','/MATHOUT.bin',*[f'/MATH{i:02d}.bin' for i in range(len(chunks))])
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port',required=True)
parser.add_argument('--public-id',required=True)
parser.add_argument('--expected-build',required=True)
parser.add_argument('--app',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
parser.add_argument('--keyboard-layout',type=int,choices=(0,1),default=1)
args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
with ScreenPort(args.port,keyboard_layout=args.keyboard_layout) as p:
    identity=parse_identity(p.command('identity',15))
    assert identity.public==args.public_id.upper() and identity.build==args.expected_build.upper(),identity
    original=fingerprint(p);logical={c:p.command(c,20) for c in ('reg','stk','dump','pwd')}
    assert not any(x.casefold() in {p.casefold() for p in paths} for x in original['files'])
    result=None
    try:
        write_file(p,paths[0],args.app.read_bytes());print(args.public_id,'math APP installed',flush=True)
        for i,data in enumerate(chunks):
            write_file(p,paths[2+i],data)
            if i%3==0:print(args.public_id,'uploaded vector block',i+1,'/',len(chunks),flush=True)
        print(args.public_id,'all',len(records),'oracle vectors uploaded',flush=True)
        launch=p.command('open "'+paths[0]+'"',timeout=60);assert 'Open failed!' not in launch,launch
        raw=read_file(p,paths[1]);assert len(raw)==544,len(raw)
        magic,version,samples,rounds,cases,failed=struct.unpack_from('<6I',raw)
        assert (magic,version,samples,rounds,cases)==(0x54414d51,1,1024,9,len(records))
        worst=struct.unpack_from('<11Q',raw,24);timings=struct.unpack_from('<99I',raw,112)
        first_index,first_op,_=struct.unpack_from('<3I',raw,508);first_expected,first_actual,checksum=struct.unpack_from('<3Q',raw,520)
        identity=parse_identity(p.command('identity'))
        assert identity.public==args.public_id.upper() and identity.build==args.expected_build.upper(),identity
        result={'identity':identity.__dict__,'oracle_cases':cases,'failed':failed,'worst_ulp':dict(zip(NAMES,worst)),'samples':samples,'rounds':rounds,'nanosecond_median_per_call':{n:statistics.median(timings[i*rounds:(i+1)*rounds])*1000/samples for i,n in enumerate(NAMES)},'raw_microseconds':dict(zip(NAMES,[list(timings[i*rounds:(i+1)*rounds]) for i in range(11)])),'first_failure':{'index':first_index,'op':first_op,'expected':f'{first_expected:016X}','actual':f'{first_actual:016X}'},'checksum':f'{checksum:016X}','vectors_sha256':hashlib.sha256(vectors).hexdigest(),'launch':launch}
        assert not failed,result
    finally:
        p.command('fsput cancel')
        current=fingerprint(p)
        for path in paths:
            actual=next((x for x in current['files'] if x.casefold()==path.casefold()),None)
            if actual:
                response=p.command('rm "'+actual+'"',30);assert 'Removed 1 entry.' in response,response
        assert fingerprint(p)==original,'math test changed original files'
        current={c:p.command(c,20) for c in logical}
        assert current==logical,('math test changed logical state',current,logical)
        if result:
            result['preservation']='original files/program/registers/stack/pwd exact';result['health']={c:p.command(c,20) for c in ('df','crash show','mpu status')};assert 'FIRMWARE CRC state=valid' in result['health']['df'] and 'actual=0x'+args.expected_build.upper() in result['health']['df'];assert 'CRASH none' in result['health']['crash show']
            (args.output_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(args.public_id,cases,'physical oracle cases PASS; median ns per call',result['nanosecond_median_per_call'],flush=True)
