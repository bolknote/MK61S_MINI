from pathlib import Path
import subprocess,sys
W=Path(__file__).resolve().parent
for name in ['original507','broad']:
 with(W/(name+'.log')).open('w')as f:subprocess.run([sys.executable,str(W/(name+'.py'))],stdout=f,stderr=subprocess.STDOUT,check=True)
 print(name+' PASS',flush=True)
