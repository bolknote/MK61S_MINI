"""Strict pure HOST parser for complete and first-fault streamed reports."""
import hashlib,struct,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'tests'),str(ROOT)]
from prepare import request,pin,FUNCTIONS,NONCE,ROWS
from check_stm32_vectors import ElfImage
from tools.apps.packer.app_relocations import extract
HEADER_BYTES=1024;PAGE_BYTES=4096;PAGE_ROWS=14;PAGES=15;REPORT_BYTES=62464
def need(v,reason):
    if not v:raise ValueError(reason)
def parse_request(raw,t):
    need(len(raw)>=64,'truncated request')
    w=struct.unpack_from('<16I',raw)
    batch=None if w[2]==0xffffffff else w[2]
    need(raw==request(t,w[3],batch,list(w[8:14])),'request differs from frozen complete matrix/nonce/CRC/context')
    if batch is not None:need(any(w[8:14]),'timing lacks qualified context')
    return dict(route=w[3],batch=batch,first=w[4],count=w[5],context=list(w[8:14]))
def checked_crc(raw,offset):
    w=bytearray(raw);wanted=struct.unpack_from('<I',w,offset)[0];struct.pack_into('<I',w,offset,0)
    return wanted==zlib.crc32(w)
def parse_report(raw,input_raw,t,app,decoded,allow_fault=False):
    q=parse_request(input_raw,t);need(len(raw)==REPORT_BYTES,'raw streamed report length')
    h=list(struct.unpack_from('<256I',raw))
    need(checked_crc(raw[:1024],1020),'header CRC')
    need(h[:2]==[0x38484c4d,1] and h[9:11]==[7,9] and h[254]==REPORT_BYTES,'report format')
    need(h[4:8]==[0xffffffff if q['batch'] is None else q['batch'],q['route'],q['first'],q['count']],'request correlation')
    need(h[11:13]==[NONCE&0xffffffff,NONCE>>32],'run nonce')
    need(h[20:22]==[int(app['shared_runtime']),int(app['code_Flash'])],'wrong APP route')
    need(q['route']==app['route_index'],'wrong route input')
    need(0<=h[8]<=q['count'] and 0<=h[47]<=PAGES,'raw group counts')
    fault=h[2]!=0
    if fault:need(allow_fault and (1<=h[2]<=8 or h[2]==0xffffffff),'first fault/incomplete stream')
    else:
        need(h[3]==0 and h[8]==q['count'] and h[47]==(q['count']+13)//14,'incomplete group coverage')
        need(h[13]==h[23]==t['fixture_crc32'] and h[14]==zlib.crc32(struct.pack('<26I',*t['runtime_words'])),'fixture/runtime anchors')
        need(h[19]==zlib.crc32(bytes.fromhex(t['footer_hex'])) and h[214:216]==[t['footer_address'],t['runtime_address']],'footer/runtime addresses')
        need(h[24]&0xff00fff0==0x4100c600 and h[25:28]==[0,0,0],'Cortex-M0+/thread/IRQ/privilege')
        need(h[24:30]==h[30:36] and (q['batch'] is None or h[24:30]==q['context']),'context changed or mixed')
        need(h[36]&3==2 and h[37:40]==[0x100,4,0x60c],'reference/tick source')
        need(h[18]==1000000 and 8<=h[16]<=250 and 0<h[17]<0x80000000 and abs(h[17]-1000*h[16])<=2000,'timer not qualified')
    need(pin(app['APP']['path'])==app['APP'] and pin(app['ELF']['path'])==app['ELF'],'APP/ELF changed')
    e=ElfImage(Path(app['ELF']['path']));delta=h[212]-e.symbols['header'];base=app['report']['load_address']+delta
    need(base%8==0 and 0x20000000<=base and base+len(decoded)<=0x20042000 and len(decoded)==app['report']['memory_bytes'],'actual packed load bounds')
    need(h[22]==struct.unpack_from('<I',Path(app['APP']['path']).read_bytes(),52)[0],'packed image CRC')
    normalized=bytearray(decoded)
    fixups,_=extract(Path(app['ELF']['path']),app['report']['load_address'],app['report']['image_bytes'],app['report']['memory_bytes'])
    for offset in fixups:
        value=struct.unpack_from('<I',normalized,offset)[0]
        struct.pack_into('<I',normalized,offset,(value-delta)&0xffffffff)
    for i,name in enumerate(['source_a','source_b','destination','arena','header','page']):
        wanted=e.symbols[name]+delta
        if name=='arena':wanted=(wanted+15)&~15
        need(h[208+i]==wanted,'actual SRAM buffer/arena address')
    if not fault:
        for op,name in enumerate(FUNCTIONS):
            mask=0x1ff if name in t['runtime_slots'] else 0xff;need(h[48+op]==mask,'runtime N/A mask')
            used=0
            for f,leaf in enumerate(t['leaves'][op]):
                used=(used+15)&~15
                wanted=(t['fixture_base']+leaf['offset'] if app['code_Flash'] else h[211]+used)|1
                need(h[64+op*9+f]==wanted and h[144+op*6+f]==leaf['crc32'],'candidate actual entry/body')
                used+=leaf['bytes']
            public=(e.symbols[name]&~1)+delta
            need(h[64+op*9+6]==public|1 and h[64+op*9+7]==t['native'][op]['entry'],'public SDK/native entry')
            at=public-base;size=app['publics'][name]['bytes']
            need(hashlib.sha256(normalized[at:at+size]).hexdigest()==app['publics'][name]['sha256'],'decoded public body/declared relocation changed')
            want_runtime=t['runtime_words'][t['runtime_slots'][name]] if name in t['runtime_slots'] else 0
            need(h[64+op*9+8]==want_runtime and h[200+op]==t['native'][op]['crc32'],'native or real runtime slot drift')
    rows=[]
    for pn in range(PAGES):
        block=raw[HEADER_BYTES+pn*PAGE_BYTES:HEADER_BYTES+(pn+1)*PAGE_BYTES]
        if pn>=h[47]:need(block==b'\xa5'*PAGE_BYTES,'unwritten sentinel page changed');continue
        ph=list(struct.unpack_from('<16I',block));need(checked_crc(block,60),'page CRC')
        need(ph[:6]==[0x3850474d,1,h[4],h[5],pn,q['first']+pn*14] and ph[9:11]==h[11:13],'page/job/nonce correlation')
        n=min(14,q['count']-pn*14)
        need(0<ph[6]<=n and (fault or ph[6]==n),'page count')
        need(ph[11:15]==[0]*4 and block[3760:]==bytes(336),'reserved page padding')
        if not fault:need(ph[7:9]==[0,0],'fault in completed page')
        for slot in range(14):
            row=block[64+slot*264:64+(slot+1)*264]
            if slot>=ph[6]:need(row==bytes(264),'unused row nonzero');continue
            index,repeats,address,*values=struct.unpack('<66I',row)
            if fault and len(rows)>=h[8]:continue
            need(index==q['first']+pn*14+slot,'row reordered/replayed/omitted')
            case=t['cases'][index];op=FUNCTIONS.index(case['function'])
            want=t['fixture_base']+case['left']['offset'] if case['banks'][0]=='F' else h[208]+32+case['alignment'][0]
            need(repeats==case['repeats'] and address==want and address%4==case['alignment'][0],'case address/alignment/repeats')
            mask=0x1ff if case['function'] in t['runtime_slots'] else 0xff
            for f in range(9):need(all(0<v<0x80000000 for v in values[f*7:f*7+7]) if mask&(1<<f) else values[f*7:f*7+7]==[0]*7,'raw positive interval or explicit runtime N/A')
            rows.append(dict(index=index,function=case['function'],repeats=repeats,address=address,raw=[values[f*7:f*7+7] for f in range(9)]))
    need(len(rows)==h[8],'completed row count mismatch')
    return dict(status='FIRST_FAULT_OR_INCOMPLETE' if fault else 'PASS_RAW_ALL_GROUPS',header=h,request=q,rows=rows,actual_APP_base=base,timer_unit='microseconds',physical_time_claim=False)
