#include "disk.h"
#include <string.h>
uint16_t spectrum_crc16(uint16_t crc,uint8_t byte) {
    crc^=(uint16_t)byte<<8;
    for(unsigned i=0;i<8;++i) crc=(uint16_t)((crc<<1)^((crc&0x8000)?0x1021:0));
    return crc;
}
static bool ready(const spectrum_fdc* f) { return f->io.read && f->io.bytes && !(f->system&3); }
static unsigned side(const spectrum_fdc* f) { return (f->system&16)?0:1; }
static uint32_t sector_offset(const spectrum_fdc* f,unsigned sector) {
    return ((f->head*f->io.heads+side(f))*16U+sector-1)*256;
}
static void finish(spectrum_fdc* f,unsigned error) {
    f->status|=(uint8_t)error;f->busy=f->drq=false;f->irq=true;
}
void spectrum_fdc_reset(spectrum_fdc* f) {
    const spectrum_disk_io io=f->io;memset(f,0,sizeof(*f));f->io=io;
    f->sector=1;f->system=0x3C;f->direction=1;f->type1=true;
}
static void tick(spectrum_fdc* f,uint32_t time) {
    if(!f->busy) return;
    if(f->type1) { if((int32_t)(time-f->due)>=0) finish(f,0);return; }
    if(!f->drq && (int32_t)(time-f->drq_due)>=0) { f->drq=true;f->due=f->drq_due+112*4; }
    if(f->drq && (int32_t)(time-f->due)>=0) finish(f,4);
}
static bool read_sector(spectrum_fdc* f) {
    if(!ready(f) || f->head>=f->io.tracks || f->head!=f->track || side(f)>=f->io.heads || f->sector<1 || f->sector>16) return false;
    const uint32_t at=sector_offset(f,f->sector);
    if(at>=f->io.bytes) { memset(f->buffer,0,256);return true; }
    const unsigned n=f->io.bytes-at<256?f->io.bytes-at:256;
    memset(f->buffer,0,256);return f->io.read(f->io.context,at,f->buffer,n);
}
static bool write_sector(spectrum_fdc* f) {
    const uint32_t at=sector_offset(f,f->sector);
    return ready(f) && f->head<f->io.tracks && side(f)<f->io.heads && f->sector>=1 && f->sector<=16 &&
        !f->io.readonly && f->io.write && at<=f->io.bytes && 256<=f->io.bytes-at &&
        f->io.write(f->io.context,at,f->buffer,256);
}
static uint16_t id_crc(const spectrum_fdc* f,unsigned sector) {
    uint16_t crc=0xFFFF;const uint8_t bytes[]={0xA1,0xA1,0xA1,0xFE,f->head,(uint8_t)side(f),(uint8_t)sector,1};
    for(unsigned i=0;i<sizeof(bytes);++i) crc=spectrum_crc16(crc,bytes[i]);
    return crc;
}
static void command(spectrum_fdc* f,uint8_t value,uint32_t time) {
    if((value&0xF0)==0xD0) { f->busy=f->drq=false;f->irq=(value&15)!=0;f->type1=true;return; }
    if(f->busy) return;
    f->command=value;f->status=0;f->irq=f->drq=false;f->busy=true;f->cursor=0;
    f->type1=!(value&128);f->multiple=(value&16)!=0;f->writing=(value&0xE0)==0xA0 || (value&0xF0)==0xF0;
    if(f->type1) {
        const unsigned old=f->head;unsigned target=old;
        if((value&0xF0)==0) { target=0;f->track=0; }
        else if((value&0xF0)==0x10) { target=f->data;f->track=f->data;f->direction=target>=old?1:0; }
        else {
            if((value&0xE0)==0x40) f->direction=1;else if((value&0xE0)==0x60) f->direction=0;
            target=f->direction?old+1:old?old-1:0;
            if(value&16) f->track=(uint8_t)target;
        }
        if(target>255) target=255;
        f->head=(uint8_t)target;
        static const unsigned rate[]={21000,42000,70000,105000};
        const unsigned steps=old>target?old-target:target-old;
        f->due=time+rate[value&3]*(steps?steps:1);
        if((value&4) && (!ready(f) || target>=f->io.tracks || f->track!=f->head)) f->status|=16;
        return;
    }
    if(!ready(f)) { finish(f,128);return; }
    if(f->writing && (f->io.readonly || !f->io.write)) { finish(f,64);return; }
    if((value&0xE0)==0x80 || (value&0xE0)==0xA0) {
        if(!read_sector(f) || ((value&2) && side(f)!=((value>>3)&1))) { finish(f,16);return; }
        f->length=256;
    } else if((value&0xF0)==0xC0) {
        const unsigned sector=f->sector>=1 && f->sector<=16?f->sector:1;const uint16_t crc=id_crc(f,sector);
        const uint8_t id[]={f->head,(uint8_t)side(f),(uint8_t)sector,1,(uint8_t)(crc>>8),(uint8_t)crc};
        memcpy(f->id,id,6);f->length=6;
    } else if((value&0xF0)==0xE0 || (value&0xF0)==0xF0) {
        f->length=6250;f->format_state=0;f->format_cursor=f->format_bytes=0;
    } else { finish(f,16);return; }
    f->drq_due=time+((value&4)?52500:700);
}
static uint8_t track_byte(spectrum_fdc* f,unsigned cursor) {
    // IBM System-34 MFM stream, generated with a single sector buffer.
    if(cursor<146) return cursor<80?0x4E:cursor<92?0:cursor<95?0xC2:cursor==95?0xFC:0x4E;
    const unsigned pos=(cursor-146)%372,sector=(cursor-146)/372+1;
    if(sector>16) return 0x4E;
    if(pos<12) return 0;
    if(pos<15) return 0xA1;
    if(pos==15) return 0xFE;
    if(pos==16) return f->head;
    if(pos==17) return (uint8_t)side(f);
    if(pos==18) return (uint8_t)sector;
    if(pos==19) return 1;
    if(pos<22) { const uint16_t crc=id_crc(f,sector);return pos==20?(uint8_t)(crc>>8):(uint8_t)crc; }
    if(pos<44) return 0x4E;
    if(pos<56) return 0;
    if(pos<59) return 0xA1;
    if(pos==59) {
        const uint8_t saved=f->sector;f->sector=(uint8_t)sector;const bool ok=read_sector(f);f->sector=saved;
        if(!ok) { finish(f,16);return 0; }
        f->format_crc=0xFFFF;
        for(unsigned i=0;i<3;++i) f->format_crc=spectrum_crc16(f->format_crc,0xA1);
        f->format_crc=spectrum_crc16(f->format_crc,0xFB);return 0xFB;
    }
    if(pos<316) { const uint8_t value=f->buffer[pos-60];f->format_crc=spectrum_crc16(f->format_crc,value);return value; }
    if(pos==316) return (uint8_t)(f->format_crc>>8);
    if(pos==317) return (uint8_t)f->format_crc;
    return 0x4E;
}
static void formatted_byte(spectrum_fdc* f,uint8_t value) {
    if(f->format_state==1) {
        f->format_id[f->format_cursor++]=value;
        if(f->format_cursor==4) { f->format_state=2;f->format_cursor=0; }
    } else if(f->format_state==3) {
        f->buffer[f->format_cursor++]=value;
        if(f->format_cursor==256) {
            if(f->format_id[0]!=f->head || f->format_id[1]!=side(f) || f->format_id[3]!=1) { finish(f,16);return; }
            const uint8_t saved=f->sector;f->sector=f->format_id[2];
            if(!write_sector(f)) finish(f,32);
            f->sector=saved;f->format_state=0;f->format_cursor=0;
        }
    } else if(value==0xFE) { f->format_state=1;f->format_cursor=0; }
    else if(f->format_state==2 && (value==0xFB || value==0xF8)) { f->format_state=3;f->format_cursor=0; }
}
static void transferred(spectrum_fdc* f,uint32_t time) {
    f->drq=false;
    if(++f->cursor<f->length) { f->drq_due=time+112;return; }
    if(f->writing && (f->command&0xE0)==0xA0 && !write_sector(f)) { finish(f,32);return; }
    if(f->multiple && (f->command&0xC0)==0x80) {
        ++f->sector;
        if(f->sector>16 || !read_sector(f)) { finish(f,16);return; }
        f->cursor=0;f->drq_due=time+700;return;
    }
    if((f->command&0xF0)==0xC0) f->sector=f->track;
    finish(f,0);
}
uint8_t spectrum_fdc_read(spectrum_fdc* f,uint8_t port,uint32_t time) {
    tick(f,time);
    if(port==0xFF) return (uint8_t)(0x3F|(f->drq?64:0)|(f->irq?128:0));
    if(port==0x1F) {
        f->irq=false;
        unsigned status=f->status|(f->busy?1:0)|(!ready(f)?128:0);
        if(f->type1) status|=(!f->head?4:0)|((time%700000U)<14000?2:0)|(f->io.readonly?64:0)|32;
        else if(f->drq) status|=2;
        return (uint8_t)status;
    }
    if(port==0x3F) return f->track;
    if(port==0x5F) return f->sector;
    if(port==0x7F && f->drq && !f->writing) {
        f->data=(f->command&0xF0)==0xC0?f->id[f->cursor]:
            (f->command&0xF0)==0xE0?track_byte(f,f->cursor):f->buffer[f->cursor];
        transferred(f,time);
    }
    return f->data;
}
void spectrum_fdc_write(spectrum_fdc* f,uint8_t port,uint8_t value,uint32_t time) {
    tick(f,time);
    if(port==0xFF) {
        if(!(value&4)) spectrum_fdc_reset(f);
        f->system=value;return;
    }
    if(port==0x1F) { command(f,value,time);return; }
    if(port==0x3F) { f->track=value;return; }if(port==0x5F) { f->sector=value;return; }
    if(port==0x7F) {
        f->data=value;
        if(f->drq && f->writing) {
            if((f->command&0xF0)==0xF0) formatted_byte(f,value);else f->buffer[f->cursor]=value;
            if(f->busy) transferred(f,time);
        }
    }
}
