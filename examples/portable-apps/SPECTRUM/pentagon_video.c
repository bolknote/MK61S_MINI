#include "ui.h"
#include <string.h>

enum { COLOR_WIDTH=256, COLOR_LINES=64, WIDE_WIDTH=320, WIDE_COLUMNS=48 };
_Static_assert(WIDE_WIDTH*SPECTRUM_WIDE_STRIP_ROWS/2+WIDE_COLUMNS*SPECTRUM_WIDE_STRIP_ROWS/8+512
    <=SPECTRUM_VIDEO_WORK_BYTES,"Wide strip overlaps the disk cache");

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

static bool wide_planes(const spectrum* s,unsigned bank,unsigned offset,unsigned cells,uint8_t* source) {
    return spectrum_bank_read(s->memory,bank,offset,source,cells*32) &&
           spectrum_bank_read(s->memory,bank,8192+offset,source+256,cells*32);
}

static void wide_row(uint8_t row[WIDE_COLUMNS],const uint8_t* planes) {
    memcpy(row,planes+24,8);
    memcpy(row+8,planes+256,32);
    memcpy(row+40,planes+8,8);
}

static uint32_t wide_colors(uint32_t bits,uint8_t attr) {
    // Expand one bit per pixel into the low bit of each INDEX4 nibble.
    bits=(bits|(bits<<12))&0x000f000fu;
    bits=(bits|(bits<<6))&0x03030303u;
    bits=(bits|(bits<<3))&0x11111111u;
    const uint32_t paper=attr>>4;
    return paper*0x11111111u ^ bits*((attr&15)^paper);
}

static void wide_pixels(uint8_t* out,const uint8_t* bits,const uint8_t* attrs) {
    // floor((6*x+3)/5) keeps 7, 6 and 7 pixels from each group of
    // three source cells. Pack their INDEX4 colors into ten bytes.
    for(unsigned col=0;col<WIDE_COLUMNS;col+=3,out+=10) {
        const uint32_t a=bits[col],b=bits[col+1],c=bits[col+2];
        const uint32_t left=wide_colors(((a&0xc0)>>1)|(a&31),attrs[col]);
        const uint32_t middle=wide_colors(((b&0x7c)>>1)|(b&1),attrs[col+1]);
        const uint32_t right=wide_colors(((c&0xf0)>>1)|(c&7),attrs[col+2]);
        out[0]=(uint8_t)(left>>20);
        out[1]=(uint8_t)(left>>12);
        out[2]=(uint8_t)(left>>4);
        out[3]=(uint8_t)((left<<4)|((middle>>20)&15));
        out[4]=(uint8_t)(middle>>12);
        out[5]=(uint8_t)(middle>>4);
        out[6]=(uint8_t)((middle<<4)|((right>>24)&15));
        out[7]=(uint8_t)(right>>16);
        out[8]=(uint8_t)(right>>8);
        out[9]=(uint8_t)right;
    }
}

static bool wide_strip(const spectrum* s,unsigned bank,unsigned first,unsigned rows,uint8_t* pixels) {
    uint8_t* attrs=pixels+WIDE_WIDTH*rows/2;
    uint8_t* planes=attrs+WIDE_COLUMNS*(SPECTRUM_WIDE_STRIP_ROWS/8);
    for(unsigned line=0;line<rows;) {
        const unsigned y=first+line;
        const unsigned band=y<64?0:y<256?1:2;
        const unsigned row=y-(band==0?0:band==1?64:256);
        const unsigned page=band==1?bank:bank-1;
        const unsigned boundary=64-(row&63);
        const unsigned lines=rows-line<boundary?rows-line:boundary;
        const unsigned cells=lines/8;
        const unsigned attr_offset=(band==0?0x1000:band==1?0x1800:0x1300)+(row/8)*32;
        if(!wide_planes(s,page,attr_offset,cells,planes))return false;
        for(unsigned i=0;i<cells;++i)wide_row(attrs+i*WIDE_COLUMNS,planes+i*32);
        for(unsigned i=0;i<cells*WIDE_COLUMNS;++i) {
            const unsigned a=attrs[i],bright=(a&64)>>3;
            unsigned ink=(a&7)|bright,paper=((a>>3)&7)|bright;
            if((a&128) && (s->frames&16)) {const unsigned t=ink;ink=paper;paper=t;}
            attrs[i]=(uint8_t)(paper<<4|ink);
        }

        const unsigned bitmap=ula_line(row)+(band==2?0x1800:0);
        // Gather each ULA phase in two reads and expand rows only once.
        for(unsigned phase=0;phase<8;++phase) {
            if(!wide_planes(s,page,bitmap+phase*256,cells,planes))return false;
            for(unsigned cell=0;cell<cells;++cell) {
                uint8_t bits[WIDE_COLUMNS];
                wide_row(bits,planes+cell*32);
                wide_pixels(pixels+(line+phase+8*cell)*(WIDE_WIDTH/2),bits,attrs+cell*WIDE_COLUMNS);
            }
        }
        line+=lines;
    }
    return true;
}

bool spectrum_video_strip(const spectrum* s,unsigned mode,unsigned strip,uint8_t* pixels,mk61_service_color_frame* frame) {
    if(!s->memory || !mode || strip>=(mode&1?3:SPECTRUM_WIDE_STRIPS)) return false;
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
    frame->format=MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE;
    const unsigned first=strip*SPECTRUM_WIDE_STRIP_ROWS;
    const unsigned rows=strip+1==SPECTRUM_WIDE_STRIPS?304-first:SPECTRUM_WIDE_STRIP_ROWS;
    frame->y=8+first;frame->width=WIDE_WIDTH;frame->height=rows;
    frame->pixel_bytes=WIDE_WIDTH*rows/2;
    return wide_strip(s,bank,first,rows,pixels);
}
