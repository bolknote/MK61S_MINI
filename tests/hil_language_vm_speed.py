#!/usr/bin/env python3
"""Pinned BASIC/FOCAL device timing through real compiler/VM/USB Screen.

Only a newly reserved /VMSPEED directory is written, then removed. Registers
and cwd are restored. No firmware installation, format or user-file changes.
Times end on a CRC-checked completion frame, before the final-key wait.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

from hil_c6_system_bootstrap import write_file, read_file
from hil_language_vm import health
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import registers, png
from hil_usb_disk_transaction import listing_entries

DIRECTORY = "/VMSPEED"


def cases(n):
    total = n*(n+1)//2
    return {
        "basic_integer": ("tbi", f"10 S=0;FOR I=1 TO {n};B=I MOD 128;C=INT(I/128);@(B)=B+C;S=S+@(B);NEXT I\n20 .RA=S;END\n", sum(i % 128+i//128 for i in range(1, n+1))),
        "basic_mixed": ("tbi", f"10 A=0;FOR I=1 TO {n};A=A+.1;NEXT I\n20 .RA=A;END\n", n*.1),
        "basic_branches": ("tbi", f"10 A=0\n20 A=A+1\n30 IF A<{n} GOTO 20\n40 .RA=A;END\n", n),
        "basic_subroutines": ("tbi", f"10 A=0;FOR I=1 TO {n};GOSUB 100;NEXT I;.RA=A;END\n100 A=A+I;RETURN\n", total),
        "basic_wide": ("tbi", f"10 A=281474976710655;FOR I=1 TO {n};B=INT(A/536870912);C=A MOD 65536;NEXT I\n20 .RA=B+C;END\n", 589822),
        "focal_integer": ("foc", f"1.10 S A=0\n1.20 F I=1,{n};S A=A+I\n1.30 S .RA=A\n1.40 E\n", total),
        "focal_mixed": ("foc", f"1.10 S A=0\n1.20 F I=1,{n};S A=A+.1\n1.30 S .RA=A\n1.40 E\n", n*.1),
        "focal_subroutines": ("foc", f"1.10 S A=0\n1.20 F I=1,{n};D 2\n1.30 S .RA=A\n1.40 E\n2.10 S A=A+I\n", total),
    }


def marker_pixels(frame):
    # Text-only band, excluding the disk overlay at x=176..191.
    return frame[:160]+frame[192:352]


def names(port, path):
    return {e.split("\t")[-1].rstrip("/").casefold() for e in listing_entries(port.command('ls "'+path+'"'))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True);ap.add_argument("--public-id", required=True)
    ap.add_argument("--build-id", required=True);ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--iterations", type=int, default=20000);ap.add_argument("--runs", type=int, default=3)
    args=ap.parse_args();assert 100<=args.iterations<=30000 and 2<=args.runs<=5
    args.output_dir.mkdir(parents=True,exist_ok=True)
    result={"status":"RUNNING","device":args.public_id,"build":args.build_id,
            "iterations":args.iterations,"cases":{},"files_removed":[]}
    written={};created=False;screen_started=False
    def identify(p):
        i=parse_identity(p.command("identity"))
        assert i.public==args.public_id.upper() and i.build==args.build_id.upper() and i.profile=="classic-v3-uc1609",i
    with ScreenPort(args.port) as port:
        identify(port);saved,raw=registers(port)
        (args.output_dir/"registers-before.txt").write_text(raw)
        cwd=port.command("pwd").splitlines()[1].strip()
        try:
            assert DIRECTORY[1:].casefold() not in names(port,"/"),"reserved directory exists; nothing overwritten"
            port.command("mkdir "+DIRECTORY);created=True;result["before"]=health(port)
            programs=cases(args.iterations);planned={}
            for name,(extension,source,_) in programs.items():
                source=(source.replace(';END',';PRINT "VM_DONE";END') if extension=="tbi" else
                        source.replace('1.40 E','1.35 P "VM_DONE"\n1.40 E'))
                planned[DIRECTORY+"/"+name+"."+extension]=source.encode("ascii")
            planned[DIRECTORY+"/marker.tbi"]=b'10 PRINT "VM_INIT";END\n'
            planned[DIRECTORY+"/marker.foc"]=b'1.10 P "VM_INIT"\n1.20 E\n'
            # Storage writes happen before USB Screen holds OVERLAY.
            for path,payload in planned.items():
                write_file(port,path,payload)
                written[path]=payload # Only acknowledged, committed targets.
                read_file(port,path,payload)
            port.attach();screen_started=True;markers={}
            for name,(extension,_,expected) in programs.items():
                if extension not in markers:
                    # Learn DONE from an untimed completed workload in the
                    # configured font; verify its numeric result as well.
                    port.open(DIRECTORY+"/"+name+"."+extension);port.pump(8)
                    assert port.frames,"no CRC-checked marker frame"
                    markers[extension]=marker_pixels(port.frames[-1]);assert any(markers[extension])
                    png(port.frames[-1],args.output_dir/(extension+"-marker.png"));port.close_app()
                    actual,_=registers(port)
                    assert abs(float(actual["RA"])-expected)<=max(1e-7,abs(expected)*1e-8)
                durations=[]
                for repeat in range(args.runs):
                    # Warm cache hits intentionally preserve the display.
                    # Put INIT there first, outside the measured interval, so
                    # a repeat cannot mistake the previous DONE for this one.
                    port.open(DIRECTORY+"/marker."+extension);port.pump(.4)
                    assert marker_pixels(port.frames[-1])!=markers[extension]
                    port.close_app()
                    port.command("RA= -999");port.command("prof start");port.pump(.05)
                    cursor=len(port.frames);changed=True;complete=False
                    started=time.monotonic();port.open(DIRECTORY+"/"+name+"."+extension)
                    while time.monotonic()-started<60:
                        port.pump(.02)
                        for frame in port.frames[cursor:]:
                            pixels=marker_pixels(frame)
                            if pixels!=markers[extension]:changed=True
                            elif changed:complete=True;break
                        cursor=len(port.frames)
                        if complete:break
                    assert complete,(name,"completion frame absent")
                    elapsed=time.monotonic()-started;port.close_app()
                    counters=port.command("prof stop");actual,report=registers(port)
                    assert abs(float(actual["RA"])-expected)<=max(1e-7,abs(expected)*1e-8),(name,report)
                    durations.append(elapsed)
                    (args.output_dir/f"{name}-{repeat}-prof.txt").write_text(counters)
                    print(f"{args.build_id} {name} run {repeat}: {elapsed:.6f}s PASS",flush=True)
                result["cases"][name]={"seconds":durations,"warm_median_seconds":statistics.median(durations[1:]),"value":float(actual["RA"])}
                (args.output_dir/"report.json").write_text(json.dumps(result,indent=2)+"\n")
            result["status"]="PASS"
        except BaseException as error:
            result["status"]="FAIL";result["error"]=repr(error)
            if port.attached:
                try:port.close_app()
                except (AssertionError,TimeoutError,OSError):pass
            raise
        finally:
            result["frames_crc_verified"]=len(port.frames)
            (args.output_dir/"terminal.txt").write_bytes(port.text)
            def cleanup(p):
                identify(p);p.command("prof stop")
                for register,value in saved.items():p.command(register+"= "+str(value))
                p.command('cd "'+cwd+'"')
                for path,payload in written.items():
                    read_file(p,path,payload)
                    assert "Removed 1 entry." in p.command('rm "'+path+'"')
                    result["files_removed"].append(path)
                if created:
                    assert not names(p,DIRECTORY)
                    p.command('rmdir "'+DIRECTORY+'"')
                    assert DIRECTORY[1:].casefold() not in names(p,"/")
                restored,_=registers(p);assert restored==saved
                result["registers_restored"]=True;result["after"]=health(p)
            if screen_started:
                port.send(0x13);port.attached=False;port.pump(.2)
                # WAITING still owns OVERLAY. Reset after leaving all APPs,
                # then resolve the same identity before storage cleanup.
                port.drain();port.write_line("rst now")
                try:port.pump(.5)
                except OSError:pass # USB disconnect is expected during reset.
                port.close();deadline=time.monotonic()+20
                while True:
                    try:
                        with ScreenPort(args.port) as check:identify(check)
                        break
                    except (OSError,TimeoutError):
                        if time.monotonic()>deadline:raise
                        time.sleep(.15)
                with ScreenPort(args.port) as fresh:cleanup(fresh)
            else:cleanup(port)
            (args.output_dir/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    assert result["status"]=="PASS",result


if __name__=="__main__":main()
