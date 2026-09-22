"""End-to-end assertions against the real MK61 ROM/core, not a game model."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def play(commands):
    r=subprocess.run([sys.argv[1],str(ROOT/'programs/games/ELITE')],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True,timeout=120)
    states=[json.loads(line) for line in r.stdout.splitlines()]
    for s in states:
        assert not s['running'] and not s['error'],s
    return states

def main():
    start,again=play(['run','input 0'])
    assert start['frame']==[73,0,121,56,6,120,121,0,73,0,57,55],start
    assert start['pages'][0]==[1000,0,0,0,84,42,40,0,12345],start
    assert again['pages'][5][0]==1000,again
    print('ELITE real-core: title, twelve cells, packed data, 55/56 read/write and return OK')

if __name__=='__main__':main()
