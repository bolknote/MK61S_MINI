#!/usr/bin/env python3
"""Raw public-key readback of a native Ms:P10 copy, original stock ROM.

First erase the ordinary sourceP8 in a real four-instruction program, then
swap hiddenP10 into logicalX and save it in physical ordinaryP9. The STOP
formatter copies the header6 carrier back into P10, leaving both P9/P10.
The display is still zero: raw readback is NOT numerical decoding or K2.
Fresh observer-free ALL5 instances mirror the entire native protocol.
Strict replay covers separate prefixes and a continuous complete program
run, never repairing the model at intermediate checkpoints.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

root=Path(__file__).resolve().parent
payload=runpy.run_path(str(root/'cache-bc-head93-native-q-payload-proof.py'))
reader,r,previous=(payload[n] for n in ('reader','r','previous'))
raw=reader['raw']


def native(flag):
    value=json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-q-payload-roundtrip-native.cjs'),flag],text=True))
    assert value['report']['minimal'] and value['report']['onlyPublicKeys']
    assert value['report']['ALL5mirror'] and value['report']['qReadbackIdleCheck']
    return value


def check(value,word,control=False):
    ready=value['addressStable'];final=value['readbackStable']
    assert ready['words']['Ms:P10']==word and ready['registers'][8]==word
    assert ready['registers'][9]=='000000000000'
    expected=['000000000000']*15
    if not control:expected[9]=word
    assert final['registers']==expected,'sourceP8 really erased, only readbackP9 remains'
    assert final['words']['Ms:P10']==word and final['words']['Q']=='0000F0000000'
    assert final['words']['Ms:P9']=='000000000000'
    assert final['ip']==0x35 and final['modeR2']==8 and final['display']=='0,'
    assert final['ST2']==[0,0,0],'not the BB/BC saved0/2/D inlet'
    codes=[0x4D]+([] if control else [0x14])+[0x4E,0x50]
    assert final['program'][71:71+len(codes)]==codes
    changed=[i for i,(a,b) in enumerate(zip(ready['program'],final['program'])) if a!=b]
    assert changed==list(range(71,71+len(codes))),changed
    for stage in value['exitStages']:
        if stage['name'] in ('payload-exit-jump','payload-exit-run'):continue
        assert stage['words']==ready['words'] and stage['registers']==ready['registers']
    jump=next(v for v in value['exitStages'] if v['name']=='payload-exit-jump')
    assert jump['words']['Ms:P7']=='FFF000000000' and jump['modeR2']==0 and jump['pc']=='01'
    assert jump['registers']==ready['registers'] and jump['words']['Ms:P10']==word
    records=value['windows']['payload-exit-run']
    ops=[v['fullBefore']['ik1302']['r'][30]+16*v['fullBefore']['ik1302']['r'][33]
         for v in records if v['ip']==0x9C]
    assert ops==codes,ops
    assert records[0]['ip']==0x9C and records[-1]['ip']==0x35
    stores=[v for v in records if v['ip']==0xD4]
    assert len(stores)==2
    assert [v['ordinaryOwner'] for v in stores]==[['register:R8'],['register:R9']]
    assert raw(stores[0]['emitted'][0:36:3])=='000000000000'
    assert raw(stores[1]['emitted'][0:36:3])==('000000000000' if control else word)
    assert not any(v['ip'] in (0xBB,0xBC,0xC7) for v in records)
    if not control:
        assert len(records)==547 and records[0]['word']==313132 and records[-1]['word']==313678
        moved=next(v for v in records if v['ip']==0xEE and
            raw(v['fullBefore']['ik1302']['m'][1:36:3])==word)
        assert moved['numericOwner']==['Ms:P9'] and stores[0]['word']<moved['word']<stores[1]['word']
        writes=[v for v in records if v['ip']==0xA8 and v['numericOwner']==['Ms:P10']]
        assert len(writes)==1 and raw(writes[0]['emitted'][1:36:3])==word
    else:assert len(records)==352
    return records


def run_case(label,flag,word,control=False):
    value=native(flag);records=check(value,word,control)
    windows={name:v for name,v in value['windows'].items()
             if name.startswith('payload-exit-') or name=='q-readback-idle'}
    total=0
    for name,records in windows.items():
        if name!='payload-exit-run':assert len(records)==30
        total+=reader['replay'](records,label+'/'+name)
    assert total==(622 if control else 847)
    previous['period'](windows['q-readback-idle'],label+' P9/P10/Q readback idle')
    print('PASS',label,total,'strict ORIGINAL ALL5 transitions in',len(windows),
        'SEPARATE windows. '+('Negative no-swap control: ordinaryP9=0, originalP8 erased.'
        if control else 'Native '+word+' ordinaryP8 -> hiddenP10 -> ordinaryP9; '
        'originalP8 erased BEFORE hidden read, P10/Q held. Display remains0, '
        'no numerical decoder/controller restoration or K2 claim.'),flush=True)
    r['inlet']['immutable_reference']()


def run():
    r['inlet']['immutable_reference']()
    cases=[('long','--raw-read-proof-input','600012345678',False),
           ('short','--raw-read-short-proof-input','600010000003',False),
           ('no-swap','--raw-read-control-proof-input','600012345678',True)]
    if '--long-only' in sys.argv:cases=cases[:1]
    if '--short-only' in sys.argv:cases=cases[1:2]
    if '--control-only' in sys.argv:cases=cases[2:]
    for case in cases:run_case(*case)
    print('Strict847 readback transitions per positive fixture include only '
        'the NEW readback windows, not the recorded/rechecked1030 Q/copy prefix. '
        'Program editing and BP01 complete actions are native/mirrored; only '
        'their first30 words are replayed. The547-word accepted program run '
        'is continuous through released-key35. Header6/blank bank premises '
        'remain; no state load, live/browser test or immutable-source edit.',flush=True)


if __name__=='__main__':run()
