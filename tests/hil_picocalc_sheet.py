#!/usr/bin/env python3
"""Qualify native SHEET pixels and S1 editing on one exact Pico UID/build.

Installs only SHEET.APP with backup/rollback. Creates one absent temporary
document, removes it afterwards and restores calculator data/USB Screen.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,re,struct,sys,time,zlib
from pathlib import Path
from hil_c5_stack import read_file,write_file
from hil_picocalc_apps import AppsPort
from hil_picocalc_software import calculator,restore
from hil_picocalc_turochamp import healthy
from hil_picocalc_display import lcd_crc
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from generate_ui_fonts import load_atlases
from build_sheet_app import document
from m8_codec import decode

OK,ESC,USER,LEFT,RIGHT,UP,DOWN,CLEAR=29,39,19,34,24,32,33,0


class SheetFont:
    """Pixel oracle composed from reviewed Ark JSON, without running APP code."""
    def __init__(self):self.faces={12:load_atlases()[0][0],16:load_atlases()[0][2]}
    def glyph(self,char,size=16):return self.faces[size]['by_codepoint'][ord(char)]
    def width(self,text,size=16):return sum(self.glyph(c,size)['advance'] for c in text)
    @staticmethod
    def pixel(frame,x,y,ink=True):
        assert 0<=x<320 and 0<=y<320
        mask=1<<(y%8);at=y//8*320+x
        if ink:frame[at]|=mask
        else:frame[at]&=~mask
    def box(self,frame,x,y,w,h):
        for row in range(y,y+h):
            for col in range(x,x+w):self.pixel(frame,col,row)
    def text(self,frame,text,x,y,size=16,inverse=False,right=316):
        for char in text:
            g=self.glyph(char,size)
            if x+g['advance']>right:break
            for dy,row in enumerate(g['rows']):
                for dx,bit in enumerate(row):
                    if bit=='1':
                        px=x+g['safe_bearing_x']+dx
                        if x<=px<right:self.pixel(frame,px,y+(10 if size==12 else 14)-g['bearing_y']+dy,not inverse)
            x+=g['advance']
    def fit(self,text,maximum,size=16):
        if self.width(text,size)<=maximum:return text
        fitted=''
        for char in text:
            if self.width(fitted+char+'>',size)>maximum:break
            fitted+=char
        return fitted+'>'
    def has(self,frame,text,x,y,size=16,inverse=False):
        expected=bytearray(12800);width=self.width(text,size)
        if inverse:self.box(expected,x,y,width,size+3)
        self.text(expected,text,x,y,size,inverse)
        return all(bool(frame[row//8*320+col]&(1<<(row%8)))==bool(expected[row//8*320+col]&(1<<(row%8)))
                   for row in range(y,y+size+3) for col in range(x,x+width))
    def table(self,cells,selected='A1',compact=False,modified=False,top=0,left=0):
        f=bytearray(12800);status='DEG'+(' *' if modified else '')
        self.box(f,0,0,320,28);sx=312-self.width(status)
        self.text(f,'SHEET / '+selected,8,6,inverse=True,right=sx-4);self.text(f,status,sx,6,inverse=True)
        cell=cells.get(selected)
        if cell:
            kind,source,value=cell
            if kind==3:
                caption=source.replace('ENT','В↑').replace('*','×')
                self.text(f,'=',8,34);self.text(f,self.fit(caption,288),24,34)
            else:self.text(f,self.fit(value,304),8,34)
        cols,rows,pitch,size=(4,11,18,12) if compact else (3,8,24,16);cw=288//cols
        self.box(f,0,56,320,pitch)
        for col in range(cols):
            label=chr(65+left+col)
            self.text(f,label,32+col*cw+(cw-self.width(label,size))//2,56+(pitch-size)//2,size,True)
        for row in range(rows):
            number=top+row+1;y=56+(row+1)*pitch;ty=y+(pitch-size)//2
            self.text(f,str(number),28-self.width(str(number),size),ty,size)
            for col in range(cols):
                x=32+col*cw;address=chr(65+left+col)+str(number);active=address==selected
                if active:self.box(f,x+1,y+1,cw-2,pitch-2)
                if address in cells:
                    kind,source,value=cells[address];value=self.fit(value,cw-8,size)
                    self.text(f,value,x+4 if kind==2 else x+cw-4-self.width(value,size),ty,size,active,x+cw-4)
                self.box(f,x,y+pitch-1,cw,1)
        for col in range(cols+1):self.box(f,31+col*cw,56,1,(rows+1)*pitch)
        self.box(f,0,282,320,1)
        self.text(f,'OK:ПРАВКА  USER:МЕНЮ',8,286);self.text(f,'←→:СТОЛБЕЦ  ↑↓:СТРОКА',8,304)
        return bytes(f)
    def editor(self,frame,text,cursor):
        expected=bytearray(12800);positions=[];x=8;row=0
        for char in text+' ':
            step=self.width(char)
            if x+step>312:x=8;row+=1
            positions.append((x,row,step));x+=step
        for char,(x,row,_) in zip(text,positions):self.text(expected,char,x,44+24*row)
        x,row,step=positions[cursor]
        for col in range(x,x+step):self.pixel(expected,col,44+24*row+18)
        return all(bool(frame[y//8*320+col]&(1<<(y%8)))==bool(expected[y//8*320+col]&(1<<(y%8)))
                   for y in range(40,200) for col in range(8,312))


def cells_in(data):
    assert data[:5]==b'MKSH\1' and zlib.crc32(data[:16]+data[20:])==struct.unpack_from('<I',data,16)[0]
    result={};at=20
    for _ in range(data[9]):
        position,kind,size=struct.unpack_from('<HBB',data,at);at+=4
        result[chr(65+position%16)+str(position//16+1)]=(kind,decode(data[at:at+size]));at+=size
    assert at==len(data);return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid','build-id'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--app',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--directory',default='/MK61S-PicoCalc-0.8');ap.add_argument('--install',action='store_true',required=True)
    args=ap.parse_args();assert re.fullmatch(r'[0-9A-Fa-f]{16}',args.uid) and re.fullmatch(r'[0-9A-Fa-f]{8}',args.build_id)
    assert re.fullmatch(r'/[A-Za-z0-9.-]+',args.directory)
    args.output.mkdir(parents=True,exist_ok=False);app_path=args.directory+'/SHEET.APP';path=args.directory+'/SHEET320.mks'
    font=SheetFont();data=args.app.read_bytes();old=None;created=False
    cells={'A1':(2,'БЮДЖЕТ','БЮДЖЕТ'),'B1':(1,'2','2'),'C1':(3,'B1 ENT 125 *','250'),
           'A2':(2,'Ж'*95,'Ж'*95),'B2':(3,'B2','#ЦИКЛ'),'A8':(2,'ВОСЕМЬ','ВОСЕМЬ'),
           'D11':(2,'ОБЗОР','ОБЗОР'),'P32':(1,'314159','314159')}
    fixture=bytes(document([(a,k,s) for a,(k,s,v) in cells.items()]))
    result=dict(passed=False,uid=args.uid.upper(),build=args.build_id.upper(),directory=args.directory,
                app_sha256=hashlib.sha256(data).hexdigest(),recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                cases=[],screens={},firmware_writes=0)
    with AppsPort(args.port,keyboard_layout=0) as p:
        p.native_display=True;p.commands();assert 'UID='+args.uid.upper() in p.command('identity')
        calculator(p);initial=p.status();healthy(initial,args.build_id.upper());p.expect('SERVICE=CLOSED','DIRTY=0','RUN=0 BUSY=0')
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        (args.output/'before.json').write_text(json.dumps(before,indent=2)+'\n')
        def keys(sequence):
            for key in sequence:p.key(key)
        def shot(name,predicate):
            p.pump(.2);first=len(p.frames);p.send(0x16);deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                p.pump(.04)
                if len(p.frames)>first and predicate(p.frames[-1]):break
            else:
                if p.frames:png(p.frames[-1],args.output/'failure.png')
                raise AssertionError('Missing native SHEET frame: '+name)
            frame=p.frames[-1];png(frame,args.output/(name+'.png'));(args.output/(name+'.bin')).write_bytes(frame)
            result['screens'][name]=hashlib.sha256(frame).hexdigest();return frame
        def grid(name,**options):
            expected=font.table(cells,**options);frame=shot(name,lambda f:f==expected)
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                status=p.status()
                if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+lcd_crc(frame) in status:break
            else:raise AssertionError('LCD source snapshot differs from SHEET frame')
        def passed(name):result['cases'].append(name);print('PASS '+name,flush=True)
        def ended(start):
            p.wait_text(b'APP_FLOW_RESULT=0',start,timeout=20);calculator(p);healthy(p.status(),args.build_id.upper())
        def leave():
            for _ in range(10):
                if 'RUNTIME=NONE ' in p.status():calculator(p);return
                if p.frames and font.has(p.frames[-1],'ЛИСТ ИЗМЕНЁН',8,6,inverse=True):keys([RIGHT,OK])
                else:keys([ESC])
                p.pump(.2)
            raise AssertionError('SHEET did not leave the foreground')
        try:
            listing=p.command('ls '+args.directory)
            assert not any(line.split('\t')[-1].casefold()=='sheet320.mks' for line in listing.splitlines()),listing
            old=read_file(p,app_path);(args.output/'previous-SHEET.APP').write_bytes(old)
            write_file(p,app_path,data);created=True;write_file(p,path,fixture)
            p.command('uscreen on');p.attach_waiting();start=len(p.text);p.open(path);p.expect('RUNTIME=APP')
            grid('table-native');keys([RIGHT,RIGHT]);grid('formula-selected',selected='C1')
            formula='B1 В↑ 125 ×'
            keys([OK]);shot('formula-editor',lambda f:font.editor(f,formula,len(formula)-1) and font.has(f,'250',40,214))
            keys([USER,LEFT,USER]);shot('reference',lambda f:font.has(f,'ССЫЛКА: $B1',8,6,inverse=True))
            keys([ESC,ESC,LEFT,LEFT,DOWN,OK]);shot('long-label',lambda f:font.editor(f,'Ж'*95,95))
            keys([LEFT,CLEAR]);shot('long-label-edited',lambda f:font.editor(f,'Ж'*94,93))
            keys([OK]);cells['A2']=(2,'Ж'*94,'Ж'*94);grid('label-committed',selected='A2',modified=True)
            passed('native 3x8 pixels, Russian/long labels, formula preview, anchored reference and cursor/delete')
            keys([USER]);shot('actions',lambda f:font.has(f,'ДЕЙСТВИЯ',8,6,inverse=True))
            keys([RIGHT]*6+[OK]);shot('sheet-menu',lambda f:font.has(f,'СПРАВКА',32,246))
            keys([RIGHT]*4+[OK]);grid('table-overview',selected='A2',compact=True,modified=True)
            keys([RIGHT]*15+[DOWN]*30);grid('corner-overview',selected='P32',compact=True,modified=True,top=21,left=12)
            keys([USER]+[RIGHT]*6+[OK]+[RIGHT]*4+[OK]);grid('corner-normal',selected='P32',modified=True,top=24,left=13)
            passed('native 4x11 overview, P32 scrolling and density change clamp without cells beyond the sheet')
            keys([USER]+[RIGHT]*5+[OK]);shot('details',lambda f:font.has(f,'314159',8,66));keys([ESC])
            keys([USER]+[RIGHT]*6+[OK]+[RIGHT]*7+[OK]);shot('help-1',lambda f:font.has(f,'SHEET / СПРАВКА',8,6,inverse=True))
            keys([OK]);shot('help-2',lambda f:font.has(f,'F USER:СПИСОК ОПЕРАЦИЙ',8,132));keys([ESC,ESC])
            shot('save-confirmation',lambda f:font.has(f,'ЛИСТ ИЗМЕНЁН',8,6,inverse=True));keys([OK]);ended(start)
            saved=read_file(p,path);(args.output/'edited.mks').write_bytes(saved)
            assert cells_in(saved)=={a:(k,s) for a,(k,s,v) in cells.items()};assert saved[8]==0
            start=len(p.text);p.open(path);p.expect('RUNTIME=APP');grid('reopened');keys([ESC]);ended(start)
            passed('eight visible sheet menu items, details/help, valid S1 save and reopen with values/sources preserved')
            # Existing bundled documents exercise the normal Explorer/S1 route,
            # without saving or replacing either document.
            values={'A2':'2','B2':'125','C2':'250','D2':'50','A3':'3','B3':'80','C3':'240','D3':'48',
                    'A4':'1','B4':'350','C4':'350','D4':'70','C5':'840','D5':'168'}
            for name in ('BUDGET','CYCLE'):
                sample_path=args.directory+'/'+name+'.mks';sample=read_file(p,sample_path)
                assert sample==(ROOT/'programs/sheets'/(name+'.mks')).read_bytes()
                parsed=cells_in(sample)
                view={a:(k,s,s if k==2 else (values[a] if name=='BUDGET' else '#ЦИКЛ' if k==3 else '42'))
                      for a,(k,s) in parsed.items()}
                expected=font.table(view);start=len(p.text);p.open(sample_path);p.expect('RUNTIME=APP')
                shot(name.lower(),lambda f:f==expected);keys([ESC]);ended(start)
                assert read_file(p,sample_path)==sample
            passed('existing BUDGET/CYCLE documents: exact native pixels, calculated values/errors and unchanged S1 files')
            assert read_file(p,app_path)==data;result['passed']=True
        finally:
            try:
                leave()
                p.command('fsput cancel')
                if created:
                    listing=p.command('ls '+args.directory)
                    if any(line.split('\t')[-1].casefold()=='sheet320.mks' for line in listing.splitlines()):
                        assert 'ERROR' not in p.command('rm "'+path+'"')
                    result['temporary_sheet_removed']=True
                if not result['passed'] and old is not None:write_file(p,app_path,old);result['original_app_restored']=True
                p.command('cd "'+re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]+'"');restore(p,before)
                assert re.findall(r'(?m)^\d{4} [0-9A-F]{2}\r?$',before['dump'])==re.findall(r'(?m)^\d{4} [0-9A-F]{2}\r?$',p.command('dump'))
                result['calculator_state_restored']=True
                if p.attached:p.send(0x13);p.attached=False;p.pump(.2)
                p.command('uscreen off' if 'USB_SCREEN=OFF ' in initial else 'uscreen on')
                result['final']=p.status();healthy(result['final'],args.build_id.upper())
                for label in ('UI_FONT_FAMILY','UI_FONT_SIZE','UI_FONT_KEY'):
                    assert re.search(label+r'=\w+',initial)[0]==re.search(label+r'=\w+',result['final'])[0]
            except BaseException as error:result.update(passed=False,cleanup_error=repr(error))
            result['frames_crc_verified']=len(p.frames)
            (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            (args.output/'terminal.bin').write_bytes(p.text)
    assert result['passed'],result
    print('SHEET PicoCalc PASS',flush=True)


if __name__=='__main__':main()
