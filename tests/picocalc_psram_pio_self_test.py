#!/usr/bin/env python3
"""Check actual PIO packet edges against SPI/PSRAM timing and byte oracles."""
from pathlib import Path
import random,re,unittest

ROOT=Path(__file__).resolve().parents[1]

class PsramPioTests(unittest.TestCase):
    def test_packets_finish_without_cpu_or_tx_dma(self):
        source=(ROOT/'ports/picocalc/psram_spi.pio').read_text()
        instructions=[];labels={}
        for line in source.splitlines():
            line=line.split(';',1)[0].strip()
            if not line or line.startswith('.'):continue
            if line.endswith(':'):labels[line[:-1]]=len(instructions);continue
            match=re.fullmatch(r'(.+?) side ([0-3])(?: \[(\d+)\])?',line)
            self.assertIsNotNone(match,line)
            instructions.append((match[1],int(match[2]),1+int(match[3] or 0)))
        rng=random.Random(0x50494F)
        for count in range(1,17):
            sent=bytes(rng.randrange(256) for _ in range(count))
            reply=bytes(rng.randrange(256) for _ in range(count))
            output=[];captured=[];words=[];isr=0;shifted=0;mosi=0
            pc=0;x=count*8-1;cycles=0;low_since=None;max_low=0;side=1;edges=[]
            while cycles<2000:
                op,new_side,delay=instructions[pc]
                if side&1 and not new_side&1:low_since=cycles
                if not side&1 and new_side&1:
                    max_low=max(max_low,cycles-low_since);low_since=None
                if not side&2 and new_side&2:
                    edges.append(cycles);output.append(mosi)
                side=new_side;next_pc=pc+1
                if op=='out pins, 1':
                    at=len(output);mosi=(sent[at//8]>>(7-at%8))&1
                elif op=='in pins, 1':
                    at=len(captured);bit=(reply[at//8]>>(7-at%8))&1
                    captured.append(bit);isr=((isr<<1)|bit)&0xFFFFFFFF;shifted+=1
                    if shifted==32:words.append(isr);isr=0;shifted=0
                elif op=='jmp x-- bitloop':
                    if x:next_pc=labels['bitloop']
                    x=(x-1)&0xFFFFFFFF
                elif op=='push block':words.append(isr);isr=0;shifted=0
                elif op=='jmp halt':break
                else:self.assertEqual(op,'nop')
                pc=next_pc;cycles+=delay
            self.assertEqual(output,[(b>>(7-i))&1 for b in sent for i in range(8)])
            self.assertEqual(captured,[(b>>(7-i))&1 for b in reply for i in range(8)])
            self.assertEqual(len(words),count//4+1)
            for i,byte in enumerate(reply):
                bits=32 if i//4<count//4 else count%4*8
                self.assertEqual((words[i//4]>>(bits-8-8*(i%4)))&255,byte)
            self.assertTrue(all(b-a==6 for a,b in zip(edges,edges[1:])))
            self.assertEqual(max_low,count*8*6)
            self.assertLessEqual(max_low*8,8000)  # 125 MHz: 8 ns/cycle; CE# <=8 us.
            self.assertEqual(side,1)             # CE# high, SCK low before CPU resumes.
            self.assertIsNone(low_since)

if __name__=='__main__':unittest.main()
