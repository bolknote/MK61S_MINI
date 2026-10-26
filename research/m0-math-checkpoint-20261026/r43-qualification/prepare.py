"""R43 fresh candidate replays with pinned cached references, and fresh primary tests."""
from pathlib import Path
import hashlib,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026'
S=ROOT/'.build/m0-math-unified-pow-rsqrt-nativeq8-r43-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='c9e7ebb1dcd34a4536e12fcb77af95ecbfc51f44176fe5b7e57e85b7cbe39515'
assert sha(S/'FROZEN.json')=='170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b'
assert not(W/'replay.py').exists()
for n in ['original507.py','broad.py']:
    t=(P/n).read_text().replace('m0-math-unified-pow-rsqrt-seedreuse-r42-20261026','m0-math-unified-pow-rsqrt-nativeq8-r43-20261026').replace('b5e0bf1e6316a2bc0924127f0b9564c025cb042842f4d3527ce1eef8fd48a676',sha(S/'FROZEN.json'));(W/n).write_text(t)
(W/'run-matrix.py').write_bytes((P/'run-matrix.py').read_bytes())
t=(P/'compare-matrices.py').read_text().replace('R42','R43').replace('R41','R42').replace('m0-math-unified-pow-rsqrt-negfirst-r41-qualification-20261026','m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026').replace('aa13981ded8055e02cd9c4fb5ee3106bc200e1210ce72bba1e5688aa32a55884',sha(P/'FROZEN.json'));(W/'compare-matrices.py').write_text(t)
t=(P/'replay.py').read_text().replace('R42','R43').replace('R41','R42').replace('r42_','r43_')
t=t.replace('m0-math-unified-pow-rsqrt-seedreuse-r42-20261026','m0-math-unified-pow-rsqrt-nativeq8-r43-20261026').replace('m0-math-unified-pow-rsqrt-negfirst-r41-qualification-20261026','m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026').replace('b5e0bf1e6316a2bc0924127f0b9564c025cb042842f4d3527ce1eef8fd48a676',sha(S/'FROZEN.json')).replace('aa13981ded8055e02cd9c4fb5ee3106bc200e1210ce72bba1e5688aa32a55884',sha(P/'FROZEN.json'))
t=t.replace('(281430,140715,2312)','(281430,140715,2303)').replace('(50220,16740,2368)','(50220,16740,2353)');(W/'replay.py').write_text(t)
for n in ['original507.py','broad.py','run-matrix.py','compare-matrices.py','replay.py']:compile((W/n).read_text(),str(W/n),'exec')
print('R43 full/admission prepared, cached R42/Qfp/MPFR explicitly; primary fresh.')
