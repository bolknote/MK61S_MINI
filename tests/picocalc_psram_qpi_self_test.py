#!/usr/bin/env python3
"""Execute production PIO with finite FIFOs and deliberately stalled DMA."""
from pathlib import Path
import collections, random, re, unittest
ROOT=Path(__file__).resolve().parents[1]

def programs(source="psram_qpi.pio"):
    result={};current=None
    for line in (ROOT/'ports/picocalc'/source).read_text().splitlines():
        line=line.split(';',1)[0].strip()
        if line.startswith('.program '):
            current={'code':[],'labels':{}};result[line.split()[1]]=current
        elif not line or line.startswith('.'):continue
        elif line.endswith(':'):current['labels'][line[:-1]]=len(current['code'])
        else:
            m=re.fullmatch(r'(.+?) side ([0-3])(?: \[(\d+)\])?',line);assert m,line
            current['code'].append((m[1],int(m[2]),1+int(m[3] or 0)))
    return result

def execute(program,packets,reply=(),stalls=False,sample_trace=None,burst=False,dropped=None):
    reading=bool(reply);size=len(packets[0]);word_count=(size+3)//4
    if burst:
        sent=[(len(data)*2-1)<<24 | int.from_bytes(p[1:],'big') for p,data in zip(packets,reply)]
    else:
        sent=[int.from_bytes(p[i:i+4].ljust(4,b'\0'),'big') for p in packets for i in range(0,len(p),4)]
    source=[n for packet in reply for byte in packet for n in (byte>>4,byte&15)]
    tx=collections.deque();rx=collections.deque();output=[];frames=[]
    tx_at=0;read_at=0
    elapsed=0;pc=0;x=y=0;osr=0;out_bits=32;isr=size*2-1 if not reading else 0;in_bits=0
    side=1;dirs=15;value=0;frame=None;low=None;max_low=0
    def dma():
        nonlocal tx_at
        # Long starvation is intentional: correctness must not depend on
        # DMA/IRQ service before the PSRAM's 8 us CE# deadline.
        feeding=not stalls or elapsed%997>260
        draining=not stalls or elapsed%1301>500
        if feeding and tx_at<len(sent) and len(tx)<(4 if reading else 8):
            tx.append(sent[tx_at]);tx_at+=1
        if draining and rx:output.append(rx.popleft())
    def advance(cycles):
        nonlocal elapsed
        for _ in range(cycles):elapsed+=1;dma()
    while elapsed<1000000:
        dma()
        if pc==0 and side==1 and len(frames)==len(packets) and not tx and tx_at==len(sent) and not rx:
            assert low is None and (not reading or read_at==len(source))
            return frames,output,max_low
        op,new_side,cycles=program['code'][pc];next_pc=(pc+1)%len(program['code'])
        if side&1 and not new_side&1:low=elapsed;frame=[]
        if not side&1 and new_side&1:
            max_low=max(max_low,elapsed-low);frames.append((frame,elapsed-low,elapsed));low=None
        if not side&2 and new_side&2:frame.append((elapsed,dirs,value))
        side=new_side
        if op.startswith('pull '):
            needed='ifempty' not in op or out_bits>=32
            if needed:
                if not tx:
                    assert side&1,('TX stall with CE# low',pc,elapsed)
                    advance(1);continue
                osr=tx.popleft();out_bits=0
        elif op=='out pins, 4':
            assert out_bits<32
            value=(osr>>28)&15;osr=(osr<<4)&0xFFFFFFFF;out_bits+=4
        elif op=='out x, 8':
            x=osr>>24;osr=(osr<<8)&0xFFFFFFFF;out_bits+=8
        elif op=='in pins, 4':
            if sample_trace is not None:sample_trace.append((elapsed,read_at))
            assert dirs==0 and read_at<len(source)
            isr=((isr<<4)|source[read_at])&0xFFFFFFFF;read_at+=1;in_bits+=4
            if in_bits==32 and not burst:
                assert len(rx)<4,('RX stall with CE# low',elapsed)
                rx.append(isr);isr=in_bits=0
        elif op=='push iffull noblock':
            if in_bits==32:
                if len(rx)<4:rx.append(isr)
                else:dropped.append(elapsed)
                isr=in_bits=0
        elif op=='mov x, status':x=0xFFFFFFFF if (len(rx)<1 if reading else len(tx)<word_count) else 0
        elif op=='mov y, status':y=0xFFFFFFFF if not rx else 0
        elif op=='mov x, isr':x=isr
        elif op.startswith('set pindirs, '):dirs=int(op.split(', ')[1])
        elif op.startswith('set pins, '):value=int(op.split(', ')[1])
        elif op.startswith('set y, '):y=int(op.split(', ')[1])
        elif op.startswith('set x, '):x=int(op.split(', ')[1])
        elif op.startswith('jmp x-- '):
            if x:next_pc=program['labels'][op.split()[-1]]
            x=(x-1)&0xFFFFFFFF
        elif op.startswith('jmp y-- '):
            if y:next_pc=program['labels'][op.split()[-1]]
            y=(y-1)&0xFFFFFFFF
        elif op.startswith('jmp !x '):
            if not x:next_pc=program['labels'][op.split()[-1]]
        elif op.startswith('jmp !y '):
            if not y:next_pc=program['labels'][op.split()[-1]]
        else:assert op=='nop',op
        pc=next_pc;advance(cycles)
    raise AssertionError(('PIO did not finish',elapsed,pc,len(frames),len(tx),len(rx),tx_at,len(sent)))

