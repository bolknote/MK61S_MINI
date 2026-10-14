#!/usr/bin/env python3
"""Late rewrite of hiddenP10 with a negative-order number, normal work/read.

Selected strict continuous ALL5 windows, independent ordinary baseline and
passive old->new per-word ledger. No model state imports, repairs or ROM edits.
Early-header bootstrap control is separate and intentionally unsuccessful.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
steady=runpy.run_path(str(root/'cache-bc-head93-canonical-steady-proof.py'))
r=num['r'];prep=num['prep'];control=num['control']
raw,stage,replay,period=(num[n] for n in ('raw','stage','replay','period'))
OLD='007012345678';NEW='950012345678';ZERO='000000000000';ONE='000010000000'


def early_control():
    source=('console.log(JSON.stringify(require('+json.dumps(str(root/'cache-bc-head93-t-packet-prepare-native.cjs'))+
        ').run({proof:true,phase:"u",normalInput:"1.2345678E-50"})));')
    data=json.loads(subprocess.check_output(['node','-e',source],text=True))
    records=data['windows']['packet-seed8'];first=records[0]
    assert first['ip']==0x9C and first['numericOwner']==['Ms:P10']
    assert first['fullBefore']['ik1302']['m'][31:35:3]==[5,9]
    assert first['fullAfter']['ik1302']['r'][36]+16*first['fullAfter']['ik1302']['r'][39]==0x9E
    write=next(v for v in records if v['ip']==0xD4)
    assert write['ordinaryOwner']==['register:RB']
    assert stage(data,'packet-seed8')['registers'][8]==ZERO
    read=next(v for v in data['windows']['packet-plant-u'] if v['ip']==0xD6)
    assert read['ordinaryOwner']==['register:R8'] and raw(read['fullBefore']['ik1302']['m'][0:36:3])==ZERO
    assert 'U' not in stage(data,'packet-idle')['markers']
    print('PASS early-small bootstrap control: header95/P10 accepts9C, STORE hitsRB notR8; '
          'requiredF/R8 never installed, following R8/0 read cannot createU. '
          'Data remainsP10 here; later loss is the downstream wrong-base control writer.',flush=True)
    return data,[(n,data['windows'][n]) for n in ('packet-seed8','packet-plant-u','packet-idle')]


def positive():
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-canonical-late-native.cjs'),
        '--proof-input'],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    assert data['baseline']['word']==NEW and data['baseline']['display']=='1,2345678-50'
    ledger=data['report']['lateNumberAudit'];assert ledger['checkedWords']==2222640
    assert ledger['contractHeld'] and ledger['firstDifference'] is None
    assert ledger['writes']==[{'word':1612300,'stage':'packet-late-sign','ip':0xE9,'target':'Ms:P10','actual':NEW}]
    assert data['nativeIdleStates']['packet-repeat-idle']==data['nativeIdleStates']['packet-idle']
    for label in ('packet-repeat-idle','packet-idle'):period(data['windows'][label],'late-small/'+label)
    sign=data['windows']['packet-late-sign'];read=next(v for v in sign if v['ip']==0xEE)
    assert read['numericOwner']==['unclassified:aux0'] and raw(read['fullBefore']['ik1302']['m'][1:36:3])==NEW
    num['copy_contract'](read,'ik1302',0xEE,True,'late_small_input_reader')
    write=next(v for v in sign if v['ip']==0xE9)
    assert write['numericOwner']==['Ms:P10'] and write['word']==1612300
    assert raw(write['fullBefore']['ik1302']['m'][1:36:3])==OLD
    assert raw(write['emitted'][1:36:3])==NEW
    num['copy_contract'](write,'ik1302',0xE9,False,'late_small_P10_writer')
    third=[(v,v['fullBefore']['ik1306']['r'][36]+16*v['fullBefore']['ik1306']['r'][39]) for v in sign]
    operand=next(v for v,ip in third if ip==0x16);result=next(v for v,ip in third if ip==0xFF)
    assert control['chip_owner'](data,operand,'ik1306')==['unclassified:aux0']
    assert raw(operand['fullBefore']['ik1306']['m'][1:36:3])==NEW
    assert raw(control['outgoing'](result,'ik1306')[1:36:3])==ONE
    for label in ('packet-repeat-reopen-lastx','packet-repeat2-reopen-lastx'):
        records=data['windows'][label];assert not any(v['ip']==0xD6 for v in records)
        source=next(v for v in records if v['ip']==0xEE)
        assert source['numericOwner']==['Ms:P10'] and raw(source['fullBefore']['ik1302']['m'][1:36:3])==NEW
        num['copy_contract'](source,'ik1302',0xEE,True,'late_small_'+label+'_reader')
        frame=prep['quadruple'](records,'late_small_'+label+'_lift')
        assert frame[0]['numericOwner']==['unclassified:aux0'] and raw(frame[0]['emitted'][1:36:3])==NEW
    print('PASS NATIVE typed1.2345678E-50 -> E9/P10 intentional rewrite at1612300 -> '
          'canonical6+7=13/normalLastX7 -> physicalP10 read twice. '
          'No ordinary new-value backup; full12-field old->new ledger holds2222640 words; '
          'exact native fixed-cycle recurrence.',flush=True)
    labels=[n for n in data['windows'] if n.startswith('packet-late-')]+[
        'packet-repeat-port5-zero','packet-repeat-plus','packet-repeat-reopen-lastx','packet-repeat-idle',
        'packet-repeat2-plus','packet-repeat2-lastx','packet-repeat2-preclear4',
        'packet-repeat2-reopen-lastx','packet-idle']
    result=[(n,data['windows'][n]) for n in labels]
    assert len(result)==24 and sum(len(v) for _,v in result)==2338
    return data,result


def run():
    r['inlet']['immutable_reference']();steady['guard_contract']()
    data,sections=early_control() if '--early-control-only' in sys.argv else positive()
    if '--contracts-only' not in sys.argv:
        direct=skipped=0
        for label,records in sections:
            a,b=replay(records,'late/'+label);direct+=a;skipped+=b
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(sections),'separate continuous windows;',
              'direct',direct,'fixed-pin skips',skipped,'not full native prefix/macrocycle.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
