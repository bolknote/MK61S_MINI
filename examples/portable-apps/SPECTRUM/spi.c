#include "disk.h"
#include <string.h>
/* A removable SDHC card on the DivMMC SPI bus. All addresses refer to the
 * mounted image; the PicoCalc's physical card is never exposed to the guest. */
void spectrum_spi_reset(spectrum_spi* s) {
    const spectrum_disk_io io=s->io;memset(s,0,sizeof(*s));s->io=io;s->idle=true;
}
void spectrum_spi_select(spectrum_spi* s,uint8_t value) {
    const bool selected=!(value&1) && (value&2);
    if(s->selected!=selected) {
        s->command_size=s->response_size=s->response_at=s->data_mode=s->write_mode=0;
        s->write_state=0;s->cursor=0;
    }
    s->selected=selected;
}
static void response(spectrum_spi* s,uint8_t r) {
    s->response[0]=r;s->response_size=1;s->response_at=0;
}
static uint8_t crc7(const uint8_t* p,unsigned n) {
    uint8_t crc=0;
    while(n--) for(unsigned bit=128;bit;bit>>=1) {
        crc=(uint8_t)((crc<<1)^(((crc&64)!=0)!=((*p&bit)!=0)?9:0));
        if(bit==1) ++p;
    }
    return (uint8_t)((crc<<1)|1);
}
static bool address(spectrum_spi* s,uint32_t arg) {
    if(!s->high_capacity && (arg&511)) return false;
    s->lba=s->high_capacity?arg:arg/512;
    return s->lba<s->io.bytes/512;
}
static void register_data(spectrum_spi* s,const uint8_t* bytes) {
    s->response[s->response_size++]=0xFE;uint16_t crc=0;
    for(unsigned i=0;i<16;++i) { s->response[s->response_size++]=bytes[i];crc=spectrum_crc16(crc,bytes[i]); }
    s->response[s->response_size++]=(uint8_t)(crc>>8);s->response[s->response_size++]=(uint8_t)crc;
}
static void command(spectrum_spi* s) {
    const unsigned cmd=s->command[0]&63;
    const uint32_t arg=((uint32_t)s->command[1]<<24)|((uint32_t)s->command[2]<<16)|((unsigned)s->command[3]<<8)|s->command[4];
    const bool app=s->app_command;s->app_command=false;
    response(s,s->idle?1:0);
    if((s->crc_enabled || cmd==0 || cmd==8) && crc7(s->command,5)!=s->command[5]) { s->response[0]|=8;return; }
    if(!s->io.read || s->io.bytes<512) { s->response[0]|=4;return; }
    if(cmd==0) { s->idle=true;s->high_capacity=false;s->data_mode=s->write_mode=0;response(s,1); }
    else if(cmd==8) { s->response[1]=s->response[2]=0;s->response[3]=1;s->response[4]=(uint8_t)arg;s->response_size=5; }
    else if(cmd==55) s->app_command=true;
    else if((cmd==41 && app) || cmd==1) { s->idle=false;s->high_capacity=cmd==41 && (arg&0x40000000);response(s,0); }
    else if(cmd==58) { s->response[1]=(uint8_t)(0x80|(s->high_capacity?64:0));s->response[2]=0xFF;s->response[3]=0x80;s->response[4]=0;s->response_size=5; }
    else if(cmd==59) s->crc_enabled=arg&1;
    else if(s->idle) return;
    else if(cmd==16) { if(arg!=512) response(s,64); }
    else if(cmd==13) { s->response[1]=s->io.readonly?32:0;s->response_size=2; }
    else if(cmd==9) {
        /* CSD v2, including the real image capacity in 512KiB units. */
        uint8_t csd[16]={0x40,0x0E,0,0x32,0x5B,0x59,0,0,0,0,0x7F,0x80,0x0A,0x40,0,0};
        const uint32_t size=s->io.bytes/(512U*1024U)-1;
        csd[7]=(uint8_t)(size>>16)&63;csd[8]=(uint8_t)(size>>8);csd[9]=(uint8_t)size;
        csd[14]=s->io.readonly?0x30:0;csd[15]=crc7(csd,15);register_data(s,csd);
    } else if(cmd==10) {
        uint8_t cid[16]={0x4D,'M','8','I','M','A','G','E',0x10,0,0,0,1,1,0xA1,0};
        cid[15]=crc7(cid,15);register_data(s,cid);
    } else if(cmd==17 || cmd==18 || cmd==24 || cmd==25) {
        if(!address(s,arg)) { response(s,32);return; }
        s->cursor=0;s->write_state=0;
        if(cmd==17 || cmd==18) s->data_mode=cmd==18?2:1;
        else if(s->io.readonly || !s->io.write) response(s,4);
        else s->write_mode=cmd==25?2:1;
    } else if(cmd==12) { s->data_mode=0;s->cursor=0;s->response[0]=0xFF;s->response[1]=0;s->response_size=2; }
    else if(cmd==23 && app) { /* Pre-erase hint, writes are synchronous. */ }
    else response(s,4);
}
uint8_t spectrum_spi_transfer(spectrum_spi* s,uint8_t value) {
    if(!s->selected) return 0xFF;
    if(s->response_at<s->response_size) return s->response[s->response_at++];
    if(s->write_mode) {
        if(!s->write_state) {
            if(value==0xFD && s->write_mode==2) { s->write_mode=0;return 0xFF; }
            if(value==(s->write_mode==2?0xFC:0xFE)) { s->write_state=1;s->cursor=0;s->crc=0; }
        } else if(s->write_state==1) {
            s->block[s->cursor++]=value;s->crc=spectrum_crc16(s->crc,value);
            if(s->cursor==512) s->write_state=2;
        } else if(s->write_state==2) { s->crc_bytes=value;s->write_state=3; }
        else {
            uint8_t result=5;
            if(s->crc_enabled && (((unsigned)s->crc_bytes<<8)|value)!=s->crc) result=11;
            else if(s->lba>=s->io.bytes/512 || !s->io.write(s->io.context,s->lba*512,s->block,512)) result=13;
            else ++s->writes;
            response(s,result);s->response[1]=0;s->response[2]=0xFF;s->response_size=3;
            ++s->lba;s->write_state=0;if(s->write_mode==1) s->write_mode=0;
        }
        return 0xFF;
    }
    if(s->command_size || (value&0xC0)==0x40) {
        s->command[s->command_size++]=value;
        if(s->command_size==6) { s->command_size=0;command(s); }
        return 0xFF;
    }
    if(s->data_mode) {
        if(!s->cursor) {
            if(s->lba>=s->io.bytes/512 || !s->io.read(s->io.context,s->lba*512,s->block,512)) { s->data_mode=0;return 9; }
            ++s->reads;s->cursor=1;s->crc=0;return 0xFE;
        }
        if(s->cursor<=512) { const uint8_t byte=s->block[s->cursor++-1];s->crc=spectrum_crc16(s->crc,byte);return byte; }
        if(s->cursor++==513) return (uint8_t)(s->crc>>8);
        s->cursor=0;++s->lba;if(s->data_mode==1) s->data_mode=0;return (uint8_t)s->crc;
    }
    return 0xFF;
}
