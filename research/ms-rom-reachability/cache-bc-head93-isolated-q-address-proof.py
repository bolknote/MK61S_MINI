#!/usr/bin/env python3
"""Actual READ9/READE addresses after the native single-Q constructor.

Only public keys act on immutable stock references. The two inputs follow
the original01/02 relative-index formula, not a key sweep. Passive ALL5
windows are replayed without checkpoint repair; fresh unobserved mirrors
cover each complete action. The zero-data controls do not prove a payload
transfer or the prepared0/2/D exchange entry.
"""
from pathlib import Path
import runpy

root=Path(__file__).resolve().parent
previous=runpy.run_path(str(root/'cache-bc-head93-native-q-isolated-proof.py'))
reader,r,all5=(previous[n] for n in ('reader','r','all5'))
raw=reader['raw']


def run():
    r['inlet']['immutable_reference']()
    total=0
    for digit,length,source in [('9',134,'register:R4'),('E',149,'register:R9')]:
        native=reader['native']('--q-address'+digit+'-proof-input')
        records=native['windows']['q-address-read'];assert len(records)==length
        assert records[0]['ip']==0x9C and records[-1]['ip']==0xBE
        assert native['isolatedStable']['markers']==['Q','aux0']
        assert native['addressed']['words']['Q']=='0000F0000000'
        assert native['addressed']['registers']==native['isolatedStable']['registers']
        assert native['addressed']['program']==native['isolatedStable']['program']
        assert native['addressed']['ST2']==[0,0,0]
        seek=next(v for v in records if v['ip']==1 and v['numericOwner']==['Ms:Q'])
        assert seek['fullBefore']['ik1302']['m'][22]==15
        counters=[v for v in records if v['ip']==2]
        n=int(digit,16);assert len(counters)==n+1
        assert [v['fullBefore']['ik1302']['r'][29] for v in counters]==list(range(n+1))
        assert all(v['fullBefore']['ik1302']['r'][32]==n for v in counters)
        assert counters[0]['numericOwner']==['Ms:P7']
        d6=next(v for v in records if v['ip']==0xD6)
        assert d6['ordinaryOwner']==[source]
        assert raw(d6['fullAfter']['ik1302']['r'][0:36:3])=='000000000000'
        changes=previous['writers'](records)
        if digit=='9':
            assert [(v['ip'],v['numericOwner']) for v in changes]==[
                (0xE7,['stack:Y']),(0xA8,['stack:Z']),(0xA8,['stack:T']),
                (0xA8,['stack:X1']),(0xE7,['Ms:P9'])]
            assert native['addressed']['words']==native['isolatedStable']['words']
        else:
            assert [(v['ip'],v['numericOwner']) for v in changes]==[
                (0xE7,['Ms:P9']),(0xA8,['Ms:P10']),(0xA8,['unclassified:aux0']),
                (0xA8,['unclassified:aux1']),(0xE7,['Ms:P9'])]
            assert raw(changes[3]['emitted'][1:36:3])=='000FFFFFFFFF'
            assert native['addressed']['words']['aux0']=='000000000000'
            assert native['addressed']['words']['aux1']=='000FFFFFFFFF'
        assert not any(v['ip'] in (0xBB,0xBC,0xC7) for v in records)
        total+=reader['replay'](records,'isolatedQ/READ'+digit)
        print('PASS source-derived READ'+digit,'actually reads',source,
              '; numericQ held; original aux0 '+('held' if digit=='9' else 'moved toaux1')+'.',flush=True)
    assert total==283
    previous['previous']['seek_contracts']()
    r['inlet']['immutable_reference']()
    print('PASS283 original ALL5 transitions in two new address windows. '
          'The native singleQ/791 prefix is reused, not added again. '
          'READ index n reads physical ordinary(n+10) mod15 in this context; '
          'READD is the source-derived candidate for physicalP8. '
          'Zero fixture, no useful payload/0/2/D/BC witness or live experiment.',flush=True)


if __name__=='__main__':run()
