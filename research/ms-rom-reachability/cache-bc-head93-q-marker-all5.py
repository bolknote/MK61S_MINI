#!/usr/bin/env python3
"""Strict native ALL5 replay, then DETACHED marker/ordering DATA hypotheses.

Only public keys act on the original emulator. Native ALL5 snapshots/tags are
passive, with a fresh observer-free mirror. All later states below are computed
by the original three-chip ROM semantics and two IR buffers/real wires.
The initial marker (and explicitly labelled optional Ms:P9 buffer) is changed
only in this separate model, NEVER loaded into an emulator. No later state or
control register/IP/return/ROM/phase is repaired. Real input schedules include
all key releases; deterministic skips require a complete fixed-input period.
Hypothesis results do not establish a compatible keyboard constructor.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import simplify, is_bv_value

root = Path(__file__).resolve().parent
replay = runpy.run_path(str(root/'cache-bc-head93-native-replay.py'))
m, r, w, q = (replay[n] for n in ('m','r','w','q'))
engine = runpy.run_path(str(root/'cache-stack-lift-ring.py'))
names, models = engine['names'], engine['models']


def number(v):
    v = simplify(v)
    assert is_bv_value(v), ('nonliteral requires a proved case split',v)
    return v.as_long()


def reduce_calculated(state):
    for name in models: state[name] = replay['literal_calculated'](state[name])
    for name in names[:2]: state[name] = [simplify(v) for v in state[name]]
    state['_wire'] = {name:{field:simplify(value) for field,value in fields.items()}
        for name,fields in state['_wire'].items()}
    return state


def initialize(record):
    state, _, phase = engine['make']({'state':record['fullBefore'],'command':record['word']})
    tags = {name:list(record['tagsBefore'][name]) for name in names}
    return state,tags,phase


def compare(state,tags,phase,target,target_tags):
    for name in names:
        for field in ('input','output'):
            assert number(state['_wire'][name][field]) == target[name][field], (name,field)
        if name.startswith('ir'):
            assert [number(v) for v in state[name]] == target[name]['m'], name
            assert phase == target[name]['tick'], name
        else:
            for field in ('r','m','st'):
                assert [number(v) for v in getattr(state[name],field)] == target[name][field], (name,field)
            for field in ('s','s1','l','t','carry'):
                assert number(getattr(state[name],field)) == target[name][field], (name,field)
            assert target[name]['tick'] == 0
        assert tags[name] == target_tags[name], ('carrier tags',name)


def pins(record):
    result={name:(record['fullBefore'][name]['keyX'],record['fullBefore'][name]['keyY'])
        for name in models}
    assert record['keysX'] == [result['ik1302'][0]]*42
    assert record['keysY'] == [result['ik1302'][1]]*42
    return result


def native_replay(native):
    records = native['records']; assert len(records) == 122
    state,tags,phase = initialize(records[0])
    for index, record in enumerate(records):
        compare(state,tags,phase,record['fullBefore'],record['tagsBefore'])
        assert engine['boundary_ip'](state['ik1302']) == record['ip']
        phase, emitted = engine['step'](state,tags,phase,pins(record))
        assert [number(v) for v in emitted['ik1302']] == record['emitted']
        reduce_calculated(state)
        compare(state,tags,phase,record['fullAfter'],record['tagsAfter'])
        if index in (0,40,80,121): print('PASS native ALL5 original word',index+1,flush=True)
    print('PASS122 consecutive native ALL5 ORIGINAL transitions,515 bits per IK, '
          '504 IR cells,10 wires,phase/all630 carrier tags; fresh unobserved full suffix mirror.',flush=True)


def cell_location(state,tags,tag):
    found=[(name,index) for name in names for index,value in enumerate(tags[name]) if value==tag]
    assert len(found)==1
    name,index=found[0]; memory=state[name] if name.startswith('ir') else state[name].m
    return name,index,memory[index]


def numeric_word(state,tags,cells,area,word):
    result=[]
    for field in range(12):
        ids=[i for i,c in enumerate(cells) if c['area']==area and c['word']==word and c['field']==field]
        assert len(ids)==1
        result.append(number(cell_location(state,tags,ids[0])[2]))
    return ''.join(f'{v:X}' for v in reversed(result))


def physical_values(state,tags):
    result=[None]*630
    for name in names:
        memory=state[name] if name.startswith('ir') else state[name].m
        for tag,value in zip(tags[name],memory):
            assert result[tag] is None
            result[tag]=number(value)
    assert all(v is not None for v in result)
    return result


def fingerprint(state,tags,phase,keys):
    result=[phase,*[v for name in models for v in keys[name]]]
    for name in names:
        result.extend(number(state['_wire'][name][field]) for field in ('input','output'))
        if name.startswith('ir'):result.extend(number(v) for v in state[name])
        else:
            for field in ('r','m','st'):result.extend(number(v) for v in getattr(state[name],field))
            for field in ('s','s1','l','t','carry'):result.append(number(getattr(state[name],field)))
        result.extend(tags[name])
    return tuple(result)


def whole_suffix(native,with_marker,*,prepared=False,seeded=False,landmark=None,p9_buffer=False,mode_repair=False):
    assert sum((prepared,seeded,landmark is not None))<=1
    if prepared or seeded:
        initial=native['fullPrepared' if prepared else 'fullSeeded'];source=initial['ik1302']
        entry={'word':0,'fullBefore':initial,'tagsBefore':native['tagsEnd'],
            'keysX':[source['keyX']]*42,'keysY':[source['keyY']]*42}
    elif landmark is not None:entry=native['landmarks'][str(landmark)]
    else:entry=next(v for v in native['records'] if v['word']==1228)
    state,tags,phase=initialize(entry); cells=native['cells']
    initial_values=physical_values(state,tags)
    ids=[i for i,c in enumerate(cells) if c['area']=='Ms' and c['word']=='Q' and c['field']==7]
    assert len(ids)==1; marker=ids[0]
    name,index,value=cell_location(state,tags,marker);assert number(value)==0
    # DETACHED symbolic model ONLY. This is not an emulator setter or a
    # keyboard preparation, and no other field/phase/wire is changed.
    if with_marker:
        memory=state[name] if name.startswith('ir') else state[name].m
        memory[index]=q['N4'](15)
        print('CONDITIONAL MODEL ONLY: Q.field7 0->F',
              'BEFORE first IP9 factory' if prepared else 'BEFORE second IP9' if seeded
              else 'at observed word'+str(entry['word']),'; physical location',
              name,index,'; emulator never receives this state.',flush=True)
    if p9_buffer:
        assert with_marker and prepared
        # A separately labelled INITIAL DATA hypothesis: compensate for the
        # early Q marker redirecting EE to Ms:P9 by copying the already
        # keyboard-created ordinary R9 word there, only in this model.
        # No later memory/control repair, and no such copy in the emulator.
        for field in range(12):
            src=[i for i,c in enumerate(cells) if c['area']=='register' and c['word']=='R9' and c['field']==field]
            dst=[i for i,c in enumerate(cells) if c['area']=='Ms' and c['word']=='P9' and c['field']==field]
            assert len(src)==len(dst)==1
            target_name,target_index,_=cell_location(state,tags,dst[0])
            target_memory=state[target_name] if target_name.startswith('ir') else state[target_name].m
            target_memory[target_index]=q['N4'](initial_values[src[0]])
        assert numeric_word(state,tags,cells,'Ms','P9')=='600010000003'
        print('CONDITIONAL INITIAL DATA ONLY: Ms:P9 numeric12 copied from existing R9; '
              'emulator never receives the marker or buffer.',flush=True)
    keys=pins(entry); changes=[]; visits=[]; writes=[]; actual_changes=[]
    word=entry['word']; end=13440 if prepared else 6720
    schedule=[(0,560,(8,9)),(560,1120,(0,0)),(1120,1680,(11,1)),(1680,6720,(0,0))]
    if prepared:schedule += [(a+6720,b+6720,k) for a,b,k in schedule[:]]
    if mode_repair:
        assert prepared
        schedule += [(13440,14000,(11,9)),(14000,14560,(0,0)),
            (14560,15120,(8,8)),(15120,16800,(0,0)),
            (16800,17360,(8,9)),(17360,17920,(0,0)),
            (17920,18480,(11,1)),(18480,23520,(0,0))]
        end=23520
    factory=None
    seen={};last_segment=None;skipped=0;calculated=0;cycles=[]
    while word<end:
        # Match the ORIGINAL public press schedule, never a release chosen
        # from a controller address. Repeat that SAME schedule for the two
        # complete IP9 reads when starting before the first factory.
        if prepared and word==6720:
            if not with_marker:compare(state,tags,phase,native['fullSeeded'],native['tagsEnd'])
            a=state['ik1302']
            factory={'ip':engine['boundary_ip'](a),'phase':phase,
                'modeR2':number(a.r[2]),'PhiB7':number(a.r[22]),
                'saved0TypeKind':[number(a.st[j]) for j in (25,32,35)],
                'Q':numeric_word(state,tags,cells,'Ms','Q'),
                'X':numeric_word(state,tags,cells,'stack','X'),
                'Y':numeric_word(state,tags,cells,'stack','Y'),
                'Z':numeric_word(state,tags,cells,'stack','Z')}
            print('CONDITIONAL' if with_marker else 'native','FIRST IP9 endpoint',json.dumps(factory),flush=True)
        if mode_repair and word in (13440,16800):
            a=state['ik1302']
            print('MODE REPAIR checkpoint',json.dumps({'word':word,'conditional':with_marker,
                'ip':engine['boundary_ip'](a),'modeR2':number(a.r[2]),
                'saved':[number(a.st[j]) for j in (25,32,35)],
                'Q':numeric_word(state,tags,cells,'Ms','Q'),
                'MsP9':numeric_word(state,tags,cells,'Ms','P9')}),flush=True)
        segment=next((a,b,k) for a,b,k in schedule if a<=word<b)
        keys['ik1302']=segment[2];segment_end=segment[1]
        if last_segment!=segment[0]:
            # A previously equal state under the same pins from an OLDER
            # segment is not evidence of a constant-input period across the
            # intervening key changes. Each period starts afresh here.
            seen.clear();last_segment=segment[0]
        signature=fingerprint(state,tags,phase,keys)
        counters=(len(changes),len(writes),len(actual_changes))
        if signature in seen:
            previous,old_counters=seen[signature];period=word-previous
            repeats=(segment_end-word)//period
            if repeats and counters==old_counters:
                advance=repeats*period;skipped+=advance;word+=advance
                cycles.append({'period':period,'repeats':repeats,'toWord':word})
                print('PASS', 'CONDITIONAL' if with_marker else 'native suffix',
                    'complete ALL5/wires/phase/tags period',period,'skip',advance,
                    'fixed keys, no tracked writers/actual ring changes/marker loss',flush=True)
                seen.clear();continue
        seen[signature]=(word,counters)
        codes={chip:engine['boundary_ip'](state[chip]) for chip in models}
        primary=codes['ik1302'];before_marker=number(cell_location(state,tags,marker)[2])
        q_location=cell_location(state,tags,marker)[:2]
        before_primary=state['ik1302'].m[:]
        before_memories={chip:state[chip].m[:] for chip in models}
        before_tags={chip:tags[chip][:] for chip in models}
        owner_tag=tags['ik1302'][22]
        owner=cells[owner_tag]['area']+':'+str(cells[owner_tag]['word'])
        phase,emitted=engine['step'](state,tags,phase,keys);reduce_calculated(state)
        calculated+=1
        for chip in models:
            for k in range(42):
                old,new=number(before_memories[chip][k]),number(emitted[chip][k])
                if old!=new:
                    actual_changes.append({'word':word,'chip':chip,'ip':f'{codes[chip]:02X}',
                        'cell':cells[before_tags[chip][k]],'before':old,'after':new})
        after_marker=number(cell_location(state,tags,marker)[2])
        if before_marker!=after_marker:
            changed={'word':word,'controllers':{k:f'{v:02X}' for k,v in codes.items()},
                'beforeLocation':q_location,'before':before_marker,'after':after_marker}
            changes.append(changed);print('marker change',json.dumps(changed),flush=True)
        if primary in (0xE5,0xEE,0xA2,0xA3,0xBB,0xBC,0xE7,0xBE):
            event={'word':word,'ip':f'{primary:02X}','owner':owner,'markerF':after_marker==15}
            if primary==0xEE:
                event['inputRaw12']=''.join(f'{number(v):X}' for v in reversed(before_primary[1:36:3]))
            visits.append(event)
            if primary in (0xA3,0xBC,0xE7):
                event['numericChanges']=[j for j in range(1,42,3)
                    if number(emitted['ik1302'][j])!=number(before_primary[j])]
                writes.append(event)
                print('CONDITIONAL' if with_marker else 'native suffix','original writer',json.dumps(event),flush=True)
        word+=1
    if not with_marker:
        compare(state,tags,phase,native['fullEnd'],native['tagsEnd'])
        print('PASS native full',end-entry['word'],'word continuation matches fresh unobserved ALL5 terminal; '
              'same fixed public keys and8 idle frames/read, deterministic skips checked.',flush=True)
    final_values=physical_values(state,tags)
    differences=[{'cell':cells[i],'before':old,'after':new}
        for i,(old,new) in enumerate(zip(initial_values,final_values)) if old!=new]
    ordinary=[v for v in differences if v['cell']['area']=='register']
    program=[v for v in differences if v['cell']['area']=='program']
    a=state['ik1302']
    report={'conditionalOnly':with_marker,'nativeMarkerConstructed':False,
        'emulatorStateNeverLoaded':True,'changedOnlyInitialSymbolicQField7':with_marker and not p9_buffer,
        'initialMsP9BufferHypothesis':p9_buffer,'fixedPublicModeRepair':mode_repair,
        'startsBeforeFirstFactory':prepared,'startsBeforeSecondRead':seeded,
        'initialWord':entry['word'],'initialIP':engine['boundary_ip'](initialize(entry)[0]['ik1302']),
        'firstReadEndpoint':factory,
        'words':end-entry['word'],'calculated':calculated,'skipped':skipped,'cycles':cycles,
        'markerChanges':changes,'visits':visits,'writers':writes,
        'sourceEEReads':[v for v in visits if v['ip']=='EE'],
        'actualRingWriteEvents':len(actual_changes),'actualRingChanges':actual_changes,
        'finalDifferences':differences,'allProgramCellsHeld':not program,'allOrdinaryCellsHeld':not ordinary,
        'finalIP':engine['boundary_ip'](state['ik1302']),
        'controller':{n:number(v) for n,v in {'modeR2':a.r[2],'modeR5':a.r[5],
            'PhiB7':a.r[22],'C7':a.r[23],'T':a.t,'savedTYPE':a.st[32],'savedKIND':a.st[35]}.items()},
        'finalQ':numeric_word(state,tags,cells,'Ms','Q'),
        'finalMsP7':numeric_word(state,tags,cells,'Ms','P7'),
        'finalMsP9':numeric_word(state,tags,cells,'Ms','P9'),
        'finalMsP10':numeric_word(state,tags,cells,'Ms','P10'),
        'finalZ':numeric_word(state,tags,cells,'stack','Z')}
    print(json.dumps({k:v for k,v in report.items() if k not in ('actualRingChanges','visits')},
        ensure_ascii=False),flush=True)
    assert word==end and calculated+skipped==end-entry['word']
    assert tags==native['tagsEnd'] and phase==84
    assert report['allProgramCellsHeld'] and report['allOrdinaryCellsHeld']
    if with_marker:
        assert changes==[]
    if with_marker and not prepared and not seeded and landmark in (None,1212):
        assert report['finalIP']==0x35
        assert report['finalQ']=='0000F0000000'
        assert report['finalMsP7']=='D20000000000'
        assert report['finalMsP9']=='000000000000'
        assert report['finalMsP10']=='600010000003'
        assert [(v['ip'],v['owner']) for v in writes]==[
            ('A3','Ms:P7'),('BC','Ms:P10'),('E7','Ms:P9')]
        assert all(v['cell']['area']=='Ms' for v in differences)
    if with_marker and (seeded or landmark==1200):
        assert not any(v['ip']=='BC' for v in writes)
        assert report['finalMsP10']=='000000000000'
        assert report['finalQ']=='0000F0000000'
    if with_marker and prepared and not p9_buffer:
        assert factory['saved0TypeKind']==[0,0,9]
        assert not any(v['ip']=='BC' for v in writes)
        assert report['finalMsP10']=='000000000000'
    if p9_buffer:
        assert factory['saved0TypeKind']==[0,2,13]
        assert factory['X']==factory['Y']=='000000000000'
        assert not any(v['ip']=='BC' for v in writes)
        assert report['finalMsP9']==report['finalMsP10']=='600010000003'
        assert report['finalQ']=='0000F0000000'
        if mode_repair:
            assert report['finalIP']==0xE6
            assert report['controller']['savedTYPE']==0 and report['controller']['savedKIND']==6
        else:assert report['finalIP']==0x35 and report['controller']['savedTYPE']==2
    if with_marker:
        print('LIMIT this is a DETACHED whole-ring hypothesis, not native Ms-write/hardware evidence '
              'or a compatible marker/control/phase keyboard constructor.',flush=True)
    return report


def run():
    r['inlet']['immutable_reference']()
    native=json.loads(subprocess.check_output(['node',
        str(root/'cache-bc-head93-native-carriers.cjs'),
        '--mode-repair-proof-input' if '--mode-repair-only' in sys.argv else '--all5-proof-input'],text=True))
    assert native['report']['ALL5mirror'] and native['report']['all5Snapshots']
    native_replay(native)
    if '--prepared-only' in sys.argv:
        whole_suffix(native,False,prepared=True)
        whole_suffix(native,True,prepared=True)
    elif '--ordering-only' in sys.argv:
        for stage in ({'seeded':True},{'landmark':1200},{'landmark':1212}):
            baseline=whole_suffix(native,False,**stage)
            hypothesis=whole_suffix(native,True,**stage)
            print('ORDERING RESULT',json.dumps({'stage':stage,
                'actualInitialIP':hypothesis['initialIP'],
                'BCtargets':[v['owner'] for v in hypothesis['writers'] if v['ip']=='BC'],
                'finalMsP10':hypothesis['finalMsP10'],
                'finalQ':hypothesis['finalQ'],'markerChanges':hypothesis['markerChanges']}),flush=True)
    elif '--buffer-only' in sys.argv:
        whole_suffix(native,True,prepared=True,p9_buffer=True)
    elif '--mode-repair-only' in sys.argv:
        whole_suffix(native,False,prepared=True,mode_repair=True)
        whole_suffix(native,True,prepared=True,p9_buffer=True,mode_repair=True)
    else:
        whole_suffix(native,False)
    if not any(flag in sys.argv for flag in ('--baseline-only','--prepared-only','--ordering-only','--buffer-only','--mode-repair-only')):
        whole_suffix(native,True)
    r['inlet']['immutable_reference']()


if __name__=='__main__': run()
