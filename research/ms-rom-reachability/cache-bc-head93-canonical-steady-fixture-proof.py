#!/usr/bin/env python3
"""Signed eight-digit NUM through the steady cycle, selected strict ALL5.

Independent ordinary display/word baseline; first/third numerical reads use
physicalP10. Original reference/mirrors, no state imports or ROM changes.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
r=num['r'];prep=num['prep']
raw,stage,replay,period=(num[n] for n in ('raw','stage','replay','period'))
ZERO='000000000000';NUMBER='007987654321'


def run():
    r['inlet']['immutable_reference']()
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-canonical-steady-native.cjs'),
        '--proof-input','--negative'],text=True))
    assert data['baseline']=={'input':'-87654321','word':NUMBER,'display':'-87654321,','R2':15}
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    assert data['report']['packetAudit']['checkedWords']==2088240
    assert data['report']['packetAudit']['numberHeld'] and data['report']['packetAudit']['firstDifference'] is None
    assert data['nativeIdleStates']['packet-repeat-idle']==data['nativeIdleStates']['packet-idle']
    for label in ('packet-repeat-idle','packet-idle'):period(data['windows'][label],'negative-fixture/'+label)
    assert stage(data,'packet-clean-backup-zero')['registers'][14]==ZERO
    assert stage(data,'packet-repeat2-plus')['display']=='13,'
    assert stage(data,'packet-repeat2-lastx')['display']=='7,'
    final=stage(data,'packet-idle');assert final['display']=='-87654321,'
    assert final['words']['Ms:P10']==final['words']['aux0']==NUMBER
    assert NUMBER not in final['registers'] and final['registers'][14]==ZERO
    for label in ('packet-reopen-lastx','packet-repeat-reopen-lastx','packet-repeat2-reopen-lastx'):
        records=data['windows'][label];assert not any(v['ip']==0xD6 for v in records)
        source=next(v for v in records if v['ip']==0xEE)
        assert source['numericOwner']==['Ms:P10']
        assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
        num['copy_contract'](source,'ik1302',0xEE,True,'signed_'+label+'_P10_reader')
        frame=prep['quadruple'](records,'signed_'+label+'_lift')
        assert frame[0]['numericOwner']==['unclassified:aux0']
        assert raw(frame[0]['emitted'][1:36:3])==NUMBER
    print('PASS NATIVE signed-87654321: three physicalP10 reads, canonical13/LastX7 work, '
          'ordinary reserve0; all12 sign/order/mantissa fields held2088240 native words; '
          'exact steady whole-native state recurrence, not arbitrary number/operation safety.',flush=True)
    labels=['packet-repeat-idle','packet-repeat2-plus','packet-repeat2-lastx',
        'packet-repeat2-preclear4','packet-repeat2-reopen-lastx','packet-idle']
    if '--contracts-only' not in sys.argv:
        total=direct=skipped=0
        for label in labels:
            a,b=replay(data['windows'][label],'signed-steady/'+label)
            direct+=a;skipped+=b;total+=a+b
        assert total==691
        print('PASS TOTAL signed691 originalALL5 words/6 separate continuous windows;',
              'direct',direct,'fixed-pin skips',skipped,'not full2088240-word prefix/macrocycle.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
