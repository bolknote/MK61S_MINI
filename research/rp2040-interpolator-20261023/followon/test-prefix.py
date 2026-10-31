#!/usr/bin/env python3
"""Replay retained CDC replies; this module never constructs a port."""
from pathlib import Path
import hashlib,importlib.util,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=ROOT/'.build/memchr-20261023/m0-hardware-v1'
OUT=ROOT/'.build/rp2040-interpolator-20261023/followon'
spec=importlib.util.spec_from_file_location('_interp002_prefix_fix',HERE/'run-pico.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rows=[]
for session in ('cdc-00','cdc-01','cdc-02'):
 folder=SOURCE/session;status=(folder/'status-000001.txt').read_text()
 intents=[x for x in map(json.loads,(folder/'writes.jsonl').read_text().splitlines()) if x['event']=='intent' and x['purpose']=='ordinary-command']
 files=sorted(folder.glob('command-*.bin'));assert len(intents)==len(files)
 for intent,p in zip(intents,files):
  command=bytes.fromhex(intent['wire_hex']).decode('ascii').removesuffix('\r')
  raw=p.read_bytes();reply=raw.decode('cp1251')
  normalized,prefix=m.correlated_reply(command,reply,status)
  assert normalized.encode('cp1251')==raw[len(prefix.encode('cp1251')):]
  assert m.canonical(command,normalized)==normalized[len(command)+2:-len('\r\nmk61> ')]
  rows.append(dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest(),command=command,prefix=prefix,body_unchanged=True))
status=(SOURCE/'cdc-02/status-000001.txt').read_text()
raw=(SOURCE/'cdc-00/command-000001.bin').read_bytes().decode('cp1251');prefix='X=[ 0,           ]\r\n'
bad=[('unknown','UNKNOWN\r\n'+raw),('fault','CRASH=HARDFAULT\r\n'+raw),('duplicate-notice',prefix+prefix+raw),
 ('wrong-X','X=[ 1,           ]\r\n'+raw),('bad-panel','PICOCALC PANEL INITIALIZED KBD=ERROR\r\n'+raw),
 ('stale-prompt','mk61> '+raw),('missing-echo',raw.removeprefix('identity\r\n')),
 ('duplicate-echo','identity\r\n'+raw),('missing-prompt',raw.removesuffix('\r\nmk61> ')),('duplicate-prompt',raw+'\r\nmk61> '),
 ('binary',prefix+'identity\r\n\x00\r\nmk61> ')]
for name,reply in bad:
 try:m.correlated_reply('identity',reply,status)
 except RuntimeError:continue
 raise AssertionError('Accepted '+name)
for body in ('ERROR: identity failed','CRASH=AVAILABLE','UID=FFFFFFFFFFFFFFFF'):
 normalized,seen=m.correlated_reply('identity',prefix+'identity\r\n'+body+'\r\nmk61> ',status)
 assert m.canonical('identity',normalized)==body and seen==prefix
assert len(rows)==12 and sum(bool(row['prefix']) for row in rows)==2
report=dict(status='PASS_PREFIX_CORRELATION_DELTA',runner_sha256=hashlib.sha256((HERE/'run-pico.py').read_bytes()).hexdigest(),
 actual_fixtures=rows,negative_cases=[x[0] for x in bad],semantic_fault_bodies_preserved=3,USB=False,Flash=False,
 scope='Pure retained-byte replay of author helper. Full raw and source notice bytes remain separate; other checks unchanged.')
(OUT/'prefix-fix-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],actual=len(rows),negative=len(bad),runner_sha256=report['runner_sha256'])))
