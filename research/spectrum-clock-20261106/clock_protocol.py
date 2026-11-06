"""Pure HOST validation for native clock/USB evidence; never opens devices."""
import re

PLANS={mhz:((mhz*64+24)//25,(mhz*4+24)//25) for mhz in (125,*range(130,251,10))}
LEASE_MS=105000
class EvidenceError(ValueError):pass
def need(value,message):
    if not value:raise EvidenceError(message)

def fields(text,prefix,expected,hexkeys=()):
    rows=[line.strip() for line in text.splitlines() if line.startswith(prefix+' ')]
    need(len(rows)==1,'Missing or duplicated '+prefix)
    pairs=[]
    for word in rows[0].split()[1:]:
        pair=word.split('=');need(len(pair)==2,'Malformed '+prefix+' field');pairs.append(pair)
    need(len({k for k,v in pairs})==len(pairs),'Duplicated '+prefix+' field')
    need({k for k,v in pairs}==set(expected),'Unexpected '+prefix+' fields')
    for k,v in pairs:
        need(re.fullmatch(r'[0-9A-Fa-f]{8}' if k in hexkeys else r'[0-9]+',v),
             'Malformed '+prefix+' '+k)
    return {k:int(v,16 if k in hexkeys else 10) for k,v in pairs}

def clock(text,mhz,active,changes):
    need(mhz in PLANS,'Unsupported clock')
    r=fields(text,'CCLOCK',('mhz','measured_khz','usb_hz','usb_khz','peri_hz','sys_div256',
        'pio_div256','pwm_div16','psram_hz','xip_hz','active','lease_ms','changes','i2c_clear'))
    pio,pwm=PLANS[mhz]
    expected=dict(mhz=mhz,usb_hz=48000000,peri_hz=48000000,sys_div256=256,
        pio_div256=pio,pwm_div16=pwm,psram_hz=(mhz*1000000*256//pio)//6,xip_hz=mhz*1000000//4,
        active=int(active),lease_ms=LEASE_MS,changes=changes,i2c_clear=1)
    need(all(r[k]==v for k,v in expected.items()),'Clock plan/readback mismatch')
    need(abs(r['measured_khz']-mhz*1000)<=100,'CPU counter mismatch')
    need(abs(r['usb_khz']-48000)<=100,'USB counter mismatch')
    return r

def fnv(data):
    h=2166136261
    for value in data:h=((h^value)*16777619)&0xffffffff
    return h

def payload(sequence,challenge):
    need(type(sequence) is int and 0<=sequence<=0xffffffff and len(challenge)==32,'Bad USB challenge')
    rx=fnv(challenge);rng=rx^sequence;data=bytearray()
    for _ in range(2048):
        rng=(rng*1664525+1013904223)&0xffffffff;data.append(rng>>24)
    return rx,bytes(data)

def usb(text,sequence,challenge):
    rx,expected=payload(sequence,challenge)
    rows=[line.strip() for line in text.splitlines() if line.startswith('CCDATA ')]
    need(len(rows)==64,'Missing or duplicated USB data row')
    data=bytearray()
    for i,line in enumerate(rows):
        m=re.fullmatch(r'CCDATA at=([0-9]+) ([0-9A-F]{64})',line)
        need(m is not None and int(m[1])==i*32,'USB data order/encoding mismatch')
        data.extend(bytes.fromhex(m[2]))
    r=fields(text,'CCUSB',('seq','rx','tx','bytes','usb'),('rx','tx'))
    need(r==dict(seq=sequence,rx=rx,tx=fnv(expected),bytes=2048,usb=48000000),
         'USB sequence/checksum/clock mismatch')
    need(data==expected and fnv(data)==r['tx'],'USB data corruption')
    return r
