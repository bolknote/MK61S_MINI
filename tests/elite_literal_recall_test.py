"""Compare automatic literal lift with explicit ENTER on the actual ROM."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/elite'),str(ROOT/'tools')]
from assembler import Assembler
from program_pack import program_binary


def run_case(directory,runner,register,stored,literal,probe,lift):
    a=Assembler()
    m=a.module(0,'literal probe').raw(0x2F,0x50,0x2F,0x2A).set(register,stored)
    # Keep nontrivial lower stack and last-X values across the tested pair.
    m.n(7).n(8).op('+').n(11).n(22).n(33).n(44)
    m.ld(register).n(literal,lift=lift)
    if probe=='stack':
        m.st('A').op('roll').st('B').op('roll').st('C').op('roll').st('D')
    elif probe=='last_x':m.raw(0x0F).st('E')
    else:m.raw(0x0C).st('F') # Observe decimal-entry X2 through exponent entry.
    m.op('stop')
    banks,_=a.link()
    image=b''.join(banks.get(bank,bytes(112)) for bank in range(32))
    (directory/'elite.bin').write_bytes(program_binary(image))
    result=subprocess.run([runner,str(directory)],input='run\n',text=True,
                          capture_output=True,check=True,timeout=30)
    state=json.loads(result.stdout)
    assert not state['running'] and not state['error'],state
    return {key:state[key] for key in ('x','regs','pages','frame','auto_display','segmented')}


def main():
    # A label can admit a path that did not execute the preceding recall.
    a=Assembler();m=a.module(0,'label boundary').ld(0).label('entry').n(1)
    assert m.items[-1].value[0]==0x0E
    checked=0
    with TemporaryDirectory(prefix='elite-literal-recall-') as temporary:
        directory=Path(temporary)
        (directory/'autoexec.m61').write_text('reinit\nload 0000 elite.bin\nrun\n')
        for register in (0,'F'):
            for stored in (0,1,-1,99999999,-99999999):
                for literal in (0,1,-1,16,1000000,99999999):
                    for probe in ('stack','last_x','x2'):
                        before=run_case(directory,sys.argv[1],register,stored,literal,probe,True)
                        after=run_case(directory,sys.argv[1],register,stored,literal,probe,None)
                        assert before==after,(register,stored,literal,probe,before,after)
                        checked+=1
    print(f'ELITE real-core: {checked} recall/literal pairs preserve stack, X1 and X2',flush=True)


if __name__=='__main__':main()
