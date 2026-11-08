#include "lcd_color.hpp"
#include "pcm_queue.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <vector>
#include <random>

using namespace picocalc::lcd;
static uint16_t* progressive_line;
static unsigned progressive_width,progressive_seen,progressive_max;
static void observe_expansion() {
    unsigned end=progressive_seen;
    while(end<progressive_width && progressive_line[end]!=0xDEAD)++end;
    assert(end>progressive_seen);
    progressive_max=std::max(progressive_max,end-progressive_seen);progressive_seen=end;
}
static void bounded_expansion() {
    for(unsigned format:{MK61_COLOR_TILE1,MK61_COLOR_TILE8,MK61_COLOR_INDEX4}) {
        mk61_service_color_frame frame{};frame.width=320;frame.height=8;frame.format=format;
        frame.x=0;frame.y=16;frame.pixel_bytes=format==MK61_COLOR_INDEX4?1280:320;
        frame.tile_bytes=format==MK61_COLOR_TILE8?80:format==MK61_COLOR_TILE1?40:0;
        std::vector<uint8_t> pixels(frame.pixel_bytes,0x16),tiles(frame.tile_bytes,1);
        frame.pixels=pixels.data();frame.tiles=tiles.empty()?nullptr:tiles.data();
        for(unsigned i=0;i<16;++i)frame.palette[i]=uint16_t(i+1);
        uint16_t palette[64];for(unsigned i=0;i<64;++i)palette[i]=uint16_t(i+1);
        uint16_t line[320];progressive_line=line;
        for(unsigned first:{0u,3u,63u,65u})for(unsigned width:{1u,63u,128u,255u}) {
            if(first+width>320)continue;
            std::fill(std::begin(line),std::end(line),uint16_t(0xDEAD));
            progressive_width=width;progressive_seen=progressive_max=0;
            const Rect r{uint16_t(first),16,uint16_t(width),1};
            color_scanline(frame,r,0,line,palette,observe_expansion);
            progressive_max=std::max(progressive_max,width-progressive_seen);
            assert(progressive_max<=64);
            for(unsigned x=0;x<width;++x)assert(line[x]==color_pixel(frame,first+x,0,palette));
        }
    }
    puts("LCD expansion: unchanged pixels and at most 64 pixels between transport service points PASS");
}
static void aligned_and_unaligned_tiles() {
    for(unsigned format:{MK61_COLOR_TILE1,MK61_COLOR_TILE8})for(unsigned width:{8U,24U,32U,256U,320U})
      for(unsigned offset=0;offset<2;++offset) {
        mk61_service_color_frame before{},after{};
        after.width=(uint16_t)width;after.height=24;after.format=format;
        after.pixel_bytes=width*3;after.tile_bytes=width/8*3*(format==MK61_COLOR_TILE8?2:1);
        std::vector<uint8_t> old_pixels(after.pixel_bytes+4),new_pixels(after.pixel_bytes+4),
            old_tiles(after.tile_bytes+4),new_tiles(after.tile_bytes+4);
        after.pixels=new_pixels.data()+offset;after.tiles=new_tiles.data()+offset;
        before=after;before.pixels=old_pixels.data();before.tiles=old_tiles.data();
        assert(valid_color(before) && valid_color(after));Update update;
        plan_color(update,before,after,false);assert(!update.count && !update.bytes);
        for(unsigned row=0;row<24;++row)for(unsigned column=0;column<width/8;++column) {
            new_pixels[offset+row*(width/8)+column]=0x80;
            plan_color(update,before,after,false);
            assert(update.count==1 && update.rectangles[0].x==column*8 && update.rectangles[0].y==(row/8)*8 &&
                   update.rectangles[0].width==8 && update.rectangles[0].height==8 && update.bytes==128);
            new_pixels[offset+row*(width/8)+column]=0;
        }
        for(unsigned i=0;i<after.tile_bytes;++i) {
            new_tiles[offset+i]=1;plan_color(update,before,after,false);
            const unsigned tile=i/(format==MK61_COLOR_TILE8?2:1);
            assert(update.count==1 && update.rectangles[0].x==(tile%(width/8))*8 &&
                   update.rectangles[0].y==(tile/(width/8))*8 && update.bytes==128);
            new_tiles[offset+i]=0;
        }
      }
    puts("LCD tiled plans: aligned/unaligned sources, 1/3/4/32/40-byte strides, every pixel row and attribute byte PASS");
}
static void randomized_color_plans() {
    std::mt19937 random(0xC010U);unsigned frames=0;
    for(unsigned format:{MK61_COLOR_TILE1,MK61_COLOR_TILE8,MK61_COLOR_INDEX4}) {
        mk61_service_color_frame next{},old{};
        next.x=17;next.y=33;next.width=format==MK61_COLOR_INDEX4?253:256;
        next.height=format==MK61_COLOR_INDEX4?93:192;next.format=format;
        next.pixel_bytes=format==MK61_COLOR_INDEX4?((next.width+1)/2)*next.height:next.width*next.height/8;
        next.tile_bytes=format==MK61_COLOR_INDEX4?0:next.width*next.height/64*(format==MK61_COLOR_TILE8?2:1);
        std::vector<uint8_t> pixels(next.pixel_bytes),tiles(next.tile_bytes),storage(MK61_COLOR_SNAPSHOT_BYTES);
        std::vector<uint16_t> lcd(WIDTH*HEIGHT,0xBEEF);uint16_t palette64[64],line[WIDTH];
        next.pixels=pixels.data();next.tiles=tiles.empty()?nullptr:tiles.data();
        for(unsigned i=0;i<16;++i) next.palette[i]=(uint16_t)(i*3137);
        for(unsigned i=0;i<64;++i) palette64[i]=(uint16_t)(i*919);
        for(unsigned iteration=0;iteration<180;++iteration) {
            // Sparse sprites, fragmented bands and fully animated frames.
            const unsigned changes=iteration%19==0?(unsigned)pixels.size():iteration%100;
            for(unsigned i=0;i<changes;++i) {
                pixels[random()%pixels.size()]=(uint8_t)random();
                if(!tiles.empty()) tiles[random()%tiles.size()]=(uint8_t)(random()%(format==MK61_COLOR_TILE8?64:256));
            }
            if(iteration%31==0) next.palette[iteration%16]^=0xFFFF;
            assert(valid_color(next));Update update;
            plan_color(update,old,next,iteration==0);
            assert(update.count<=Update::CAPACITY && update.bytes<=next.width*next.height*2);
            unsigned bytes=0;
            for(unsigned i=0;i<update.count;++i) {
                const auto r=update.rectangles[i];bytes+=r.width*r.height*2;
                assert(r.width && r.height && r.x>=next.x && r.y>=next.y &&
                    r.x+r.width<=next.x+next.width && r.y+r.height<=next.y+next.height);
                for(unsigned y=0;y<r.height;++y) {
                    color_scanline(next,r,y,line,palette64);
                    for(unsigned x=0;x<r.width;++x) lcd[(r.y+y)*WIDTH+r.x+x]=line[x];
                }
            }
            assert(bytes==update.bytes);
            for(unsigned y=0;y<HEIGHT;++y) for(unsigned x=0;x<WIDTH;++x) {
                if(x>=next.x && x<next.x+next.width && y>=next.y && y<next.y+next.height)
                    assert(lcd[y*WIDTH+x]==color_pixel(next,x-next.x,y-next.y,palette64));
                else assert(lcd[y*WIDTH+x]==0xBEEF);
            }
            copy_color(old,next,storage.data());++frames;
        }
    }
    std::printf("LCD randomized reconstruction: %u TILE1/TILE8/odd INDEX4 frames PASS\n",frames);
}
int main() {
    bounded_expansion();
    aligned_and_unaligned_tiles();
    randomized_color_plans();
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
    // Two opposite-edge sprites must not transmit their unchanged middle.
    bits[0]=bits[31]=0x80;verify();
    assert(update.count==2 && update.bytes==2*8*8*2);
    std::printf("LCD sparse edges: 4096 -> %u pixel bytes, %u windows\n",update.bytes,update.count);
    std::fill(bits.begin(),bits.end(),0);verify();
    for(unsigned y=0;y<192;++y) bits[y*32]=bits[y*32+31]=0x80;
    verify();assert(update.count==2 && update.bytes==2*8*192*2);
    std::printf("LCD vertical edges: 98304 -> %u pixel bytes, %u windows\n",update.bytes,update.count);
    // A short gap is cheaper than an extra command/DMA window.
    std::fill(bits.begin(),bits.end(),0);verify();bits[0]=bits[2]=0x80;verify();
    assert(update.count==1 && update.rectangles[0].width==24 && update.bytes==24*8*2);
    // More than 32 separate runs must retain every change within the budget.
    std::fill(bits.begin(),bits.end(),0);verify();
    for(unsigned y=0;y<192;y+=8) {
        bits[y*32+(y/8%2)]=0x80;bits[y*32+31-(y/8%2)]=0x80;
    }
    verify();assert(update.count<=Update::CAPACITY && update.bytes<256*192*2);
    std::printf("LCD 48 staggered runs: %u pixel bytes, %u windows\n",update.bytes,update.count);
    // Dense changes favor one full frame rather than many expensive windows.
    std::fill(bits.begin(),bits.end(),0);verify();
    for(unsigned y=0;y<192;y+=8) for(unsigned x=0;x<32;++x)
        if((x+y/8)%2) bits[y*32+x]=0x80;
    verify();assert(update.count==1 && update.bytes==256*192*2);
    std::printf("LCD dense checkerboard: %u pixel bytes, %u window\n",update.bytes,update.count);
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
    uint8_t indexed_saved[4];copy_color(old,indexed,indexed_saved);
    packed[1]^=0x10;plan_color(update,old,indexed,false);
    assert(update.count==1 && update.bytes==12 && update.rectangles[0].width==3 && update.rectangles[0].height==2);
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
