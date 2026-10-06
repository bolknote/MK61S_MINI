#!/usr/bin/env python3
"""Play the installed, unmodified High Noon via its M61 driver and USB Screen.

Only game inputs/test registers change. No firmware/FS writes or RNG seeding.
Screens are recognized from the game's actual FMK pixels, not terminal prompts:
M61 is asynchronous and a CDC prompt may appear while a child is still running.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from hil_c6_system_bootstrap import read_file
from hil_language_vm import health
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png,registers
from hil_usb_disk_transaction import listing_entries

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from m8_codec import encode

DIGITS=(4,9,8,7,14,13,12,19,18,17)
OK,ESC=37,39


def folder_index(report,name):
    entries=listing_entries(report)
    matches=[i for i,entry in enumerate(entries)
             if entry.casefold()==("d\t"+name+"/").casefold()]
    assert len(matches)==1,(name,entries)
    return matches[0]


class GameFont:
    """Independent FMK2 raw-glyph oracle for the 47-column, ten-row game face."""
    def __init__(self,data):
        assert data[:4]==b"FMK2" and data[5:8]==bytes((5,5,0x31))
        bit=(16+data[10]*2)*8
        def read(n):
            nonlocal bit
            value=0
            for _ in range(n):
                value=(value<<1)|((data[bit//8]>>(7-bit%8))&1);bit+=1
            return value
        self.glyphs={};self.cache={}
        for start,count in zip(data[16:16+data[10]*2:2],data[17:17+data[10]*2:2]):
            for code in range(start,start+count+1):
                width,advance=read(4)+1,read(4)+1
                assert read(1)==0 and advance==width+1
                rows=tuple(read(width) for _ in range(5))
                self.glyphs[code]=(width,advance,rows)

    @staticmethod
    def pixel(frame,x,y):return (frame[y//8*192+x]>>(y%8))&1

    def pattern(self,text):
        if text not in self.cache:
            rows=[[] for _ in range(5)]
            for code in encode(text):
                width,advance,bits=self.glyphs[code]
                for y in range(5):
                    rows[y].extend((bits[y]>>(width-1-x))&1 for x in range(width))
                    rows[y].extend([0]*(advance-width))
            self.cache[text]=tuple(tuple(row) for row in rows)
        return self.cache[text]

    def matches(self,frame,text,row,x=2):
        pattern=self.pattern(text)
        if not pattern[0] or x+len(pattern[0])>190:return False
        return all(self.pixel(frame,x+dx,2+row*6+y)==value
                   for y,line in enumerate(pattern) for dx,value in enumerate(line))

    def has(self,frame,text):return any(self.matches(frame,text,row) for row in range(10))
    def contains(self,frame,text):
        width=len(self.pattern(text)[0])
        return any(self.matches(frame,text,row,x) for row in range(10) for x in range(2,191-width))
    def number_after(self,frame,prefix):
        for row in range(10):
            if not self.matches(frame,prefix,row):continue
            x=2+len(self.pattern(prefix)[0]);digits=""
            for _ in range(4):
                found=next((str(n) for n in range(10) if self.matches(frame,str(n),row,x)),None)
                if found is None:break
                digits+=found;x+=len(self.pattern(found)[0])
            if digits:return int(digits)
        return None


class Game:
    def __init__(self,port,font,directory,output,result):
        self.port,self.font,self.directory,self.output,self.result=port,font,directory,output,result
        self.index=0
    def wait(self,*labels,timeout=8):
        self.port.pump(.5);self.port.send(0x16)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.port.pump(.05)
            if b"Open failed!" in self.port.text[self.port.open_text_start:]:
                raise AssertionError("High Noon open failed")
            if self.port.frames:
                frame=self.port.frames[-1]
                for label in labels:
                    if self.font.has(frame,label):return label
        raise TimeoutError("expected High Noon screen: "+repr(labels))
    def save(self,name):
        frame=self.port.frames[-1];self.index+=1
        filename=f"{self.index:03d}-{name}"
        png(frame,self.output/(filename+".png"))
        (self.output/(filename+".bin")).write_bytes(frame)
        self.result["screens"].append({"name":name,"file":filename+".png",
            "sha256":hashlib.sha256(frame).hexdigest(),"frames":len(self.port.frames)})
    def number(self,value):
        for c in str(value):self.port.key(DIGITS[int(c)])
        self.port.key(OK)
    def key(self):self.port.key(OK)
    def start(self):
        self.port.open(self.directory+"/autoexec.m61")
        self.wait("ПОКАЗАТЬ ИНСТРУКЦИЮ?");self.save("intro")
        self.number(0);self.wait("ВАША СТРАТЕГИЯ?")
    def start_from_explorer(self):
        assert self.directory.startswith("/")
        components=self.directory.strip("/").split("/")
        assert all(component and component not in (".","..") for component in components)
        indices=[];parent="/"
        for component in components:
            indices.append(folder_index(self.port.command("ls "+parent),component))
            parent=parent.rstrip("/")+"/"+component
        self.port.open_text_start=len(self.port.text)
        self.port.key(ESC) # Calculator -> the pinned build's main menu.
        for _ in range(3):self.port.key(36) # DFU, USB disk, Setup, Explorer.
        self.port.key(OK);self.port.pump(.2)
        for index in indices:
            for _ in range(index):self.port.key(36)
            self.port.key(OK);self.port.pump(.3)
        self.wait("ПОКАЗАТЬ ИНСТРУКЦИЮ?");self.save("explorer-autoexec-intro")
        self.result["checks"].append("Explorer-folder-entry-autoexec-M61")
        print("Explorer folder entry -> High Noon autoexec PASS",flush=True)
    def stop(self):
        self.port.key(ESC);self.port.pump(.5)
        # A second ESC is safe if a nested interpreter's final key is pending.
        self.port.key(ESC);self.port.pump(.3)
    def final(self,expected_choice=None):
        self.port.pump(.5)
        values,report=registers(self.port)
        assert values["RE"]==99,(values,report)
        if expected_choice is not None:assert values["R1"]==expected_choice,(values,report)
        assert not self.font.has(self.port.frames[-1],"ВАША СТРАТЕГИЯ?")
        self.save("returned-to-calculator")
        self.result["register_reports"].append(report)

    def instructions_surrender(self,explorer_start=False):
        if explorer_start:self.start_from_explorer()
        else:self.port.open(self.directory+"/autoexec.m61")
        self.wait("ПОКАЗАТЬ ИНСТРУКЦИЮ?");self.number(1)
        self.wait("ЧЁРНЫЙ БАРТ ВЫЗВАЛ");self.save("instructions-1");self.key()
        self.wait("У КАЖДОГО ПО ЧЕТЫРЕ");self.save("instructions-2");self.key()
        self.wait("ПРОДОЛЖИТЬ?");self.save("instructions-confirm");self.number(1)
        self.wait("ВАШИ ВОЗМОЖНЫЕ ХОДЫ:");self.save("moves-menu");self.key()
        self.wait("ВАША СТРАТЕГИЯ?");self.number(7)
        self.wait("С ТАКИМ ЗНАНИЕМ ПРАВИЛ");self.save("invalid-strategy");self.key()
        self.wait("ВАША СТРАТЕГИЯ?");self.number(1)
        self.wait("СКОЛЬКО ШАГОВ ПРОЙТИ:");self.number(11)
        self.wait("ТАК БЫСТРО НЕ ХОДЯТ.");self.save("invalid-steps");self.key()
        self.wait("СКОЛЬКО ШАГОВ ПРОЙТИ:");self.number(10)
        self.wait("МЕЖДУ ВАМИ ");assert self.font.number_after(self.port.frames[-1],"МЕЖДУ ВАМИ ")==90
        self.save("player-step-90");self.key()
        self.wait("БАРТ ПРОШЁЛ ","БАРТ СТРЕЛЯЕТ");self.save("bart-first-turn");self.key()
        self.wait("ВАША СТРАТЕГИЯ?");self.save("next-player");self.number(5)
        self.wait("СОГЛАСНЫ?");self.number(1)
        self.wait("ОЧЕНЬ МУДРОЕ РЕШЕНИЕ.");self.save("surrender");self.key();self.final(5)
        self.result["checks"].append("instructions-invalid-input-player-bart-surrender-font-return")
        print("Instructions, invalid inputs, PLAYER/BART, surrender and return PASS",flush=True)

    def escape(self):
        self.start();self.number(6);self.wait("КАК ДАЛЕКО ВЫ УБЕЖАЛИ?");self.number(50)
        self.wait("ОН УДРАЛ ТАК БЫСТРО,");self.save("escape-50");self.key();self.final(6)
        self.result["checks"].append("escape-ending")
        self.start();self.stop();self.final()
        self.result["checks"].append("ESC-at-player-INPUT")
        print("Escape ending and ESC cancellation PASS",flush=True)

    def victory(self,attempts):
        for attempt in range(1,attempts+1):
            self.start();distance,shots,covers=100,0,0
            print(f"Natural RNG duel {attempt} starts",flush=True)
            for turn in range(1,25):
                self.wait("ВАША СТРАТЕГИЯ?")
                action=1 if distance>50 else 4 if covers<3 else 3
                self.number(action)
                if action==1:
                    self.wait("СКОЛЬКО ШАГОВ ПРОЙТИ:");self.number(10)
                    self.wait("МЕЖДУ ВАМИ ")
                    distance=self.font.number_after(self.port.frames[-1],"МЕЖДУ ВАМИ ")
                    assert distance is not None
                elif action==4:
                    covers+=1;self.wait("ВЫ СБИЛИ БАРТА С ТОЛКУ.")
                else:
                    shots+=1;self.wait("ВОТ ЭТО ВЫСТРЕЛ!","ПЛОХОЙ ВЫСТРЕЛ.",
                        "ПУЛЯ ЗАДЕЛА БАРТА","ВЫ РАНИЛИ ЕГО","БРАВО! ПАТРОНЫ КОНЧИЛИСЬ.")
                frame=self.port.frames[-1];self.save(f"duel-{attempt}-{turn}-player")
                won=self.font.has(frame,"ВОТ ЭТО ВЫСТРЕЛ!")
                self.key()
                if won:
                    self.wait("КАК МЭР ДОДЖ-СИТИ");self.save("reward-announcement");self.key()
                    self.wait("ЧЕК НОМЕР ");frame=self.port.frames[-1]
                    assert self.font.contains(frame,"$20,000"),"receipt amount absent/clipped"
                    assert sum(self.font.matches(frame,"*"*47,row) for row in range(10))==2,"receipt borders"
                    self.save("reward-receipt");self.key()
                    self.wait("НЕ ТРАТЬТЕ ВСЁ СРАЗУ.");self.save("reward-final");self.key();self.final(3)
                    self.result["checks"].append("natural-RNG-M61-victory-reward-receipt-font-return")
                    self.result["victory"]={"attempt":attempt,"turn":turn,"shots":shots}
                    print(f"Real M61 victory, reward, $20,000 receipt and return PASS (duel {attempt})",flush=True)
                    return
                self.wait("БАРТ ПРОШЁЛ ","БАРТ СТРЕЛЯЕТ","ВАШ ШАНС:","БАРТ УДРАЛ ИЗ ГОРОДА")
                frame=self.port.frames[-1];self.save(f"duel-{attempt}-{turn}-bart")
                moved=self.font.number_after(frame,"МЕЖДУ ВАМИ ")
                if moved is not None:distance=moved
                dead=self.font.has(frame,"ВЫ УМЕРЛИ,") or self.font.has(frame,"БАРТ УДРАЛ ИЗ ГОРОДА")
                self.key()
                print(f"Duel {attempt}, turn {turn}: action={action}, distance={distance}, shots={shots}, dead={dead}",flush=True)
                if dead:self.final();break
                if shots>=4:self.stop();self.final();break
            else:self.stop();self.final()
        raise AssertionError(f"No victory in {attempts} natural-RNG duels; reward not qualified")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("port","public-id","build-id"):ap.add_argument("--"+name,required=True)
    ap.add_argument("--directory",default="/games/High Noon")
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--attempts",type=int,default=12)
    ap.add_argument("--explorer-start",action="store_true",
                    help="start the first game by entering its folder in Explorer, not CDC open")
    args=ap.parse_args();assert 1<=args.attempts<=20
    args.output_dir.mkdir(parents=True,exist_ok=True)
    result={"status":"RUNNING","checks":[],"screens":[],"register_reports":[]}
    local=ROOT/"programs/games/High Noon";font=GameFont((local/"HighNoon.FMK").read_bytes())
    with ScreenPort(args.port) as port:
        identity=parse_identity(port.command("identity"))
        assert identity.public==args.public_id.upper() and identity.build==args.build_id.upper() and identity.profile=="classic-v3-uc1609",identity
        game=Game(port,font,args.directory,args.output_dir,result)
        try:
            for path in sorted(local.iterdir()):
                data=path.read_bytes() if path.suffix.lower()==".fmk" else encode(path.read_text())
                read_file(port,args.directory+"/"+path.name,data)
            result["checks"].append("all-seven-installed-files-byte-identical")
            result["before"]=health(port);port.attach();port.pump(.2);game.save("before-game")
            game.instructions_surrender(args.explorer_start);game.escape();game.victory(args.attempts)
            result["after"]=health(port);result["CRC_checked_frames"]=len(port.frames);result["status"]="PASS"
        except BaseException as error:
            result["status"]="FAIL";result["error"]=str(error)
            try:game.stop();result["after_failure"]=health(port)
            except (OSError,AssertionError,TimeoutError) as diagnostic:result["diagnostic_error"]=str(diagnostic)
            raise
        finally:
            if port.attached:
                # Host DETACH intentionally leaves a WAITING session. Only a
                # physical ESC hold can destroy it; virtual ESC cannot do so.
                try:port.send(0x13);port.attached=False;port.pump(.2)
                except (OSError,AssertionError,TimeoutError) as error:
                    result["cleanup_error"]=str(error)
                    if result["status"]=="PASS":result["status"]="FAIL"
            (args.output_dir/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
            (args.output_dir/"terminal.txt").write_bytes(port.text)
    assert result["status"]=="PASS",result
    print("High Noon hardware PASS",flush=True)


if __name__=="__main__":main()
