#include "../examples/portable-apps/ANOTHER/display_pages.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    uint16_t pixels[2][AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT];
    aw_display_pages *pages;
    unsigned selected, visible, selects, shows, rectangles, pixel_bytes;
    unsigned early_rectangles, busy_writes;
    bool fail_select, fail_show, fail_rect, cancel, waited;
} panel;
typedef struct { uint8_t bytes[2 * AW_VIDEO_PAGE_BYTES]; unsigned reads, writes, write_bytes; } store;
static bool rd(void *ctx, uint32_t offset, void *out, uint32_t size) {
    store *s=ctx;assert(offset<=sizeof(s->bytes) && size<=sizeof(s->bytes)-offset);
    ++s->reads;memcpy(out,s->bytes+offset,size);return true;
}
static bool wr(void *ctx, uint32_t offset, const void *in, uint32_t size) {
    store *s=ctx;assert(offset<=sizeof(s->bytes) && size<=sizeof(s->bytes)-offset);
    ++s->writes;s->write_bytes+=size;memcpy(s->bytes+offset,in,size);return true;
}
static bool select_page(void *ctx,unsigned page) {
    panel *p=ctx;assert(page<2);if(p->fail_select)return false;
    ++p->selects;p->selected=page;return true;
}
static bool show_page(void *ctx,unsigned page) {
    panel *p=ctx;assert(page==p->selected && p->waited);
    if (p->fail_show) {
        while (p->pages->pending_bands) assert(aw_display_pages_write_one(p->pages));
        return false;
    }
    ++p->shows;p->visible=page;return true;
}
static bool send_rect(void *ctx,unsigned x,unsigned y,unsigned width,unsigned height,
                      const uint8_t *pixels,const uint16_t *palette,bool clear) {
    panel *p=ctx;(void)clear;
    assert(p->selected<2 && !(x&1) && !(width&1) && width && height && height<=80);
    assert(x+width<=320 && y+height<=200 && width*height/2<=12800);
    if (p->rectangles && p->pages->pending_bands) {
        ++p->busy_writes;
        assert(aw_display_pages_write_one(p->pages));
    }
    if(p->fail_rect)return false;
    if(!p->waited) {assert(p->selected!=p->visible);++p->early_rectangles;}
    ++p->rectangles;p->pixel_bytes+=width*height/2;
    for(unsigned row=0;row<height;++row)for(unsigned col=0;col<width;++col) {
        uint8_t pair=pixels[row*(width/2)+col/2];unsigned index=(pair>>((col&1)?0:4))&15;
        p->pixels[p->selected][(y+row)*320+x+col]=palette[index];
    }
    return true;
}
static bool wait_for_frame(void *ctx) {
    panel *p=ctx;
    assert(!p->waited);
    p->waited=true;
    return !p->cancel;
}
static bool frame_at_deadline(aw_display_pages *pages,const uint8_t *frame,const uint16_t *palette,panel *p) {
    p->waited=false;
    return aw_display_pages_present(pages,frame,palette,NULL,select_page,show_page,send_rect,wait_for_frame,p);
}
static void equal(const panel *p,const uint8_t *frame,const uint16_t *palette) {
    assert(p->visible<2);
    for(unsigned i=0;i<320u*200u;++i) {
        uint8_t pair=frame[i/2];unsigned index=(pair>>((i&1)?0:4))&15;
        assert(p->pixels[p->visible][i]==palette[index]);
    }
}
static void solid_flashes(unsigned capacity) {
    uint8_t *frame=malloc(AW_VIDEO_PAGE_BYTES),*shared=malloc(capacity);
    panel *p=calloc(1,sizeof(*p));store *memory=calloc(1,sizeof(*memory));
    assert(frame && shared && p && memory);p->selected=p->visible=2;
    aw_assets a={0};a.capacity=sizeof(memory->bytes);a.ctx=memory;a.store_read=rd;a.store_write=wr;
    aw_display_compact first;aw_display_pages pages;
    assert(aw_display_compact_init(&first,&a,0,shared,capacity,shared,capacity));
    assert(aw_display_pages_init(&pages,&first,AW_VIDEO_PAGE_BYTES));
    p->pages = &pages;
    uint16_t palette[16]={0},alternate[16]={0};palette[15]=0xffff;
    alternate[4]=0xffff;alternate[5]=0;alternate[0]=0x1234;
    memset(frame,0xff,AW_VIDEO_PAGE_BYTES);
    assert(frame_at_deadline(&pages,frame,palette,p));equal(p,frame,palette);
    memset(frame,0,AW_VIDEO_PAGE_BYTES);
    assert(frame_at_deadline(&pages,frame,palette,p));equal(p,frame,palette);
    assert(p->shows==2 && p->pixel_bytes==2*AW_VIDEO_PAGE_BYTES);
    const unsigned bytes=p->pixel_bytes,reads=memory->reads,writes=memory->writes;
    for(unsigned n=0;n<20;++n) {
        memset(frame,(n&1)?0x55:0x44,AW_VIDEO_PAGE_BYTES);
        assert(frame_at_deadline(&pages,frame,alternate,p));
        equal(p,frame,alternate);
    }
    /* Alternate indices and palettes represent the same two RGB pages.
     * Switching them never rewrites pixels or touches PSRAM. */
    assert(p->pixel_bytes==bytes && memory->reads==reads && memory->writes==writes && p->shows==22);
    memset(frame,0x44,AW_VIDEO_PAGE_BYTES);p->fail_show=true;
    const unsigned visible=p->visible;
    assert(!frame_at_deadline(&pages,frame,alternate,p));
    assert(p->visible==visible);p->fail_show=false;
    assert(frame_at_deadline(&pages,frame,alternate,p));equal(p,frame,alternate);
    /* Subsequent ordinary images still compare with the page's actual saved
     * indices and palette, even after repeated RGB-only page reuse. */
    frame[1234]=0x04;
    assert(frame_at_deadline(&pages,frame,alternate,p));equal(p,frame,alternate);
    free(memory);free(p);free(shared);free(frame);
}
static uint32_t rand32(uint32_t *s){*s=*s*1664525u+1013904223u;return *s;}
static void run(unsigned capacity) {
    uint8_t *frame=calloc(1,AW_VIDEO_PAGE_BYTES),*shared=malloc(capacity);
    panel *p=calloc(1,sizeof(*p));store *memory=calloc(1,sizeof(*memory));
    assert(frame && shared && p && memory);p->selected=p->visible=2;
    aw_assets a={0};a.capacity=sizeof(memory->bytes);a.ctx=memory;a.store_read=rd;a.store_write=wr;
    aw_display_compact first;aw_display_pages pages;
    assert(aw_display_compact_init(&first,&a,0,shared,capacity,shared,capacity));
    assert(!aw_display_pages_init(&pages,&first,0));
    assert(!aw_display_pages_init(&pages,&first,AW_VIDEO_PAGE_BYTES-1));
    assert(aw_display_pages_init(&pages,&first,AW_VIDEO_PAGE_BYTES));
    p->pages = &pages;
    uint16_t palette[4][16];
    for(unsigned k=0;k<4;++k)for(unsigned i=0;i<16;++i)palette[k][i]=(uint16_t)(i*0x1111u^(k*0x2345u));
    assert(frame_at_deadline(&pages,frame,palette[0],p));equal(p,frame,palette[0]);
    assert(p->pixel_bytes==AW_VIDEO_PAGE_BYTES && p->shows==1 && p->selects==1 && p->busy_writes);
    unsigned writes=memory->writes,write_bytes=memory->write_bytes;
    assert(frame_at_deadline(&pages,frame,palette[0],p));
    assert(memory->writes==writes && p->shows==1 && p->selects==1);
    const unsigned early=p->early_rectangles;
    frame[47*AW_VIDEO_STRIDE+35]^=0x10;
    assert(frame_at_deadline(&pages,frame,palette[0],p));equal(p,frame,palette[0]);
    assert(p->early_rectangles==early && memory->writes==writes+1 &&
           memory->write_bytes>write_bytes && memory->write_bytes<write_bytes+AW_VIDEO_BAND_ROWS*AW_VIDEO_STRIDE);
    /* A copy-from-above packet in row zero is invalid even if its length fits. */
    aw_display_compact *active = pages.slot[pages.visible];
    memory->bytes[active->external_base] = 0;
    assert(!frame_at_deadline(&pages,frame,palette[0],p) && !active->valid && !a.fault);
    assert(frame_at_deadline(&pages,frame,palette[0],p));equal(p,frame,palette[0]);
    p->cancel=true;
    assert(!frame_at_deadline(&pages,frame,palette[1],p));equal(p,frame,palette[0]);
    assert(p->early_rectangles>early && !pages.slot[pages.selected]->valid);
    p->cancel=false;
    unsigned before=p->pixel_bytes;
    assert(frame_at_deadline(&pages,frame,palette[1],p));equal(p,frame,palette[1]);
    assert(p->pixel_bytes-before==AW_VIDEO_PAGE_BYTES);
    frame[2*AW_VIDEO_STRIDE+5]^=1;before=p->pixel_bytes;
    assert(frame_at_deadline(&pages,frame,palette[0],p));equal(p,frame,palette[0]);
    assert(p->pixel_bytes-before<AW_VIDEO_PAGE_BYTES);
    frame[3*AW_VIDEO_STRIDE+6]^=1;before=p->pixel_bytes;
    assert(frame_at_deadline(&pages,frame,palette[1],p));equal(p,frame,palette[1]);
    assert(p->pixel_bytes-before<AW_VIDEO_PAGE_BYTES);
    uint32_t random=0x9a7f1234u;
    /* Exercise dense and sparse differences, palette eviction and recovery. */
    for(unsigned iteration=0;iteration<400;++iteration) {
        if(iteration%79==0)for(unsigned i=0;i<AW_VIDEO_PAGE_BYTES;++i)frame[i]=(uint8_t)(rand32(&random)>>24);
        else if(iteration%79==2)memset(frame,(int)(iteration&0xff),AW_VIDEO_PAGE_BYTES);
        else for(unsigned j=0;j<1+iteration%70;++j) {
            unsigned at=rand32(&random)%AW_VIDEO_PAGE_BYTES;frame[at]^=(uint8_t)(1u<<(rand32(&random)&7));
        }
        const unsigned k=iteration%29<20?(iteration&1):2+(iteration&1);
        assert(frame_at_deadline(&pages,frame,palette[k],p));equal(p,frame,palette[k]);
        if (iteration%79==0)
            assert(pages.slot[pages.visible]->band_sizes[0] == AW_VIDEO_STRIDE*AW_VIDEO_BAND_ROWS);
    }
    p->fail_select=true;
    unsigned k=0;
    while(k<4 && !memcmp(pages.slot[pages.visible]->palette,palette[k],sizeof(palette[k]))) ++k;
    assert(k<4);const uint16_t *different=palette[k];
    assert(!frame_at_deadline(&pages,frame,different,p));
    p->fail_select=false;p->fail_show=true;
    const unsigned visible=p->visible;
    assert(!frame_at_deadline(&pages,frame,different,p));
    assert(p->visible==visible && !pages.slot[pages.selected]->valid && !pages.pending_bands);
    p->fail_show=false;
    assert(frame_at_deadline(&pages,frame,different,p));equal(p,frame,different);
    frame[71*AW_VIDEO_STRIDE+2]^=0x10;p->fail_rect=true;
    assert(!frame_at_deadline(&pages,frame,different,p));
    assert(!pages.slot[pages.selected]->valid);
    p->fail_rect=false;
    assert(frame_at_deadline(&pages,frame,different,p));equal(p,frame,different);
    free(memory);free(p);free(shared);free(frame);
}
int main(void){run(12800);run(3200);solid_flashes(12800);solid_flashes(3200);
    puts("Another World two-page RGB, packed bands, LCD overlap and fallback tests passed");return 0;}
