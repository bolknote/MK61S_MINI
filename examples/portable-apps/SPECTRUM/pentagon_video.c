#include "ui.h"
#include <string.h>

enum { COLOR_WIDTH=256, COLOR_LINES=64, WIDE_WIDTH=320, WIDE_COLUMNS=48 };
_Static_assert(WIDE_WIDTH*SPECTRUM_WIDE_STRIP_ROWS/2+WIDE_COLUMNS*SPECTRUM_WIDE_STRIP_ROWS/8+512
    <=SPECTRUM_VIDEO_WORK_BYTES,"Wide strip overlaps the disk cache");

unsigned spectrum_video_mode(const spectrum* s) {
    const unsigned mode=SPECTRUM_HAS_PENTAGON && s->memory && s->memory->extended?s->memory->control&0x41:0;
    return mode&1?SPECTRUM_VIDEO_16C:mode?mode:spectrum_timex_mode(s)==2?SPECTRUM_VIDEO_HICOLOR:0;
}

static unsigned ula_line(unsigned y) {
    return ((y&192)<<5)|((y&7)<<8)|((y&56)<<2);
}

static bool video_read(const spectrum* s,const spectrum_video_snapshot* saved,unsigned bank,
                       unsigned offset,uint8_t* out,unsigned size) {
    if(saved && saved->io) return saved->io->read(saved->io->context,
        saved->address+(bank&1)*SPECTRUM_BANK_BYTES+offset,out,size);
    if(s->memory) return spectrum_bank_read(s->memory,bank,offset,out,size);
    memcpy(out,s->ram+offset,size);return true;
}

bool spectrum_video_capture(const spectrum* s,unsigned mode,uint8_t* work,spectrum_video_snapshot* saved) {
    const unsigned bank=s->memory && (s->memory->paging&8)?7:5;
    saved->frames=s->frames;saved->border=mode==SPECTRUM_VIDEO_HICOLOR?spectrum_border(s):0;
    saved->ulaplus=(s->extensions&SPECTRUM_ULAPLUS) && s->ulaplus_mode;
    if(mode==SPECTRUM_VIDEO_HICOLOR)
        for(unsigned i=0;i<(saved->ulaplus?64u:16u);++i) saved->palette[i]=spectrum_palette(s,i);
    if(!saved->io) return true;
    for(unsigned n=mode==SPECTRUM_VIDEO_HICOLOR?1:0;n<2;++n) {
        const unsigned page=bank-1+n;
        const unsigned end=mode==SPECTRUM_VIDEO_WIDE?16384:14336;
        for(unsigned offset=0;offset<end;) {
            const unsigned count=end-offset<4096?end-offset:4096;
            if(!video_read(s,NULL,page,offset,work,count) ||
               !saved->io->write(saved->io->context,saved->address+n*SPECTRUM_BANK_BYTES+offset,work,count)) return false;
            offset+=count;
        }
    }
    return true;
}

static bool hicolor_strip(const spectrum* s,const spectrum_video_snapshot* saved,unsigned bank,unsigned strip,uint8_t* pixels) {
    enum { CELLS=COLOR_WIDTH*COLOR_LINES/8 };
    _Static_assert(5*CELLS<=SPECTRUM_VIDEO_WORK_BYTES,"HiColor strip too large");
    uint8_t* attributes=pixels+CELLS;
    uint8_t* source=pixels+4*CELLS;
    for(unsigned plane=0;plane<2;++plane) {
        const unsigned at=strip*CELLS+plane*8192;
        if(!video_read(s,saved,bank,at,source,CELLS)) return false;
        for(unsigned y=0;y<COLOR_LINES;++y)
            memcpy(pixels+plane*CELLS+y*32,source+ula_line(y),32);
    }
    const bool plus=saved->ulaplus;
    for(unsigned i=CELLS;i--;) {
        const unsigned a=attributes[i],group=plus?(a>>6)*16:(a&64)>>3;
        unsigned paper=group+((a>>3)&7)+(plus?8:0),ink=group+(a&7);
        if(!plus && (a&128) && (saved->frames&16)) { const unsigned t=paper;paper=ink;ink=t; }
        const uint16_t bg=saved->palette[paper],fg=saved->palette[ink];
        attributes[4*i]=(uint8_t)bg;attributes[4*i+1]=(uint8_t)(bg>>8);
        attributes[4*i+2]=(uint8_t)fg;attributes[4*i+3]=(uint8_t)(fg>>8);
    }
    return true;
}

static uint8_t colors(uint8_t byte) {
    // 16C packs the two brightness bits together above the two GRB triples.
    return (uint8_t)(((byte&7)<<4)|((byte&0x40)>>3<<4)|((byte&0x80)>>4)|((byte&0x38)>>3));
}

