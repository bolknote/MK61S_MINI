#!/usr/bin/env python3
"""Pinned baseline/VM HIL. Only our /VMHIL files and test registers are written.

Firmware/System installation is separate. No format or backups. Optional USB
tests take the display and inject keys; physical M61 checks run before that.
"""
import argparse
import json
import time
from pathlib import Path

from hil_c6_system_bootstrap import write_file,read_file
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort,PROMPT
from hil_portable_system_apps import registers,png
from hil_usb_disk_transaction import listing_entries

FIXTURES={
    "arith.tbi":b"10 A=6*7\n20 .R0=A\n30 .R1=SIN(0)+COS(0)+SQRT(16)+LN(EXP(1))\n40 END\n",
    "loops.tbi":b"10 S=0\n20 FOR I=1 TO 5\n30 GOSUB 100\n40 NEXT I\n50 .R2=S;END\n100 @(I)=I*2;S=S+@(I);RETURN\n",
    "state.tbi":b"10 .R3=A\n20 .R4=@(5)\n30 END\n",
    "input.tbi":b"10 FOR I=1 TO 2\n20 INPUT @(I)\n30 NEXT I\n40 .R5=@(1)+@(2)\n50 END\n",
    "arith.foc":b"1.10 S A=2+3*4\n1.20 S .R6=A\n1.30 E\n",
    "loops.foc":b"1.10 S S=0\n1.20 F I=1,3;D 2\n1.30 S .R7=S\n1.40 E\n2.10 S S=S+I\n",
    "loader.m61":b'open "arith.tbi"\nopen "loops.tbi"\nopen "state.tbi"\nret\n',
}
EXTENDED_FIXTURES={
    # Numeric boundaries must survive compiler/runner eviction and the
    # public double register interface, regardless of internal cell type.
    "numeric.tbi":(
        b"10 S=0;FOR I=2147483646 TO 2147483648;S=S+1;NEXT I\n"
        b"20 .RA=2147483647+1-2147483648;.RB=281474976710655 MOD 65536\n"
        b"30 .RC=INT(-7/2);.RD=S;END\n"),
    "numeric.foc":(
        b"1.10 S S=0\n1.20 F I=2147483646,2147483648;S S=S+1\n"
        b"1.30 S .RA=2147483647+1-2147483648\n"
        b"1.40 S .RB=INT(281474976710655/536870912)\n"
        b"1.50 S .RC=INT(-7/2)\n1.60 S .RD=S\n1.70 E\n"),
    # Source fits BASIC's original 3584 bytes; bytecode exceeds the 3184-byte
    # in-WORKSPACE slot and therefore stays beside the USB session over INPUT.
    "large.tbi":b"10 A=0\n"+b"".join(
        ("%u A=A+A+A+A+A+A+A\n"%(20+i*10)).encode() for i in range(120))+
        b"2000 INPUT @(2)\n2010 .R8=@(2)\n2020 END\n",
    "input.foc":b"1.10 S S=0\n1.20 F I=1,2;D 2\n1.30 S .R9=S\n1.40 E\n2.10 A X\n2.20 S S=S+X\n",
}

def health(port):
    reports={c:port.command(c,timeout=15) for c in ("identity","mpu status","crash show","df","prof")}
    assert "CRASH none" in reports["crash show"],reports
    assert "FIRMWARE CRC state=valid" in reports["df"],reports
    assert "enabled=1 layout=ok" in reports["mpu status"],reports
    return reports

def require_foreground(port):
    response=port.text[port.open_text_start:]
    assert b"Open failed!" not in response,response
    assert not PROMPT.search(response),f"foreground returned before test keys: {response!r}"

