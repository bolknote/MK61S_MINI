#!/usr/bin/env python3
"""Execute the actual PIO text: QPI pins, dummy clocks, FIFO and CE# limits."""
from pathlib import Path
import random,re,unittest
ROOT=Path(__file__).resolve().parents[1]

def programs():
    result={};current=None
    for line in (ROOT/'ports/picocalc/psram_qpi.pio').read_text().splitlines():
        line=line.split(';',1)[0].strip()
        if line.startswith('.program '):
            current={'code':[],'labels':{}};result[line.split()[1]]=current
        elif not line or line.startswith('.'):continue
        elif line.endswith(':'):current['labels'][line[:-1]]=len(current['code'])
        else:
            m=re.fullmatch(r'(.+?) side ([0-3])(?: \[(\d+)\])?',line)
            assert m,line
            current['code'].append((m[1],int(m[2]),1+int(m[3] or 0)))
    return result

def run(program,sent,reply=b''):
    out=[n for b in sent for n in (b>>4,b&15)];source=[n for b in reply for n in (b>>4,b&15)]
    pc=0;x=(len(reply) if reply else len(sent))*2-1;y=0
    elapsed=0;side=1;dirs=15;value=0;writes=0;reads=0;isr=0;bits=0;words=[];edges=[];low=None;max_low=0;irq=False
    while elapsed<2000:
        op,new_side,cycles=program['code'][pc]
        if side&1 and not new_side&1:low=elapsed
        if not side&1 and new_side&1:max_low=max(max_low,elapsed-low);low=None
        if not side&2 and new_side&2:edges.append((elapsed,dirs,value))
        side=new_side;next_pc=pc+1
        if op=='out pins, 4':value=out[writes];writes+=1
        elif op=='in pins, 4':
            assert dirs==0
            isr=((isr<<4)|source[reads])&0xFFFFFFFF;reads+=1;bits+=4
            if bits==32:words.append(isr);isr=0;bits=0
        elif op.startswith('set pindirs, '):dirs=int(op.split(', ')[1])
        elif op.startswith('set y, '):y=int(op.split(', ')[1])
        elif op.startswith('jmp x-- '):
            if x:next_pc=program['labels'][op.split()[-1]]
            x=(x-1)&0xFFFFFFFF
        elif op.startswith('jmp y-- '):
            if y:next_pc=program['labels'][op.split()[-1]]
            y=(y-1)&0xFFFFFFFF
        elif op=='push block':words.append(isr);isr=0;bits=0
        elif op=='irq 0 rel':irq=True
        elif op.startswith('jmp '):break
        else:assert op=='nop',op
        pc=next_pc;elapsed+=cycles
    assert side==1 and low is None
    assert writes==len(out) and reads==len(source)
    return dict(edges=edges,words=words,low=max_low,irq=irq,elapsed=elapsed)

class QpiTests(unittest.TestCase):
    def test_write_all_preloaded_packet_lengths(self):
        p=programs()['mk61_psram_qpi_write'];rng=random.Random(0x515049)
        for count in range(1,33):
            sent=bytes(rng.randrange(256) for _ in range(count));r=run(p,sent)
            self.assertEqual([v for _,d,v in r['edges']], [n for b in sent for n in (b>>4,b&15)])
            self.assertTrue(all(d==15 for _,d,_ in r['edges']))
            self.assertTrue(r['irq']);self.assertEqual(r['low'],count*2*6)
            self.assertLessEqual((count+3)//4,8) # entire TX fits joined FIFO
            self.assertLessEqual(r['low']*10,8000) # 100 MHz worst supported CPU
    def test_read_all_lengths_and_headers(self):
        p=programs()['mk61_psram_qpi_read'];rng=random.Random(0x4542)
        for count in range(1,33):
            for address in (0,1,1023,0x3FFFFF,0x7FFFFF):
                sent=bytes([0xEB])+address.to_bytes(3,'big');reply=bytes(rng.randrange(256) for _ in range(count))
                r=run(p,sent,reply);e=r['edges']
                self.assertEqual([v for _,_,v in e[:8]], [n for b in sent for n in (b>>4,b&15)])
                self.assertTrue(all(d==15 for _,d,_ in e[:8]))
                self.assertTrue(all(d==0 for _,d,_ in e[8:]))
                self.assertEqual(len(e),8+6+count*2) # 6 dummy clocks, then data
                self.assertLessEqual(count//4,8) # autopush never stalls while CE# low
                self.assertEqual(len(r['words']),count//4+1) # final push with CE# high
                for i,b in enumerate(reply):
                    bits=32 if i//4<count//4 else count%4*8
                    self.assertEqual((r['words'][i//4]>>(bits-8-8*(i%4)))&255,b)
                self.assertLessEqual(r['low']*10,8000)
                # Last data edge gets > tACLK(6 ns)+tCLK(48 ns) CE# hold.
                self.assertGreater((r['low']-(e[-1][0]-e[0][0]+2))*8,54)
    def test_pio_instruction_budget(self):
        total=sum(len(p['code']) for p in programs().values())
        spi=sum(bool(re.search(r' side [0-3]',line)) for line in (ROOT/'ports/picocalc/psram_spi.pio').read_text().splitlines())
        self.assertLessEqual(total+spi,32)
if __name__=='__main__':unittest.main()