class QpiTests(unittest.TestCase):
    def test_write_variable_packets_and_stalled_tx(self):
        p=programs()['mk61_psram_qpi_write'];rng=random.Random(0x515049)
        for count in range(1,33):
            for batch in (1,3,19):
                packets=[bytes(rng.randrange(256) for _ in range(count)) for _ in range(batch)]
                frames,_,low=execute(p,packets,stalls=True)
                for (edges,_,_),data in zip(frames,packets):
                    self.assertEqual([v for _,_,v in edges],[n for b in data for n in (b>>4,b&15)])
                    self.assertTrue(all(d==15 for _,d,_ in edges))
                self.assertEqual(low,count*2*6)
                self.assertLessEqual(low*10,8000)
    def test_read_batches_with_stalled_tx_and_rx(self):
        p=programs()['mk61_psram_qpi_read'];rng=random.Random(0x4542)
        for batch in (1,2,19,64,108,128):
            for base in (0,1008,0x7FFFF0-(batch-1)*16):
                headers=[bytes([0xEB])+(base+i*16).to_bytes(3,'big') for i in range(batch)]
                replies=[bytes(rng.randrange(256) for _ in range(16)) for _ in range(batch)]
                frames,words,low=execute(p,headers,replies,stalls=True)
                self.assertEqual(b''.join(x.to_bytes(4,'big') for x in words),b''.join(replies))
                for (edges,duration,end),header in zip(frames,headers):
                    self.assertEqual([v for _,_,v in edges[:8]],[n for b in header for n in (b>>4,b&15)])
                    self.assertEqual(len(edges),8+6+32)
                    self.assertTrue(all(d==15 for _,d,_ in edges[:8]))
                    self.assertTrue(all(d==0 for _,d,_ in edges[8:]))
                    self.assertGreater((end-edges[-1][0])*8,54)
                    self.assertLessEqual(duration*10,8000)
                self.assertLessEqual(low*10,8000)
    def test_ai_read_clock_packet_bounds(self):
        p=programs()['mk61_psram_qpi_read']
        headers=[bytes([0xEB])+(1008+i*16).to_bytes(3,'big') for i in range(128)]
        replies=[bytes((i+j)&255 for j in range(16)) for i in range(128)]
        frames,words,low=execute(p,headers,replies,stalls=True)
        self.assertEqual(b''.join(x.to_bytes(4,'big') for x in words),b''.join(replies))
        # Fractional PIO phase can move an edge by one SYS tick. Bound that
        # uncertainty for25/33.3/45MHz read candidates, not just mean clocks.
        for div in (461,346,256):
            def earliest_ns(cycles):return (cycles*div//256)*1000000000/270000000
            def latest_ns(cycles):return ((cycles*div+255)//256)*1000000000/270000000
            self.assertLess(latest_ns(low),4000)  # Stricter extended grade CE#.
            previous_end=None
            for edges,duration,end in frames:
                self.assertGreaterEqual(earliest_ns(end-edges[-1][0]),3)
                if previous_end is not None:
                    self.assertGreaterEqual(earliest_ns(end-duration-previous_end),18)
                previous_end=end
            self.assertGreaterEqual(earliest_ns(1),2.5)  # Header CE# setup.
            self.assertGreaterEqual(earliest_ns(3),0.45*11.9)  # High/low width.

    def test_late_sample_preserves_clock_waveform(self):
        new=programs('psram_qpi_late.pio')['mk61_psram_qpi_read']
        old=programs()['mk61_psram_qpi_read']
        self.assertEqual(programs()['mk61_psram_qpi_write'],programs('psram_qpi_late.pio')['mk61_psram_qpi_write'])
        at=new['labels']['read_nibble']
        self.assertEqual(new['code'][at:at+3],[('nop',2,3),('in pins, 4',0,1),('jmp x-- read_nibble',0,2)])
        self.assertEqual(old['code'][at:at+3],[('nop',2,2),('in pins, 4',2,1),('jmp x-- read_nibble',0,3)])
        headers=[bytes([0xEB])+(1008+i*16).to_bytes(3,'big') for i in range(128)]
        replies=[bytes((i*37+j*13)&255 for j in range(16)) for i in range(128)]
        for stalled in (False,True):
            before=[];after=[]
            a,aw,al=execute(old,headers,replies,stalls=stalled,sample_trace=before)
            b,bw,bl=execute(new,headers,replies,stalls=stalled,sample_trace=after)
            self.assertEqual(aw,bw);self.assertEqual(al,bl)
            for i,((ae,ad,az),(be,bd,bz)) in enumerate(zip(a,b)):
                ast=az-ad;bst=bz-bd
                self.assertEqual(ad,bd)
                self.assertEqual([(t-ast,d,v) for t,d,v in ae],[(t-bst,d,v) for t,d,v in be])
                for j in range(32):
                    self.assertEqual(after[i*32+j][0]-bst,before[i*32+j][0]-ast+1)
            if not stalled:self.assertEqual(a,b)

    def test_instruction_budget(self):
        spi=sum(bool(re.search(r' side [0-3]',x)) for x in (ROOT/'ports/picocalc/psram_spi.pio').read_text().splitlines())
        for source in ('psram_qpi.pio','psram_qpi_late.pio'):
            count=sum(len(p['code']) for p in programs(source).values())
            self.assertLessEqual(count+spi,32)
            burst=programs('psram_qpi_burst.pio')['mk61_psram_qpi_burst']
            self.assertEqual(len(burst['code']),spi+len(programs(source)['mk61_psram_qpi_read']['code']))

    def test_variable_read_bursts_and_rx_starvation(self):
        p=programs('psram_qpi_burst.pio')['mk61_psram_qpi_burst']
        rng=random.Random(0x50494F)
        sizes=(16,64,32,32,64,16)*9
        addresses=(1008,1024,1120,0x7FFFE0,0x7FFFC0,0x7FFFF0)*9
        headers=[b'\xeb'+at.to_bytes(3,'big') for at in addresses]
        replies=[rng.randbytes(size) for size in sizes]
        def ns(cycles,upper=False):
            return ((cycles*461+(255 if upper else 0))//256)*1e9/270e6
        for stalled in (False,True):
            drops=[]
            frames,words,low=execute(p,headers,replies,stalls=stalled,burst=True,dropped=drops)
            self.assertEqual(len(words)+len(drops),sum(sizes)//4)
            if stalled:self.assertTrue(drops)
            else:
                self.assertFalse(drops)
                self.assertEqual(b''.join(w.to_bytes(4,'big') for w in words),b''.join(replies))
            self.assertLess(ns(low,True),8000)
            previous=None
            for (edges,duration,end),header,size in zip(frames,headers,sizes):
                self.assertEqual([v for _,_,v in edges[:8]],[n for b in header for n in (b>>4,b&15)])
                self.assertEqual(len(edges),8+6+2*size)
                self.assertTrue(all(d==15 for _,d,_ in edges[:8]))
                self.assertTrue(all(d==0 for _,d,_ in edges[8:]))
                self.assertTrue(all(b[0]-a[0]==6 for a,b in zip(edges[14:],edges[15:])))
                self.assertGreaterEqual(ns(end-edges[-1][0]),20)
                if previous is not None:self.assertGreaterEqual(ns(end-duration-previous),50)
                previous=end
if __name__=='__main__':unittest.main()
