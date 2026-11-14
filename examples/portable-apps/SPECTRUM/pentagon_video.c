#include "ui.h"
#include <string.h>

enum { COLOR_WIDTH=256, COLOR_LINES=64, WIDE_WIDTH=320, WIDE_LINES=104 };

unsigned spectrum_video_mode(const spectrum* s) {
    return s->memory && s->memory->extended?s->memory->control&0x41:0;
}

static unsigned ula_line(unsigned y) {
    return ((y&192)<<5)|((y&7)<<8)|((y&56)<<2);
}

static uint8_t colors(uint8_t byte) {
    // 16C packs the two brightness bits together above the two GRB triples.
    return (uint8_t)(((byte&7)<<4)|((byte&0x40)>>3<<4)|((byte&0x80)>>4)|((byte&0x38)>>3));
}

static bool color_strip(const spectrum* s,unsigned bank,unsigned strip,uint8_t* pixels) {
    uint8_t* source=pixels+COLOR_WIDTH*COLOR_LINES/2;
    for(unsigned part=0;part<4;++part) {
        const unsigned offset=strip*2048+(part&2?8192:0);
        if(!spectrum_bank_read(s->memory,bank-1+(part&1),offset,source,2048)) return false;
        for(unsigned line=0;line<COLOR_LINES;++line) {
            const uint8_t* row=source+ula_line(line);
            uint8_t* target=pixels+line*(COLOR_WIDTH/2)+part;
            for(unsigned x=0;x<32;++x) target[4*x]=colors(row[x]);
        }
    }
    return true;
}

static bool wide_row(const spectrum* s,unsigned bank,unsigned offset,uint8_t* out) {
    // The LCD shows the central 40 of the 48 character columns. The
    // outer columns use offsets 24..31 and 8..15 in the other half-bank.
    return spectrum_bank_read(s->memory,bank,offset+28,out,4) &&
        spectrum_bank_read(s->memory,bank,8192+offset,out+4,32) &&
        spectrum_bank_read(s->memory,bank,offset+8,out+36,4);
}

static bool wide_strip(const spectrum* s,unsigned bank,unsigned strip,uint8_t* pixels,uint8_t* tiles) {
    const unsigned first=strip*WIDE_LINES;
    const unsigned rows=strip<2?WIDE_LINES:304-first;
    for(unsigned line=0;line<rows;++line) {
        const unsigned y=first+line;
        const unsigned band=y<64?0:y<256?1:2;
        const unsigned row=y-(band==0?0:band==1?64:256);
        const unsigned page=band==1?bank:bank-1;
        const unsigned bitmap=ula_line(row)+(band==2?0x1800:0);
        if(!wide_row(s,page,bitmap,pixels+line*(WIDE_WIDTH/8))) return false;
        if(!(line&7)) {
            const unsigned attrs=(band==0?0x1000:band==1?0x1800:0x1300)+(row/8)*32;
            if(!wide_row(s,page,attrs,tiles)) return false;
            for(unsigned x=0;x<WIDE_WIDTH/8;++x) {
                const unsigned a=tiles[x],bright=(a&64)>>3;
                unsigned ink=(a&7)|bright,paper=((a>>3)&7)|bright;
                if((a&128) && (s->frames&16)) {const unsigned t=ink;ink=paper;paper=t;}
                tiles[x]=(uint8_t)(paper<<4|ink);
            }
            tiles+=WIDE_WIDTH/8;
        }
    }
    return true;
}

bool spectrum_video_strip(const spectrum* s,unsigned mode,unsigned strip,uint8_t* pixels,mk61_service_color_frame* frame) {
    if(!s->memory || !mode || strip>=3) return false;
    const unsigned bank=(s->memory->paging&8)?7:5;
    *frame=(mk61_service_color_frame){0};
    frame->pixels=pixels;
    for(unsigned i=0;i<16;++i) frame->palette[i]=spectrum_color(i);
    if(mode&1) {
        frame->format=MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE;
        frame->x=32;frame->y=64+strip*COLOR_LINES;frame->width=COLOR_WIDTH;frame->height=COLOR_LINES;
        frame->pixel_bytes=COLOR_WIDTH*COLOR_LINES/2;
        return color_strip(s,bank,strip,pixels);
    }
    frame->format=MK61_COLOR_TILE1|MK61_COLOR_PRESERVE_OUTSIDE;
    const unsigned first=strip*WIDE_LINES;
    const unsigned rows=strip<2?WIDE_LINES:304-first;
    frame->y=8+first;frame->width=WIDE_WIDTH;frame->height=rows;
    frame->pixel_bytes=WIDE_WIDTH*rows/8;frame->tile_bytes=WIDE_WIDTH*rows/64;
    uint8_t* tiles=pixels+frame->pixel_bytes;
    frame->tiles=tiles;
    return wide_strip(s,bank,strip,pixels,tiles);
}