static bool color_strip(const spectrum* s,const spectrum_video_snapshot* saved,unsigned bank,unsigned strip,uint8_t* pixels) {
    uint8_t* source=pixels+COLOR_WIDTH*COLOR_LINES/2;
    for(unsigned part=0;part<4;++part) {
        const unsigned offset=strip*2048+(part&2?8192:0);
        if(!video_read(s,saved,bank-1+(part&1),offset,source,2048)) return false;
        for(unsigned line=0;line<COLOR_LINES;++line) {
            const uint8_t* row=source+ula_line(line);
            uint8_t* target=pixels+line*(COLOR_WIDTH/2)+part;
            for(unsigned x=0;x<32;++x) target[4*x]=colors(row[x]);
        }
    }
    return true;
}

static bool wide_planes(const spectrum* s,const spectrum_video_snapshot* saved,unsigned bank,unsigned offset,unsigned cells,uint8_t* source) {
    return video_read(s,saved,bank,offset,source,cells*32) &&
           video_read(s,saved,bank,8192+offset,source+256,cells*32);
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

static bool wide_strip(const spectrum* s,const spectrum_video_snapshot* saved,unsigned bank,unsigned first,unsigned rows,uint8_t* pixels) {
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
        if(!wide_planes(s,saved,page,attr_offset,cells,planes))return false;
        for(unsigned i=0;i<cells;++i)wide_row(attrs+i*WIDE_COLUMNS,planes+i*32);
        for(unsigned i=0;i<cells*WIDE_COLUMNS;++i) {
            const unsigned a=attrs[i],bright=(a&64)>>3;
            unsigned ink=(a&7)|bright,paper=((a>>3)&7)|bright;
            if((a&128) && (saved->frames&16)) {const unsigned t=ink;ink=paper;paper=t;}
            attrs[i]=(uint8_t)(paper<<4|ink);
        }

        const unsigned bitmap=ula_line(row)+(band==2?0x1800:0);
        // Gather each ULA phase in two reads and expand rows only once.
        for(unsigned phase=0;phase<8;++phase) {
            if(!wide_planes(s,saved,page,bitmap+phase*256,cells,planes))return false;
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

bool spectrum_video_snapshot_strip(const spectrum* s,const spectrum_video_snapshot* saved,unsigned mode,unsigned strip,
                                   uint8_t* pixels,mk61_service_color_frame* frame) {
    if(!mode || (!SPECTRUM_HAS_SINCLAIR && mode==SPECTRUM_VIDEO_HICOLOR) ||
       (!SPECTRUM_HAS_PENTAGON && mode!=SPECTRUM_VIDEO_HICOLOR) ||
       (mode!=SPECTRUM_VIDEO_HICOLOR && !s->memory) ||
       strip>=(mode==SPECTRUM_VIDEO_WIDE?SPECTRUM_WIDE_STRIPS:3)) return false;
    const unsigned bank=saved->io?5:s->memory && (s->memory->paging&8)?7:5;
    *frame=(mk61_service_color_frame){0};
    frame->pixels=pixels;
    for(unsigned i=0;i<16;++i) frame->palette[i]=spectrum_color(i);
    frame->format=MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE;
    if(mode!=SPECTRUM_VIDEO_WIDE) {
        frame->x=32;frame->y=64+strip*COLOR_LINES;frame->width=COLOR_WIDTH;frame->height=COLOR_LINES;
        if(mode==SPECTRUM_VIDEO_HICOLOR) {
            frame->format=MK61_COLOR_CELL565|MK61_COLOR_PRESERVE_OUTSIDE;
            frame->pixel_bytes=COLOR_WIDTH*COLOR_LINES/8;
            frame->tiles=pixels+frame->pixel_bytes;frame->tile_bytes=frame->pixel_bytes*4;
            return hicolor_strip(s,saved,bank,strip,pixels);
        }
        frame->pixel_bytes=COLOR_WIDTH*COLOR_LINES/2;
        return color_strip(s,saved,bank,strip,pixels);
    }
    const unsigned first=strip*SPECTRUM_WIDE_STRIP_ROWS;
    const unsigned rows=strip+1==SPECTRUM_WIDE_STRIPS?304-first:SPECTRUM_WIDE_STRIP_ROWS;
    frame->y=8+first;frame->width=WIDE_WIDTH;frame->height=rows;
    frame->pixel_bytes=WIDE_WIDTH*rows/2;
    return wide_strip(s,saved,bank,first,rows,pixels);
}

bool spectrum_video_strip(const spectrum* s,unsigned mode,unsigned strip,uint8_t* pixels,mk61_service_color_frame* frame) {
    spectrum_video_snapshot saved={0};
    return spectrum_video_capture(s,mode,pixels,&saved) && spectrum_video_snapshot_strip(s,&saved,mode,strip,pixels,frame);
}
