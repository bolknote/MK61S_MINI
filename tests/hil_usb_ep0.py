#!/usr/bin/env python3
"""Read/validate EP0 on one identity-pinned macOS CDC device, without claiming it.

The CDC identity and IORegistry location select the only libusb handle opened.
No interface detach/claim, valid address/configuration write, endpoint HALT or
bus reset is issued. --strict adds malformed requests that must STALL and then
checks recovery with a valid GET_CONFIGURATION. Firmware installation and MSC
mount/eject are separate HIL steps.
"""
import argparse
import ctypes as c
import ctypes.util
import json
from pathlib import Path
import time

from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import Port
from hil_usb_disk_transaction import usb_tree, walk_nodes, usb_serial


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--public-id',required=True)
    parser.add_argument('--expected-build',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--strict',action='store_true')
    a=parser.parse_args()
    with Port(a.port) as port:
        port.drain();port.write_line('');time.sleep(.2);port.drain()
        identity=parse_identity(port.command('identity',10))
        assert identity.public==a.public_id.upper() and identity.build==a.expected_build.upper(),identity
    nodes=[n for n in walk_nodes(usb_tree()) if n.get('idVendor')==0x483 and
           n.get('idProduct')==0x5740 and usb_serial(n).upper()==identity.usb]
    assert len(nodes)==1,nodes
    location=nodes[0]['locationID'];bus=location>>24;address=nodes[0]['USB Address']
    lib=c.CDLL(ctypes.util.find_library('usb-1.0'))
    def api(name,restype,args):
        fn=getattr(lib,name);fn.restype=restype;fn.argtypes=args;return fn
    init=api('libusb_init',c.c_int,[c.POINTER(c.c_void_p)])
    exit_usb=api('libusb_exit',None,[c.c_void_p])
    listing=api('libusb_get_device_list',c.c_ssize_t,[c.c_void_p,c.POINTER(c.POINTER(c.c_void_p))])
    free=api('libusb_free_device_list',None,[c.POINTER(c.c_void_p),c.c_int])
    get_bus=api('libusb_get_bus_number',c.c_uint8,[c.c_void_p])
    get_address=api('libusb_get_device_address',c.c_uint8,[c.c_void_p])
    get_desc=api('libusb_get_device_descriptor',c.c_int,[c.c_void_p,c.c_void_p])
    open_usb=api('libusb_open',c.c_int,[c.c_void_p,c.POINTER(c.c_void_p)])
    close=api('libusb_close',None,[c.c_void_p])
    string=api('libusb_get_string_descriptor_ascii',c.c_int,[c.c_void_p,c.c_uint8,c.c_void_p,c.c_int])
    transfer=api('libusb_control_transfer',c.c_int,[c.c_void_p,c.c_uint8,c.c_uint8,c.c_uint16,c.c_uint16,c.c_void_p,c.c_uint16,c.c_uint])
    ctx=c.c_void_p();devices=c.POINTER(c.c_void_p)();handle=c.c_void_p();rows=[];passed=False
    assert init(c.byref(ctx))==0
    try:
        count=listing(ctx,c.byref(devices));assert count>=0
        found=[devices[i] for i in range(count) if get_bus(devices[i])==bus and get_address(devices[i])==address]
        assert len(found)==1,(bus,address,len(found))
        descriptor=c.create_string_buffer(18);assert get_desc(found[0],descriptor)==0
        cached=bytes(descriptor);assert cached[8:12]==b'\x83\x04\x40\x57'
        status=open_usb(found[0],c.byref(handle));assert status==0,('libusb_open',status)
        text=c.create_string_buffer(256);n=string(handle,cached[16],text,256)
        assert n>0 and text.raw[:n].decode('ascii').upper()==identity.usb
        def request(bm,req,value,index,length,pipe=False):
            out=c.create_string_buffer(max(length,1));started=time.monotonic_ns()
            n=transfer(handle,bm,req,value,index,out,length,2000)
            rows.append(dict(bm=bm,request=req,value=value,index=index,length=length,result=n,reply=out.raw[:max(n,0)].hex(),us=(time.monotonic_ns()-started)//1000))
            if pipe: assert n==-9,rows[-1];return b''
            assert n>=0,rows[-1]
            return out.raw[:n]
        dev=request(0x80,6,0x100,0,18);assert dev==cached
        cfg=request(0x80,6,0x200,0,9);assert len(cfg)==9 and cfg[:2]==b'\x09\x02'
        length=int.from_bytes(cfg[2:4],'little');assert length==67 and cfg[4]==2 and cfg[5]==1 and cfg[7]==0xC0
        full=request(0x80,6,0x200,0,length);assert len(full)==length and full[:9]==cfg
        for limit in (1,8,18,64,65,255):
            assert request(0x80,6,0x200,0,limit)==full[:limit]
        for index in range(6):
            data=request(0x80,6,0x300|index,0x409 if index else 0,64)
            assert len(data)==data[0] and data[1]==3 and 2<=len(data)<=64
        assert request(0x80,8,0,0,1)==b'\x01'
        assert request(0x80,0,0,0,2)==b'\x01\x00'
        for interface in (0,1):
            assert request(0x81,0,0,interface,2)==b'\0\0'
            assert request(0x81,10,0,interface,1)==b'\0'
        endpoints=[];offset=9
        while offset<len(full):
            size=full[offset];assert size>=2 and offset+size<=len(full)
            if full[offset+1]==5: endpoints.append(full[offset+2])
            offset+=size
        assert sorted(endpoints)==[1,0x82,0x83],endpoints
        for endpoint in (0,0x80,*endpoints):
            assert request(0x82,0,0,endpoint,2)==b'\0\0'
        bad=[(0x80,6,0x600,0,10),(0x80,6,0x700,0,9),(0x80,6,0xF00,0,5)]
        if a.strict:
            bad.extend([(0x80,6,0x101,0,18),(0x80,6,0x201,0,9),(0x80,6,0x306,0x409,64),
                        (0x81,10,0,2,1),(0x81,10,0,0x100,1),(0x82,0,0,0x84,2),(0x82,0,0,0x182,2),
                        (0x80,8,0,0,2),(0x80,0,1,0,2)])
        # SET_CONFIGURATION is deliberately ARM-fixture-only. On macOS a
        # raw malformed value 0x100 deconfigured the device through the host
        # API instead of exercising the 16-bit wire rejection. No configuration
        # or address writes belong in this host read/error test.
        for values in bad:
            request(*values,pipe=True)
            assert request(0x80,8,0,0,1)==b'\x01','EP0 did not recover after STALL'
        passed=True
    finally:
        if handle:close(handle)
        if devices:free(devices,1)
        exit_usb(ctx)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(dict(status='PASS' if passed else 'FAIL',identity=identity.__dict__,location=location,bus=bus,address=address,
                                          strict=a.strict,requests=rows),indent=2)+'\n')
    print('Physical EP0 PASS',identity.public,identity.build,len(rows),'requests',flush=True)


if __name__=='__main__':main()
