#!/usr/bin/env python3
"""Fresh native P8/Y/aux1 cleanup and primary-to-secondary request delivery.

Separate strict ALL5 windows/slices, no checkpoint repairs or emulator state
imports. A delivered byte/reply is NOT a numerical SIGN success or K1/K2.
P10 still holds the fixture, not the hoped-for SIGN result1.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import And, BitVec

root=Path(__file__).resolve().parent
prep=runpy.run_path(str(root/'cache-bc-head93-t-packet-prepare-proof.py'))
prior=prep['prior']
r,w,q=(prep[n] for n in ('r','w','q'))
raw,stage,replay,period,preserved_number=(prep[n] for n in
    ('raw','stage','replay','period','preserved_number'))
F,ZERO,NUMBER=(prep[n] for n in ('F','ZERO','NUMBER'))


def chip_owner(data,v,chip='ik1303'):
    return sorted({data['cells'][tag]['area']+':'+str(data['cells'][tag]['word'])
        for j,tag in enumerate(v['tagsBefore'][chip]) if j%3==1})


def outgoing(v,chip='ik1303'):
    # Passive original630 carrier identities; values are never written back.
    after={tag:v['fullAfter'][name]['m'][j]
           for name,tags in v['tagsAfter'].items() for j,tag in enumerate(tags)}
    return [after[tag] for tag in v['tagsBefore'][chip]]


def native(negative=False):
    data=json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-t-packet-prepare-native.cjs'),'--proof-input',
        '--clear-u' if negative else '--sign-retry'],text=True))
    report=data['report'];assert report['onlyPublicKeys'] and report['ALL5mirror']
    assert data['extraMarkerPrepared']['registers'][12]==F
    inlet=stage(data,'packet-shift-y');clear=stage(data,'packet-clear-u')
    assert inlet['markers']==['Y','U','Ms:P8','aux1']
    assert clear['markers']==(['Y','U','Ms:P8','aux1'] if negative else ['Y','Ms:P8','aux1'])
    assert clear['words']['Ms:P10']==NUMBER and clear['words']['V']=='FFF000000000'
    assert clear['registers']==inlet['registers'] and clear['program']==inlet['program']
    final=stage(data,'packet-idle')
    assert final['registers']==clear['registers'] and final['program']==clear['program']
    assert final['words']['Ms:P10']==NUMBER and final['markers']==clear['markers']
    audit=report['packetAudit']
    assert audit['checkedWords']==(191520 if negative else 225120)
    assert audit['numberHeld'] and audit['firstDifference'] is None
    assert final['ip']==0x35 and final['pc']=='06'
    assert final['display']==('ЕГГ0Г' if negative else '0,')
    period(data['windows']['packet-idle'],'packet-control/'+('no-lead' if negative else 'reply'))
    for name,records in data['windows'].items():
        if name.startswith('packet-'):preserved_number(records,data['cells'])
    return data


def single_store(v):
    assert v['ip']==0xE9 and v['numericOwner']==['stack:T']
    a=r['concrete_primary'](v['fullBefore']['ik1302'])
    payload=[BitVec('packet_E9_A'+str(j),4) for j in range(12)]
    old=[BitVec('packet_E9_oldT'+str(j),4) for j in range(12)]
    for j in range(12):a.r[3*j]=payload[j];a.m[1+3*j]=old[j]
    p=w['base'](a,0xE9);out=[]
    b=w['ex'](a,0xE9,*q['arbitrary_keys']('packet_E9_keys'),
        serial_inputs=[q['N4'](n) for n in v['fullAfter']['ik1302']['m']],emitted_outputs=out)
    w['prove'](p,And(w['ip'](b)==0xA2,*[out[1+3*j]==payload[j] for j in range(12)],
        *[out[j]==a.m[j] for j in range(42) if j%3!=1 or j>=37]),
        'conditional native E9/T single-store, arbitrary A/oldT, no four-word push')


def third_ack(v):
    a=r['concrete_primary'](v['fullBefore']['ik1306'])
    data=[BitVec('packet_FD_numeric'+str(j),4) for j in range(12)]
    for j in range(12):a.m[1+3*j]=data[j]
    p=w['base'](a,0xFD);out=[]
    model=prior['engine']['models']['ik1306']
    model['execute_command'](a,0xFD,*prior['all5']['pins'](v)['ik1306'],
        serial_inputs=[q['N4'](n) for n in v['fullAfter']['ik1306']['m']],emitted_outputs=out)
    w['prove'](p,And(out[31]==15,*[out[j]==a.m[j] for j in range(42) if j!=31]),
        'conditional IK1306/FD writes low request nibbleF only; all other numeric fields '
        'and high request nibble held, not an arithmetic success theorem')


def third_operand(call,data):
    read=next(v for v in call if
        v['fullBefore']['ik1306']['r'][36]+16*v['fullBefore']['ik1306']['r'][39]==0x16)
    write=next(v for v in call if
        v['fullBefore']['ik1306']['r'][36]+16*v['fullBefore']['ik1306']['r'][39]==0xFF)
    assert chip_owner(data,read,'ik1306')==chip_owner(data,write,'ik1306')==['unclassified:aux0']
    assert raw(read['fullBefore']['ik1306']['m'][1:36:3])==ZERO
    assert raw(read['fullAfter']['ik1306']['r'][0:36:3])==ZERO
    assert raw(outgoing(write,'ik1306')[1:36:3])==ZERO
    model=prior['engine']['models']['ik1306']
    for v,code in ((read,0x16),(write,0xFF)):
        a=r['concrete_primary'](v['fullBefore']['ik1306'])
        symbolic=[BitVec('packet_operand_'+str(code)+'_'+str(j),4) for j in range(12)]
        for j in range(12):
            (a.m if code==0x16 else a.r)[1+3*j if code==0x16 else 3*j]=symbolic[j]
        p=w['base'](a,code);out=[]
        b=model['execute_command'](a,code,*prior['all5']['pins'](v)['ik1306'],
            serial_inputs=[q['N4'](n) for n in v['fullAfter']['ik1306']['m']],emitted_outputs=out)
        wanted=[b.r[3*j] if code==0x16 else out[1+3*j] for j in range(12)]
        w['prove'](p,And(*[wanted[j]==symbolic[j] for j in range(12)]),
            'conditional IK1306/'+f'{code:02X}'+
            (' reads whole numeric aux0 into A' if code==0x16 else ' writes whole A to aux0'))
    print('PASS NATIVE numeric operand is aux0=0, not P10=12345678; '
          'IK1306/16 reads it at',read['word'],'and FF returns0 at',write['word'],
          'all12-field detached read/write contracts passed. '
          'The hoped-for1 requires a native P10->aux0 transfer first.',flush=True)


def check(data,negative=False):
    clear=data['windows']['packet-clear-u']
    sections=[]
    if negative:
        assert len(clear)==1116 and clear[1]['ip']==0x9D
        assert not any(v['ip'] in (0xD6,0xE7,0xA8,0xE9) for v in clear)
        assert {tuple(v['numericOwner']) for v in clear if v['ip']==0x9C}=={
            ('Ms:P9',),('stack:Z',)}
        sections=[('rejected_head',clear[:6]),('error_stop',clear[-12:])]
        print('PASS NATIVE no-lead negative: repeated9C/P9,Z/00; V/FFF never read; '
              'U remains. Not a global timing impossibility.',flush=True)
    else:
        assert len(clear)==129 and clear[0]['ip']==0x9C and clear[1]['ip']==0x9E
        assert clear[0]['numericOwner']==['Ms:V']
        source=next(v for v in clear if v['ip']==0xD6)
        assert source['ordinaryOwner']==['register:R4']
        assert raw(source['fullBefore']['ik1302']['m'][0:36:3])==ZERO
        assert next(v for v in clear if v['ip']==1)['numericOwner']==['stack:Z']
        assert [v for v in clear if v['ip']==1][-1]['numericOwner']==['Ms:U']
        frame=prep['quadruple'](clear,'packet_clear_U')
        assert [v['numericOwner'] for v in frame]==[
            ['stack:Z'],['stack:T'],['stack:X1'],['Ms:U']]
        sections=[('clear_U',clear)]
        for name in ('packet-clear-u-prime','packet-sign'):
            records=data['windows'][name]
            assert len(records)==(1116 if name.endswith('prime') else 1196)
            assert not any(v['ip'] in (0xD6,0xEE,0xE9,0xE7,0xA8) for v in records)
            sections.extend([(name+'_head',records[:6]),(name+'_error',records[-12:])])
        call=data['windows']['packet-sign-retry'];assert len(call)==120
        assert call[0]['numericOwner']==['stack:X'] and call[1]['ip']==0x9E
        store=next(v for v in call if v['ip']==0xE9);single_store(store)
        request=next(v for v in call if v['ip']==0xA3)
        assert request['numericOwner']==['Ms:P9']
        assert raw(request['emitted'][1:36:3])=='320000000000'
        before=call[call.index(request)-1]
        assert before['ip']==0xA2 and before['numericOwner']==['Ms:P8']
        assert stage(data,'packet-idle')['words']['Ms:P9']=='3F0000000000'
        controls=[];replies=[];route=[];third_route=[];other_writes=[]
        for v in call:
            core=v['fullBefore']['ik1303'];ip=core['r'][36]+16*core['r'][39]
            owners=chip_owner(data,v);written=outgoing(v)
            if ip==0x5E and owners==['Ms:P9'] and core['m'][31:35:3]==[2,3]:
                controls.append(v)
            for chip in ('ik1302','ik1303','ik1306'):
                old=v['fullBefore'][chip]['m'];actual=outgoing(v,chip)
                target=chip_owner(data,v,chip)
                if target==['Ms:P9'] and actual[31:35:3]==[15,3] and actual!=old:
                    replies.append((v['word'],chip,
                        v['fullBefore'][chip]['r'][36]+16*v['fullBefore'][chip]['r'][39]))
                if chip=='ik1306' and actual!=old:
                    other_writes.append((v['word'],chip,f'{v["fullBefore"][chip]["r"][36]+16*v["fullBefore"][chip]["r"][39]:02X}',
                        target,raw(old[1:36:3]),raw(actual[1:36:3])))
            if v['word']>=request['word'] and len(route)<35:
                route.append((v['word'],f'{ip:02X}',owners,raw(core['m'][1:36:3]),
                              raw(written[1:36:3])))
                third=v['fullBefore']['ik1306']
                third_route.append((v['word'],f'{third["r"][36]+16*third["r"][39]:02X}',
                    chip_owner(data,v,'ik1306'),raw(third['m'][1:36:3]),
                    raw(third['r'][0:36:3]),third['r'][29]))
        print('SECONDARY TRACE',json.dumps(route),flush=True)
        print('P9 3F WRITERS',json.dumps(replies),'IK1306 WRITES',json.dumps(other_writes),flush=True)
        print('IK1306 TRACE',json.dumps(third_route),flush=True)
        assert controls,'secondary must actually read32/P9, not just a primary write'
        assert replies,'3F must have an observed real outgoing writer (do not assume which chip)'
        assert replies==[(765041,'ik1306',0xFD)]
        third_ack(next(v for v in call if v['word']==765041))
        third_operand(call,data)
        print('PASS NATIVE selected pair P8/P9: primary32 at',request['word'],
              'secondary5E reads32 at',[v['word'] for v in controls],
              '3F writer',replies,flush=True)
        print('BOUNDARY: P10 still12345678, aux0 operand0 returns0. Request delivery and '
              'IK1306/FD low-nibbleF write established; IK1303 keeps its quiet loop. '
              'This does NOT establish arithmetic execution/normal exit/full K1/K2.',flush=True)
        sections.append(('request_reply_formatter',call))
    sections.append(('idle',data['windows']['packet-idle']))
    return sections


def run():
    r['inlet']['immutable_reference']()
    covered=direct=skipped=count=0
    for negative in (False,True):
        data=native(negative);sections=check(data,negative)
        if '--contracts-only' not in sys.argv:
            for label,records in sections:
                a,b=replay(records,'packet-control/'+('negative/' if negative else 'positive/')+label)
                covered+=len(records);direct+=a;skipped+=b;count+=1
        if '--positive-only' in sys.argv:break
    if '--contracts-only' not in sys.argv:
        assert covered==direct+skipped
        print('PASS TOTAL',covered,'words in',count,'SEPARATE ALL5 windows/slices;',
              'direct',direct,'fixed-pin skips',skipped,
              'not entire1116/1196 waits or historical constructor.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
