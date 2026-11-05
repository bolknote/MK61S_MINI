#include "media.h"
#include <string.h>
enum spectrum_error spectrum_scl_unpack(const spectrum_source* source,const spectrum_memory_io* io,uint32_t target) {
    uint8_t bytes[256],header[16]={0};
    if(!source || !io || !source->read || !io->clear || !io->write) return SPECTRUM_IO;
    if(source->size<13 || !source->read(source->context,0,bytes,9)) return SPECTRUM_IO;
    if(memcmp(bytes,"SINCLAIR",8) || bytes[8]>128) return SPECTRUM_FORMAT;
    const unsigned files=bytes[8];unsigned sectors=0;
    if(source->size<13U+14U*files) return SPECTRUM_FORMAT;
    for(unsigned i=0;i<files;++i) {
        if(!source->read(source->context,9+14*i,bytes,14)) return SPECTRUM_IO;
        sectors+=bytes[13];
    }
    const uint32_t data=9+14*files,end=data+sectors*256U;
    if(sectors>2544 || source->size!=end+4) return SPECTRUM_FORMAT;
    uint32_t sum=0;
    for(uint32_t at=0;at<end;) {
        const unsigned n=end-at<256?end-at:256;
        if(!source->read(source->context,at,bytes,n)) return SPECTRUM_IO;
        for(unsigned i=0;i<n;++i) sum+=bytes[i];
        at+=n;
    }
    if(!source->read(source->context,end,bytes,4)) return SPECTRUM_IO;
    const uint32_t stored=bytes[0]|((uint32_t)bytes[1]<<8)|((uint32_t)bytes[2]<<16)|((uint32_t)bytes[3]<<24);
    if(sum!=stored) return SPECTRUM_FORMAT;
    if(!io->clear(io->context,target,SPECTRUM_TRD_BYTES)) return SPECTRUM_IO;
    unsigned next=16;
    for(unsigned i=0;i<files;++i) {
        if(!source->read(source->context,9+14*i,header,14)) return SPECTRUM_IO;
        header[14]=(uint8_t)(next&15);header[15]=(uint8_t)(next/16);next+=header[13];
        if(!io->write(io->context,target+i*16,header,16)) return SPECTRUM_IO;
    }
    memset(bytes,0,256);bytes[0xE1]=(uint8_t)(next&15);bytes[0xE2]=(uint8_t)(next/16);
    bytes[0xE3]=0x16;bytes[0xE4]=(uint8_t)files;bytes[0xE5]=(uint8_t)(2544-sectors);bytes[0xE6]=(uint8_t)((2544-sectors)>>8);
    bytes[0xE7]=0x10;memcpy(bytes+0xF5,"SCLIMAGE",8);
    if(!io->write(io->context,target+0x800,bytes,256)) return SPECTRUM_IO;
    for(unsigned i=0;i<sectors;++i)
        if(!source->read(source->context,data+i*256,bytes,256) ||
           !io->write(io->context,target+4096+i*256,bytes,256)) return SPECTRUM_IO;
    return SPECTRUM_OK;
}
