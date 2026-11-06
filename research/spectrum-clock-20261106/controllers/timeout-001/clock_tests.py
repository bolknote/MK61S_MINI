import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import clock_hil as c
import clock_protocol as p

def status(mhz=200):
    a,b=p.PLANS[mhz]
    return (f'CCLOCK mhz={mhz} measured_khz={mhz*1000} usb_hz=48000000 usb_khz=48000 '
        f'peri_hz=48000000 sys_div256=256 pio_div256={a} pwm_div16={b} psram_hz={(mhz*1000000*256//a)//6} '
        f'xip_hz={mhz*1000000//4} active=1 lease_ms=105000 changes=1 i2c_clear=1\n')
def echo(sequence=37,challenge=bytes(range(32))):
    rx,data=p.payload(sequence,challenge)
    return ''.join(f'CCDATA at={at} {data[at:at+32].hex().upper()}\n' for at in range(0,2048,32))+f'CCUSB seq={sequence} rx={rx:08X} tx={p.fnv(data):08X} bytes=2048 usb=48000000\n'

class Evidence(unittest.TestCase):
    def test_actual_native_clock_guard(self):
        receipt=json.loads((c.PACKAGE/'ADMIT-002.result/receipt.json').read_text())
        expected=json.loads((c.PACKAGE/'ADMIT-002.json').read_text())['expected']
        for mhz in p.PLANS:
            good=receipt['status_after'].replace('RP2040 125 MHz',f'RP2040 {mhz} MHz')
            good=good.replace('SYS_HZ=125000000',f'SYS_HZ={mhz*1000000}').replace('PERI_HZ=125000000','PERI_HZ=48000000')
            self.assertEqual(c.clock_guard(good,expected,mhz),0)
            for bad in (good.replace('PERI_HZ=48000000','PERI_HZ=50000000'),
                        good.replace('CRASH=NONE','CRASH=HARDFAULT'),good.replace('PHYSICAL_KEYS=0','PHYSICAL_KEYS=1'),
                        good.replace(f'RP2040 {mhz} MHz','RP2040 300 MHz')):
                with self.subTest(mhz=mhz),self.assertRaises(c.Hold):c.clock_guard(bad,expected,mhz,0)
    def test_startup_wait_is_bounded_and_faults_are_strict(self):
        receipt=json.loads((c.PACKAGE/'ADMIT-002.result/receipt.json').read_text())
        expected=json.loads((c.PACKAGE/'ADMIT-002.json').read_text())['expected']
        good=receipt['status_after'].replace('PERI_HZ=125000000','PERI_HZ=48000000')
        waiting=good.replace('KBD=OK','KBD=WAIT').replace('PANEL_INIT=1','PANEL_INIT=0')
        class Port:
            def __init__(self,rows):self.rows=iter(rows);self.waits=0
            def status(self):return next(self.rows)
            def pump(self,seconds):self.waits+=1
        port=Port([waiting,good]);self.assertEqual(c.ready_status(port,expected,125),good)
        self.assertEqual(port.waits,1)
        for bad in (waiting.replace('CRASH=NONE','CRASH=HARDFAULT'),waiting.replace('KBD=WAIT','KBD=FAIL')):
            with self.assertRaises(c.Hold):c.ready_status(Port([bad]),expected,125)
        with patch.object(c.time,'monotonic',side_effect=[0,11]),self.assertRaises(c.Hold):
            c.ready_status(Port([waiting]),expected,125)
    def test_all_profiles(self):
        for mhz in p.PLANS:self.assertEqual(p.clock(status(mhz),mhz,True,1)['mhz'],mhz)
    def test_clock_corruption(self):
        good=status()
        for bad in (good+good,good.replace('48000000','47000000'),good.replace('512','640'),
                    good.replace('200000','200101'),good.replace('sys_div256=256','sys_div256=320'),
                    good.replace('active=1','active=0'),good.replace('changes=1','changes=2'),
                    good.replace('mhz=200','mhz=200 mhz=200'),good.replace('usb_khz=48000','usb_khz=0')):
            with self.subTest(bad=bad),self.assertRaises(p.EvidenceError):p.clock(bad,200,True,1)
    def test_echo_roundtrip(self):
        for sequence in (0,37,0xffffffff):
            self.assertEqual(p.usb(echo(sequence),sequence,bytes(range(32)))['bytes'],2048)
    def test_echo_corruption(self):
        good=echo();rows=good.splitlines(True)
        variants=[good.replace('seq=37','seq=38'),good.replace('bytes=2048','bytes=2047'),
            good.replace('usb=48000000','usb=47999999'),''.join(rows[1:]),
            rows[1]+rows[0]+''.join(rows[2:]),good+rows[-1],good.replace('at=32 ','at=0 '),
            good.replace('at=0 '+rows[0].split()[-1],'at=0 '+'00'*32)]
        for bad in variants:
            with self.subTest(bad=bad[:100]),self.assertRaises(p.EvidenceError):p.usb(bad,37,bytes(range(32)))
        with self.assertRaises(p.EvidenceError):p.usb(good,37,b'x'*32)
    def test_receipt_finalization(self):
        # The first read-only admit hit a duplicate action key at finalization.
        # Verify final receipts can be emitted without opening any device.
        with tempfile.TemporaryDirectory() as temp:
            g=c.Gate.__new__(c.Gate);g.out=Path(temp);g.phase=g.out/'phase';g.phase.write_text('{}')
            g.grant=g.out/'grant';g.grant.write_text('{}');g.j={'action':'admit'}
            g.start=0;g.events=[];g.final={'lease':'reserved_ports_closed'}
            g.finish(True);r=json.loads((g.out/'receipt.json').read_text())
            self.assertEqual(r['status'],'PASS');self.assertEqual(r['action'],'admit')

if __name__=='__main__':unittest.main()
