from pathlib import Path
import subprocess,sys
W=Path(__file__).resolve().parent
for phase in ['power','edge','admission']:
 with(W/(phase+'.log')).open('w')as f:subprocess.run([sys.executable,str(W/'replay.py'),phase],stdout=f,stderr=subprocess.STDOUT,check=True)
 print(phase+' PASS',flush=True)
