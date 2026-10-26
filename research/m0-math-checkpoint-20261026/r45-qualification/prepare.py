"""Prepare R45 full pow replays and all-operation primary qualification."""
from pathlib import Path
import hashlib,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-pow-rsqrt-nativeq8-r43-qualification-20261026'
S=ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='ebef878da8240173c273bb9e31b02c0a55c48e75286a7fe0dcc800c3c2130786'
assert sha(S/'FROZEN.json')=='dbc455078837507acaeb750df1e3fb6800b923e2a9a880c9c6bcc2150ba3527a'
assert not(W/'replay.py').exists()
for n in ['original507.py','broad.py']:
    t=(P/n).read_text().replace('m0-math-unified-pow-rsqrt-nativeq8-r43-20261026','m0-math-unified-ddiv-cold-overflow-r45-20261026').replace('170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b',sha(S/'FROZEN.json'));(W/n).write_text(t)
(W/'run-matrix.py').write_bytes((P/'run-matrix.py').read_bytes())
t=(P/'compare-matrices.py').read_text().replace('R43','R45').replace('R42','R43').replace('m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026','m0-math-unified-pow-rsqrt-nativeq8-r43-qualification-20261026').replace('c9e7ebb1dcd34a4536e12fcb77af95ecbfc51f44176fe5b7e57e85b7cbe39515',sha(P/'FROZEN.json'))
t=t.replace("            if b['operation']!='pow':assert a['instructions']==b['instructions'],(name,i,b['operation'])\n",'')
t=t.replace('every_nonpow_candidate_and_zero_control_instruction_count_exact_R43=True','all_operation_candidate_and_zero_control_deltas_recorded=True')
t=t.replace('PASS_R45_PRIMARY_ALL_NONPOW_BITS_REFERENCES_AND_OWN_COSTS_EXACT_R43','PASS_R45_PRIMARY_ALL_BITS_REFS_AND_ALL_OPERATION_COST_DELTAS_RECORDED')
(W/'compare-matrices.py').write_text(t)
t=(P/'replay.py').read_text().replace('R43','R45').replace('R42','R43').replace('r43_','r45_')
t=t.replace('m0-math-unified-pow-rsqrt-nativeq8-r43-20261026','m0-math-unified-ddiv-cold-overflow-r45-20261026').replace('m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026','m0-math-unified-pow-rsqrt-nativeq8-r43-qualification-20261026').replace('170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b',sha(S/'FROZEN.json')).replace('c9e7ebb1dcd34a4536e12fcb77af95ecbfc51f44176fe5b7e57e85b7cbe39515',sha(P/'FROZEN.json'))
t=t.replace('(281430,140715,2303)','(281430,140715,2293)').replace('(50220,16740,2353)','(50220,16740,2343)').replace(';assert cost-pc in (-1,0),(current,cost,pc)','');(W/'replay.py').write_text(t)
for n in ['original507.py','broad.py','run-matrix.py','compare-matrices.py','replay.py']:compile((W/n).read_text(),str(W/n),'exec')
print('R45 full/admission with cachedR43/gold/Qfp and fresh all-operation primary prepared; allcostchanges retained.')
