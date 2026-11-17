#include "ui.h"
#include <string.h>

enum { COLOR_WIDTH=256, COLOR_LINES=64, WIDE_WIDTH=320, WIDE_COLUMNS=48 };
_Static_assert(WIDE_WIDTH*SPECTRUM_WIDE_STRIP_ROWS/2+WIDE_COLUMNS*SPECTRUM_WIDE_STRIP_ROWS/8+512
    <=SPECTRUM_VIDEO_WORK_BYTES,"Wide strip overlaps the disk cache");

unsigned spectrum_video_mode(const spectrum* s) {
    const unsigned mode=spectrum_pentagon_video_mode(s);
    return mode?mode:spectrum_timex_mode(s)==2?SPECTRUM_VIDEO_HICOLOR:0;
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

static bool capture_range(const spectrum* s,const spectrum_video_snapshot* saved,unsigned bank,
                          unsigned offset,unsigned bytes,uint8_t* work) {
    const uint32_t base=saved->address+(bank&1)*SPECTRUM_BANK_BYTES;
    while(bytes) {
        const unsigned count=bytes<4096?bytes:4096;
        if(!video_read(s,NULL,bank,offset,work,count) ||
           !saved->io->write(saved->io->context,base+offset,work,count)) return false;
        offset+=count;bytes-=count;
    }
    return true;
}

bool spectrum_video_capture(const spectrum* s,unsigned mode,uint8_t* work,spectrum_video_snapshot* saved) {
    const unsigned bank=s->memory && (s->memory->paging&8)?7:5;
    saved->frames=s->frames;saved->border=mode==SPECTRUM_VIDEO_HICOLOR?spectrum_border(s):0;
    saved->ulaplus=(s->extensions&SPECTRUM_ULAPLUS) && s->ulaplus_mode;
    if(mode==SPECTRUM_VIDEO_HICOLOR)
        for(unsigned i=0;i<(saved->ulaplus?64u:16u);++i) saved->palette[i]=spectrum_palette(s,i);
    if(!saved->io) return true;
    if(SPECTRUM_HAS_PENTAGON && mode==SPECTRUM_VIDEO_WIDE) {
        // The middle uses a standard display file in each plane. The
        // upper and lower bands use their own pixel and attribute ranges.
        for(unsigned plane=0;plane<16384;plane+=8192)
            if(!capture_range(s,saved,bank,plane,6912,work) ||
               !capture_range(s,saved,bank-1,plane,2048,work) ||
               !capture_range(s,saved,bank-1,plane+0x1000,256,work) ||
               !capture_range(s,saved,bank-1,plane+0x1300,192,work) ||
               !capture_range(s,saved,bank-1,plane+0x1800,2048,work)) return false;
        return true;
    }
    if(!SPECTRUM_HAS_PENTAGON || mode==SPECTRUM_VIDEO_HICOLOR)
        return capture_range(s,saved,bank,0,14336,work);
    for(unsigned page=bank-1;page<=bank;++page) {
        // The two packed planes have a 2 KiB gap that the renderer skips.
        if(!capture_range(s,saved,page,0,SPECTRUM_BITMAP_BYTES,work) ||
           !capture_range(s,saved,page,8192,SPECTRUM_BITMAP_BYTES,work)) return false;
    }
    return true;
}

static void hicolor_attributes(const spectrum_video_snapshot* saved,uint8_t* attributes,unsigned cells) {
    const bool plus=saved->ulaplus;
    for(unsigned i=cells;i--;) {
        const unsigned a=attributes[i],group=plus?(a>>6)*16:(a&64)>>3;
        unsigned paper=group+((a>>3)&7)+(plus?8:0),ink=group+(a&7);
        if(!plus && (a&128) && (saved->frames&16)) { const unsigned t=paper;paper=ink;ink=t; }
        const uint16_t bg=saved->palette[paper],fg=saved->palette[ink];
        attributes[4*i]=(uint8_t)bg;attributes[4*i+1]=(uint8_t)(bg>>8);
        attributes[4*i+2]=(uint8_t)fg;attributes[4*i+3]=(uint8_t)(fg>>8);
    }
}

static bool hicolor_strip(const spectrum* s,const spectrum_video_snapshot* saved,unsigned bank,unsigned strip,uint8_t* pixels) {
    enum { CELLS=COLOR_WIDTH*COLOR_LINES/8 };
    _Static_assert(5*CELLS<=SPECTRUM_VIDEO_WORK_BYTES,"HiColor strip too large");
    uint8_t* source=pixels+4*CELLS;
    for(unsigned plane=0;plane<2;++plane) {
        const unsigned at=strip*CELLS+plane*8192;
        if(!video_read(s,saved,bank,at,source,CELLS)) return false;
        for(unsigned y=0;y<COLOR_LINES;++y)
            memcpy(pixels+plane*CELLS+y*32,source+ula_line(y),32);
    }
    hicolor_attributes(saved,pixels+CELLS,CELLS);
    return true;
}

void spectrum_hicolor_flash(const spectrum* s,spectrum_hicolor_changes* changes) {
    const uint8_t* const attributes=(s->memory?s->memory->cache:s->ram)+8192;
    for(unsigned i=0;i<SPECTRUM_BITMAP_BYTES;++i)
        if(attributes[i]&128) spectrum_hicolor_dirty(changes,i);
}

void spectrum_hicolor_patch(const spectrum* s,const spectrum_video_snapshot* saved,unsigned strip,
                            const spectrum_video_damage* d,uint8_t* pixels) {
    const uint8_t* const screen=s->memory?s->memory->cache:s->ram;
    const unsigned width=d->right-d->left,cells=width*(d->bottom-d->top);
    uint8_t* const attributes=pixels+cells;
    for(unsigned y=d->top;y<d->bottom;++y) {
        const unsigned at=ula_line(strip*COLOR_LINES+y)+d->left,offset=(y-d->top)*width;
        memcpy(pixels+offset,screen+at,width);
        memcpy(attributes+offset,screen+8192+at,width);
    }
    hicolor_attributes(saved,attributes,cells);
}

void spectrum_hicolor_frame(const spectrum_video_damage* d,unsigned strip,uint8_t* pixels,
                            mk61_service_color_frame* f) {
    const unsigned cols=d->right-d->left,rows=d->bottom-d->top,cells=cols*rows;
    *f=(mk61_service_color_frame){0};
    f->pixels=pixels;f->tiles=pixels+cells;
    f->pixel_bytes=cells;f->tile_bytes=4*cells;
    f->x=32+8*d->left;f->y=64+64*strip+d->top;f->width=8*cols;f->height=rows;
    f->format=MK61_COLOR_CELL565|MK61_COLOR_PRESERVE_OUTSIDE;
}

#if SPECTRUM_HAS_PENTAGON
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

static void wide_row(uint8_t row[WIDE_COLUMNS],const uint8_t* low,const uint8_t* high) {
    memcpy(row,low+24,8);
    memcpy(row+8,high,32);
    memcpy(row+40,low+8,8);
}

static uint32_t wide_colors(uint32_t bits,uint8_t attr) {
    // Expand one bit per pixel into the low bit of each INDEX4 nibble.
    bits=(bits|(bits<<12))&0x000f000fu;
    bits=(bits|(bits<<6))&0x03030303u;
    bits=(bits|(bits<<3))&0x11111111u;
    const uint32_t paper=attr>>4;
    return paper*0x11111111u ^ bits*((attr&15)^paper);
}

static void wide_pixels(uint8_t* out,const uint8_t* bits,const uint8_t* attrs,unsigned columns) {
    // floor((6*x+3)/5) keeps 7, 6 and 7 pixels from each group of
    // three source cells. Pack their INDEX4 colors into ten bytes.
    for(unsigned col=0;col<columns;col+=3,out+=10) {
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

typedef struct { uint16_t first,bitmap,attribute;uint8_t rows,outer; } wide_area;
static const wide_area wide_areas[]={
    {0,0,0x1000,64,1},{64,0,0x1800,192,0},{256,0x1800,0x1300,48,1}
};
static const wide_area* wide_area_at(unsigned y) {
    return &wide_areas[y<64?0:y<256?1:2];
}

static void wide_attributes(uint8_t* attrs,unsigned count,bool flash) {
    for(unsigned i=0;i<count;++i) {
        const unsigned a=attrs[i],bright=(a&64)>>3;
        unsigned ink=(a&7)|bright,paper=((a>>3)&7)|bright;
        if((a&128) && flash) {const unsigned t=ink;ink=paper;paper=t;}
        attrs[i]=(uint8_t)(paper<<4|ink);
    }
}

static bool wide_strip(const spectrum* s,const spectrum_video_snapshot* saved,unsigned bank,unsigned first,unsigned rows,uint8_t* pixels) {
    uint8_t* attrs=pixels+WIDE_WIDTH*rows/2;
    uint8_t* planes=attrs+WIDE_COLUMNS*(SPECTRUM_WIDE_STRIP_ROWS/8);
    for(unsigned line=0;line<rows;) {
        const unsigned y=first+line;
        const wide_area* area=wide_area_at(y);
        const unsigned row=y-area->first,page=bank-area->outer;
        const unsigned boundary=64-(row&63);
        const unsigned lines=rows-line<boundary?rows-line:boundary;
        const unsigned cells=lines/8;
        const unsigned attr_offset=area->attribute+(row/8)*32;
        if(!wide_planes(s,saved,page,attr_offset,cells,planes))return false;
        for(unsigned i=0;i<cells;++i)wide_row(attrs+i*WIDE_COLUMNS,planes+i*32,planes+256+i*32);
        wide_attributes(attrs,cells*WIDE_COLUMNS,(saved->frames&16)!=0);

        const unsigned bitmap=ula_line(row)+area->bitmap;
        // Gather each ULA phase in two reads and expand rows only once.
        for(unsigned phase=0;phase<8;++phase) {
            if(!wide_planes(s,saved,page,bitmap+phase*256,cells,planes))return false;
            for(unsigned cell=0;cell<cells;++cell) {
                uint8_t bits[WIDE_COLUMNS];
                wide_row(bits,planes+cell*32,planes+256+cell*32);
                wide_pixels(pixels+(line+phase+8*cell)*(WIDE_WIDTH/2),bits,attrs+cell*WIDE_COLUMNS,WIDE_COLUMNS);
            }
        }
        line+=lines;
    }
    return true;
}

bool spectrum_pentagon_flash(const spectrum* s,uint8_t* work,spectrum_video_damage strips[SPECTRUM_WIDE_STRIPS]) {
    const unsigned bank=(s->memory->paging&8)?7:5;
    for(unsigned area=0;area<sizeof(wide_areas)/sizeof(*wide_areas);++area) {
        const wide_area* a=&wide_areas[area];
        const unsigned bytes=a->rows*4;
        if(!video_read(s,NULL,bank-a->outer,a->attribute,work,bytes) ||
           !video_read(s,NULL,bank-a->outer,a->attribute+8192,work+bytes,bytes)) return false;
        for(unsigned row=0;row<a->rows;row+=8) {
            uint8_t attrs[WIDE_COLUMNS];
            const unsigned offset=row*4,y=a->first+row;
            wide_row(attrs,work+offset,work+bytes+offset);
            spectrum_video_damage* d=&strips[y/SPECTRUM_WIDE_STRIP_ROWS];
            for(unsigned x=0;x<WIDE_COLUMNS;x+=3)
                if((attrs[x]|attrs[x+1]|attrs[x+2])&128)
                    spectrum_video_include_cell(d,x/3,y%SPECTRUM_WIDE_STRIP_ROWS,8);
        }
    }
    return true;
}

static bool wide_live_cells(const spectrum* s,unsigned bank,unsigned offset,unsigned x,unsigned count,uint8_t* row) {
    while(count) {
        const unsigned end=x<8?8:x<40?40:48;
        const unsigned start=x<8?24+x:x<40?8192+x-8:x-32;
        const unsigned n=count<end-x?count:end-x;
        if(!video_read(s,NULL,bank,offset+start,row,n)) return false;
        row+=n;x+=n;count-=n;
    }
    return true;
}

bool spectrum_pentagon_patch(const spectrum* s,unsigned mode,unsigned strip,const spectrum_video_damage* d,
                            uint8_t* pixels) {
    const unsigned bank=(s->memory->paging&8)?7:5,cols=d->right-d->left;
    if(mode==SPECTRUM_VIDEO_16C) {
        uint8_t row[32];
        for(unsigned y=d->top;y<d->bottom;++y,pixels+=4*cols) {
            const unsigned first=2048*strip+ula_line(y)+d->left;
            for(unsigned part=0;part<4;++part) {
                if(!video_read(s,NULL,bank-1+(part&1),first+(part&2?8192:0),row,cols)) return false;
                for(unsigned x=0;x<cols;++x)pixels[4*x+part]=colors(row[x]);
            }
        }
    } else {
        uint8_t bits[WIDE_COLUMNS],attrs[WIDE_COLUMNS];
        const unsigned first=strip*SPECTRUM_WIDE_STRIP_ROWS,x=d->left*3,columns=cols*3;
        for(unsigned y=d->top;y<d->bottom;++y,pixels+=10*cols) {
            const wide_area* area=wide_area_at(first+y);
            const unsigned row=first+y-area->first,page=bank-area->outer;
            if(y==d->top || !(row&7)) {
                if(!wide_live_cells(s,page,area->attribute+(row/8)*32,x,columns,attrs)) return false;
                wide_attributes(attrs,columns,(s->frames&16)!=0);
            }
            if(!wide_live_cells(s,page,area->bitmap+ula_line(row),x,columns,bits)) return false;
            wide_pixels(pixels,bits,attrs,columns);
        }
    }
    return true;
}

static void index4_frame(const uint8_t* pixels,mk61_service_color_frame* frame) {
    *frame=(mk61_service_color_frame){0};
    frame->pixels=pixels;
    for(unsigned i=0;i<16;++i) frame->palette[i]=spectrum_color(i);
    frame->format=MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE;
}

void spectrum_pentagon_frame(unsigned mode,unsigned strip,const spectrum_video_damage* d,const uint8_t* pixels,
                             mk61_service_color_frame* f) {
    index4_frame(pixels,f);
    const unsigned unit=mode==SPECTRUM_VIDEO_WIDE?20:8;
    f->x=unit*d->left+(mode==SPECTRUM_VIDEO_WIDE?0:32);
    f->y=d->top+(mode==SPECTRUM_VIDEO_WIDE?8+strip*SPECTRUM_WIDE_STRIP_ROWS:64+strip*COLOR_LINES);
    f->width=unit*(d->right-d->left);f->height=d->bottom-d->top;
    f->pixel_bytes=f->width*f->height/2;
}

void spectrum_pentagon_clip(unsigned mode,const spectrum_video_damage* d,uint8_t* pixels,mk61_service_color_frame* f) {
    const unsigned unit=mode==SPECTRUM_VIDEO_WIDE?10:4,pitch=f->width/2;
    const unsigned bytes=unit*(d->right-d->left),rows=d->bottom-d->top;
    const uint8_t* src=pixels+d->top*pitch+unit*d->left;
    if(src!=pixels || bytes!=pitch)
        for(unsigned y=0;y<rows;++y)memmove(pixels+y*bytes,src+y*pitch,bytes);
    f->x+=2*unit*d->left;f->y+=d->top;
    f->width=2*bytes;f->height=rows;f->pixel_bytes=bytes*rows;
}
#endif

bool spectrum_video_snapshot_strip(const spectrum* s,const spectrum_video_snapshot* saved,unsigned mode,unsigned strip,
                                   uint8_t* pixels,mk61_service_color_frame* frame) {
    if(!mode || (!SPECTRUM_HAS_SINCLAIR && mode==SPECTRUM_VIDEO_HICOLOR) ||
       (!SPECTRUM_HAS_PENTAGON && mode!=SPECTRUM_VIDEO_HICOLOR) ||
       (mode!=SPECTRUM_VIDEO_HICOLOR && !s->memory) ||
       strip>=(mode==SPECTRUM_VIDEO_WIDE?SPECTRUM_WIDE_STRIPS:3)) return false;
    const unsigned bank=saved->io?5:s->memory && (s->memory->paging&8)?7:5;
    if(SPECTRUM_HAS_SINCLAIR && mode==SPECTRUM_VIDEO_HICOLOR) {
        static const spectrum_video_damage full={0,32,0,64};
        spectrum_hicolor_frame(&full,strip,pixels,frame);
        return hicolor_strip(s,saved,bank,strip,pixels);
    }
#if SPECTRUM_HAS_PENTAGON
    index4_frame(pixels,frame);
    if(mode!=SPECTRUM_VIDEO_WIDE) {
        frame->x=32;frame->y=64+strip*COLOR_LINES;frame->width=COLOR_WIDTH;frame->height=COLOR_LINES;
        frame->pixel_bytes=COLOR_WIDTH*COLOR_LINES/2;
        return color_strip(s,saved,bank,strip,pixels);
    }
    const unsigned first=strip*SPECTRUM_WIDE_STRIP_ROWS;
    const unsigned rows=strip+1==SPECTRUM_WIDE_STRIPS?304-first:SPECTRUM_WIDE_STRIP_ROWS;
    frame->y=8+first;frame->width=WIDE_WIDTH;frame->height=rows;
    frame->pixel_bytes=WIDE_WIDTH*rows/2;
    return wide_strip(s,saved,bank,first,rows,pixels);
#else
    return false;
#endif
}

bool spectrum_video_strip(const spectrum* s,unsigned mode,unsigned strip,uint8_t* pixels,mk61_service_color_frame* frame) {
    spectrum_video_snapshot saved={0};
    return spectrum_video_capture(s,mode,pixels,&saved) && spectrum_video_snapshot_strip(s,&saved,mode,strip,pixels,frame);
}