def run():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port",required=True);ap.add_argument("--public-id",required=True)
    ap.add_argument("--build-id",required=True);ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--profile",choices=("classic-v3-uc1609","mini-v3-a00"),default="classic-v3-uc1609")
    ap.add_argument("--install-fixtures",action="store_true")
    ap.add_argument("--screen",action="store_true")
    ap.add_argument("--extended",action="store_true",help="large image, USB reattach and FOCAL INPUT")
    ap.add_argument("--install-extended-fixtures",action="store_true")
    args=ap.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    assert not args.extended or args.screen,"extended checks require --screen"
    result={"status":"RUNNING","checks":[],"runs":[]}
    mini=args.profile=="mini-v3-a00"
    number15=(21,17,29) if mini else (9,13,37)
    with ScreenPort(args.port,keyboard_layout=0 if mini else 1) as port:
        identity=parse_identity(port.command("identity"))
        assert identity.public==args.public_id.upper() and identity.build==args.build_id.upper(),identity
        assert identity.profile==args.profile,identity
        try:
            if args.install_fixtures:
                root=listing_entries(port.command("ls /"))
                assert not any(e.split("\t")[-1].rstrip("/").casefold()=="vmhil" for e in root),root
                port.command("mkdir /VMHIL")
                for name,data in FIXTURES.items():
                    write_file(port,"/VMHIL/"+name,data);read_file(port,"/VMHIL/"+name,data)
            else:
                for name,data in FIXTURES.items():read_file(port,"/VMHIL/"+name,data)
            if args.install_extended_fixtures:
                names={e.split("\t")[-1].casefold() for e in listing_entries(port.command("ls /VMHIL"))}
                for name,data in EXTENDED_FIXTURES.items():
                    # Never replace an existing file with unverified contents.
                    if name.casefold() not in names:write_file(port,"/VMHIL/"+name,data)
                    read_file(port,"/VMHIL/"+name,data)
            elif args.extended:
                for name,data in EXTENDED_FIXTURES.items():read_file(port,"/VMHIL/"+name,data)
            result["before"]=health(port)
            for repeat in range(3):
                started=time.monotonic()
                report=port.command('open "/VMHIL/loader.m61"',timeout=20)
                values,register_report=registers(port)
                assert values["R0"]==42 and abs(values["R1"]-6)<0.00001,(values,report)
                assert values["R2"]==30 and values["R3"]==42 and values["R4"]==10,(values,report)
                result["runs"].append({"test":"physical-M61","repeat":repeat,"seconds":time.monotonic()-started})
                print("physical M61: arithmetic/FOR/GOSUB/array/retained values PASS",flush=True)
            result["checks"].append("physical-M61-language-state")
            if args.screen:
                port.attach();port.pump(.3)
                for name,register,value in (("arith.tbi","R0",42),("arith.foc","R6",14),("loops.foc","R7",6)):
                    port.command(register+"= 0")
                    port.open("/VMHIL/"+name);port.pump(.6)
                    require_foreground(port)
                    if port.frames:png(port.frames[-1],args.output_dir/(name+".png"))
                    port.close_app()
                    values,report=registers(port);assert values[register]==value,(name,values,report)
                    print("USB "+name+": PASS",flush=True)
                port.open("/VMHIL/input.tbi");port.pump(.5)
                require_foreground(port)
                for keys in (number15,number15):
                    for key in keys:port.key(key)
                port.pump(.5);port.close_app()
                values,report=registers(port);assert values["R5"]==30,(values,report)
                result["checks"].append("USB-language-input")
                if args.extended:
                    port.command("R8= 0")
                    port.open("/VMHIL/large.tbi");port.pump(.8)
                    require_foreground(port)
                    # Host-initiated DETACH has no acknowledgement in v2.
                    # Fresh CAPS below proves the session reached WAITING:
                    # an ATTACH sent to an already ATTACHED session is ignored.
                    port.send(0x13);port.attached=False;port.pump(.3)
                    port.attach_waiting();port.pump(.2)
                    for key in number15:port.key(key)
                    port.pump(.5);port.close_app()
                    values,report=registers(port);assert values["R8"]==15,(values,report)
                    result["checks"].append("USB-large-image-detach-reattach-INPUT")
                    print("USB large image + reattach during INPUT: PASS",flush=True)
                    port.command("R9= 0")
                    port.open("/VMHIL/input.foc");port.pump(.5)
                    require_foreground(port)
                    for _ in range(2):
                        for key in number15:port.key(key)
                    port.pump(.5);port.close_app()
                    values,report=registers(port);assert values["R9"]==30,(values,report)
                    result["checks"].append("USB-FOCAL-INPUT-FOR")
                    print("USB FOCAL FOR/INPUT: PASS",flush=True)
                    for name,wide in (("numeric.tbi",65535),("numeric.foc",524287)):
                        port.open("/VMHIL/"+name);port.pump(.7)
                        require_foreground(port);port.close_app()
                        values,report=registers(port)
                        assert (values["RA"],values["RB"],values["RC"],values["RD"]) == (0,wide,-4,3),(name,report)
                        result["checks"].append("USB-"+name+"-overflow-wide-floor-FOR")
                        print("USB "+name+": overflow, wide arithmetic, floor and FOR PASS",flush=True)
                    port.open("/VMHIL/large.tbi");port.pump(.8)
                    require_foreground(port)
                    if port.frames:png(port.frames[-1],args.output_dir/"large-input-before-cancel.png")
                    port.key(39);port.pump(.3) # Cancel the editor's INPUT.
                    port.close_app() # Dismiss the ordinary final-result wait.
                    values,report=registers(port);assert values["R8"]==15,(values,report)
                    result["checks"].append("USB-large-image-INPUT-cancel")
                    print("USB large image INPUT cancellation: PASS",flush=True)
                result["USB_frames_crc_checked"]=len(port.frames)
                assert port.frames,"no complete CRC-checked USB frame"
            result["after"]=health(port);result["status"]="PASS"
        except BaseException as error:
            result["status"]="FAIL";result["error"]=str(error)
            try:
                if args.screen and port.caps is not None and not port.attached:
                    port.attach_waiting()
                if port.attached:
                    port.key(39);port.key(39)
                result["after_failure"]=health(port)
            except (AssertionError,OSError,TimeoutError) as diagnostic:
                result["diagnostic_error"]=str(diagnostic)
            raise
        finally:
            if port.attached:
                # Restore the physical display, retaining the documented
                # WAITING session. serviceEscapeHold checks physical keys;
                # a virtual ESC hold cannot free the session's OVERLAY lease.
                try:
                    port.send(0x13);port.attached=False;port.pump(.2)
                except (AssertionError,OSError,TimeoutError) as cleanup:
                    result["cleanup_error"]=str(cleanup)
                    if result["status"]=="PASS":
                        result["status"]="FAIL";result["error"]="USB cleanup failed: "+str(cleanup)
            (args.output_dir/"result.json").write_text(json.dumps(result,indent=2)+"\n")
            (args.output_dir/"terminal.txt").write_bytes(port.text)
            if port.frames:png(port.frames[-1],args.output_dir/"last-frame.png")
    assert result["status"]=="PASS",result
    print("Language HIL PASS",flush=True)

if __name__=="__main__":run()
