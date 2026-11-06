from pathlib import Path
import hashlib,json,os,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;C=HERE/'candidate'
sys.path.insert(0,str(ROOT))
from tools.apps.spectrum.build_spectrum_app import SOURCES
flags=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-DMK61_TARGET_PICOCALC=1',
       '-fsanitize=address,undefined','-fno-omit-frame-pointer',
       '-I'+str(ROOT/'sdk/portable/include'),'-I'+str(ROOT/'code'),
       '-I'+str(C/'examples/portable-apps/SPECTRUM')]
core=[str(C/p) for p in SOURCES[1:]]
report={}
env=dict(os.environ,ASAN_OPTIONS='detect_stack_use_after_return=1')
with (HERE/'input-oracle-build.log').open('w') as log:
    for mode in ('CHUNK','PIPE'):
        extra=[] if mode=='PIPE' else ['-DORACLE_SOURCE="../cosmic-chunk/candidate/examples/portable-apps/SPECTRUM/main.c"']
        exe=HERE/f'input-oracle-{mode}'
        mode_core=core if mode=='PIPE' else [str(ROOT/'third_party/emu2149/emu2149.c') if p.endswith('/third_party/emu2149/emu2149.c') else p for p in core]
        subprocess.run(flags+extra+[str(HERE/'input_oracle.c')]+mode_core+['-o',str(exe)],check=True,stdout=log,stderr=log)
        for game in ('INPUT','MANIC','COSMIC','IANNA'):
            args=['INPUT'] if game=='INPUT' else [str(HERE.parent/f'{game}.Z80'),str(HERE.parent/f'{game}.ULP')]
            with (HERE/f'input-{mode}-{game}.txt').open('w') as out:
                subprocess.run([str(exe)]+args,check=True,stdout=out,stderr=log,env=env)
        print(mode,'completed',flush=True)
    # A shifted input timeline must change the observed trajectory.
    with (HERE/'input-PIPE-negative.txt').open('w') as out:
        subprocess.run([str(HERE/'input-oracle-PIPE'),'INPUT','unused','1000'],check=True,stdout=out,stderr=log,env=env)
for game in ('INPUT','MANIC','COSMIC','IANNA'):
    a=(HERE/f'input-CHUNK-{game}.txt').read_bytes();b=(HERE/f'input-PIPE-{game}.txt').read_bytes()
    assert a==b,game
    last=a.splitlines()[-1].split()
    report[game]={'frames':len(a.splitlines()),'identical':True,'trajectory_sha256':hashlib.sha256(a).hexdigest(),
                  'pcm_samples_at_last_capture':int(last[5].split(b'/')[0]),'sound_events_at_last_capture':int(last[4].split(b'/')[0])}
observations=list(map(int,re.findall(r'max_prefetch_IN_wall_ahead_us=(\d+)',(HERE/'input-oracle-build.log').read_text())))
assert len(observations)==9 and max(observations)<=4000
for index,game in enumerate(('INPUT','MANIC','COSMIC','IANNA')):report[game]['simulated_max_prefetch_IN_wall_ahead_us']=observations[index+4]
assert (HERE/'input-PIPE-negative.txt').read_bytes()!=(HERE/'input-PIPE-INPUT.txt').read_bytes()
report['negative_shift_1000T_detected']=True
report['scope']='Weighted AY+pipeline vs production per-tick AY+outer512 reference; actual APP schedulers/real Z80/AY, timestamped guest IN, all32CPUfields/fullRAM/video/bothPSGstates/ordered events/fullPCM at every capture. Simulated wall/native costs, no hardware speed claim.'
(HERE/'input-oracle-equality.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
