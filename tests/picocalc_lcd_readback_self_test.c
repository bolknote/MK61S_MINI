#include "picocalc_lcd_readback.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    bool selected, data;
    unsigned count, fail_at;
    uint8_t bytes[32], modes[32];
} wire;
static bool lines(void *ctx, bool selected, bool data) {
    wire *w=ctx;w->selected=selected;w->data=data;return true;
}
static bool transfer(void *ctx, uint8_t out, uint8_t *in) {
    wire *w=ctx;assert(w->selected && w->count<sizeof(w->bytes));
    const unsigned n=w->count++;w->bytes[n]=out;w->modes[n]=(uint8_t)w->data;
    if(n==w->fail_at)return false;
    const uint8_t answer[]={0,0,0,0,0,0,0,0,0,0,0,0xee,0xaa,0xbe};
    *in=answer[n];return true;
}
typedef struct {bool selected,data;unsigned count,fail_at;uint8_t prefix[12];} row_wire;
static bool row_lines(void *ctx,bool selected,bool data){row_wire *w=ctx;w->selected=selected;w->data=data;return true;}
static bool row_transfer(void *ctx,uint8_t out,uint8_t *in){
    row_wire *w=ctx;assert(w->selected);unsigned n=w->count++;
    if(n<sizeof(w->prefix))w->prefix[n]=out;
    if(n==w->fail_at)return false;
    if(n<12){*in=0;return true;}
    const unsigned q=(n-12)/2,component=(n-12)%2;
    assert(q<320 && out==0 && w->data);
    const uint16_t value=(uint16_t)(((q&31u)<<11)|((q&63u)<<5)|((q+7)&31u));
    *in=(uint8_t)(component ? value : value>>8);
    return true;
}
int main(void) {
    wire w={0};w.fail_at=99;
    picocalc_lcd_read_bus bus={&w,lines,transfer};uint8_t rgb[3]={0};
    assert(picocalc_lcd_read_pixel(&bus,319,479,rgb));
    const uint8_t expected[]={0x2a,1,63,1,63,0x2b,1,223,1,223,0x2e,0,0,0};
    const uint8_t modes[]={0,1,1,1,1,0,1,1,1,1,0,1,1,1};
    assert(w.count==sizeof(expected) && !w.selected && w.data);
    assert(!memcmp(w.bytes,expected,sizeof(expected)) && !memcmp(w.modes,modes,sizeof(modes)));
    assert(rgb[0]==0xac && rgb[1]==0x54 && rgb[2]==0xf4);
    assert(!picocalc_lcd_read_pixel(&bus,320,0,rgb) && !picocalc_lcd_read_pixel(&bus,0,480,rgb));
    for(unsigned i=0;i<sizeof(expected);++i) {
        memset(&w,0,sizeof(w));w.fail_at=i;
        assert(!picocalc_lcd_read_pixel(&bus,0,0,rgb));
        assert(!w.selected);
    }
    row_wire rw={0};rw.fail_at=2000;uint8_t row[640];picocalc_lcd_read_bus wide={&rw,row_lines,row_transfer};
    assert(picocalc_lcd_read_row565(&wide,479,row) && !rw.selected && rw.count==12+320*2);
    const uint8_t prefix[]={0x2a,0,0,1,63,0x2b,1,223,1,223,0x2e,0};
    assert(!memcmp(rw.prefix,prefix,sizeof(prefix)));
    for(unsigned i=0;i<320;++i){const uint16_t want=(uint16_t)(((i&31u)<<11)|((i&63u)<<5)|((i+7)&31u));
        assert(((uint16_t)row[2*i]|((uint16_t)row[2*i+1]<<8))==want);}
    memset(&rw,0,sizeof(rw));rw.fail_at=500;
    assert(!picocalc_lcd_read_row565(&wide,42,row) && !rw.selected);
    assert(!picocalc_lcd_read_row565(&wide,480,row));
    puts("LCD GRAM diagnostic: exact CASET/RASET/RAMRD, single-pixel/row reads and timeout cleanup PASS");
    return 0;
}
