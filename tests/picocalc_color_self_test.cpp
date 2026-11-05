#include "lcd_color.hpp"
#include "pcm_queue.hpp"
#include <cassert>
#include <cstdio>
#include <vector>
#include <random>

using namespace picocalc::lcd;
int main() {
    std::vector<uint8_t> storage(MK61_COLOR_SNAPSHOT_BYTES),bits(6144),tiles(768);
    mk61_service_color_frame next{},old{};
    next.pixels=bits.data();next.tiles=tiles.data();next.pixel_bytes=6144;next.tile_bytes=768;
    next.width=256;next.height=192;next.x=32;next.y=64;next.format=MK61_COLOR_TILE1;
    for(unsigned i=0;i<16;++i) next.palette[i]=(uint16_t)(i*0x1111);
    assert(valid_color(next));Update update;
    std::vector<uint16_t> lcd(WIDTH*HEIGHT);
    std::mt19937 random(42);
    const auto verify=[&](bool force=false) {
        plan_color(update,old,next,force);
        assert(update.count<=Update::CAPACITY);
        unsigned bytes=0;uint16_t line[WIDTH];
        for(unsigned i=0;i<update.count;++i) {
            const auto r=update.rectangles[i];bytes+=r.width*r.height*2;
            assert(r.x>=next.x && r.y>=next.y && r.x+r.width<=next.x+next.width && r.y+r.height<=next.y+next.height);
            for(unsigned y=0;y<r.height;++y) {
                color_scanline(next,r,y,line);
                for(unsigned x=0;x<r.width;++x) lcd[(r.y+y)*WIDTH+r.x+x]=line[x];
            }
        }
        assert(bytes==update.bytes);
        for(unsigned y=0;y<next.height;++y) for(unsigned x=0;x<next.width;++x) {
            const uint8_t t=tiles[(y/8)*32+x/8];
            const unsigned color=(bits[y*32+x/8]&(128>>(x%8)))?t&15:t>>4;
            assert(lcd[(next.y+y)*WIDTH+next.x+x]==next.palette[color]);
        }
        copy_color(old,next,storage.data());
    };
    verify(true);assert(update.bytes==256*192*2);verify();assert(!update.count);
    for(unsigned iteration=0;iteration<80;++iteration) {
        for(unsigned j=0;j<iteration;++j) { bits[random()%bits.size()]=(uint8_t)random();tiles[random()%tiles.size()]=(uint8_t)random(); }
        if(iteration%7==0) next.palette[iteration%16]^=0xFFFF;
        verify();
    }
    // Snapshot owns every byte; mutating the APP source cannot race the LCD.
    const auto saved=storage;bits[1]^=255;tiles[2]^=255;assert(storage==saved);
    auto invalid=next;invalid.pixel_bytes--;assert(!valid_color(invalid));
    invalid=next;invalid.width=255;assert(!valid_color(invalid));
    invalid=next;invalid.x=65;assert(!valid_color(invalid));
    invalid=next;invalid.format=0xFFFF;assert(!valid_color(invalid));
    invalid=next;invalid.pixels=nullptr;assert(!valid_color(invalid));
    // Indexed mode supports odd widths; the trailing nibble is padding.
    uint8_t packed[]={0x12,0x30,0x45,0x60};mk61_service_color_frame indexed{};
    indexed.width=3;indexed.height=2;indexed.pixel_bytes=4;indexed.pixels=packed;
    for(unsigned i=0;i<16;++i) indexed.palette[i]=(uint16_t)(100+i);
    assert(valid_color(indexed));assert(color_pixel(indexed,0,0)==101 && color_pixel(indexed,2,1)==106);
    indexed.tiles=packed;assert(!valid_color(indexed));
    // 64-entry CLUT, two indices per 8x8 tile, and both dirty attribute bytes.
    std::vector<uint8_t> pairs(1536);uint16_t clut[64];
    for(unsigned i=0;i<64;++i) clut[i]=(uint16_t)(i*919);
    next.format=MK61_COLOR_TILE8;next.tiles=pairs.data();next.tile_bytes=1536;
    pairs[0]=39;pairs[1]=61;bits[0]=0x80;assert(valid_color(next));
    assert(color_pixel(next,0,0,clut)==clut[61] && color_pixel(next,1,0,clut)==clut[39]);
    copy_color(old,next,storage.data());pairs[0]=17;plan_color(update,old,next,false);
    assert(update.count==1 && update.rectangles[0].width==8 && update.rectangles[0].height==8);
    pairs[1]=64;assert(!valid_color(next));pairs[1]=63;assert(valid_color(next));
    next.tile_bytes=768;assert(!valid_color(next));
    picocalc::audio_stream::Queue queue;
    assert(!queue.pop() && !queue.underruns.load());
    int16_t input[1200];for(unsigned i=0;i<1200;++i) input[i]=(int16_t)(i-600);
    assert(queue.push(input,1200)==1024 && queue.queued()==1024);
    for(unsigned i=0;i<1024;++i) assert(queue.pop()==input[i]);
    assert(!queue.pop() && queue.underruns.load()==1);
    // Cursor wrap preserves every sample and distinguishes full/empty.
    queue.read.store(UINT32_MAX-50);queue.write.store(UINT32_MAX-50);
    for(unsigned n=0;n<3000;++n) {
        assert(queue.push(input,127)==127);
        for(unsigned i=0;i<127;++i) assert(queue.pop()==input[i]);
        assert(!queue.queued());
    }
    puts("PicoCalc color palette, snapshot ownership, dirty windows and bounds: PASS");
}
