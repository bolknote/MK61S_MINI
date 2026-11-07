#include "sd_multi_write.hpp"
#include "sd_crc.hpp"
#include "event_wait.hpp"
#include "lcd_update.hpp"
#include "lcd_chain.hpp"
#include "lcd_color.hpp"
#include "psram_stream.hpp"
#include "sleep_clock_lease.hpp"
#include <array>
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
namespace {
struct Clocks {
 static inline uint32_t first=0,second=0;
 static uint32_t read0(){return first;}
 static uint32_t read1(){return second;}
 static void set0(uint32_t bits){first|=bits;}
 static void set1(uint32_t bits){second|=bits;}
 static void clear0(uint32_t bits){first&=~bits;}
 static void clear1(uint32_t bits){second&=~bits;}
};
void sleep_clocks(){
 using picocalc::SleepClockLease;
 Clocks::first=0x100;Clocks::second=0x200;
 {
  SleepClockLease<Clocks> transport(3,12);assert(transport.temporary());
  assert(Clocks::first==0x103 && Clocks::second==0x20C);
  {SleepClockLease<Clocks> nested(3,12);assert(!nested.temporary());}
  assert(Clocks::first==0x103 && Clocks::second==0x20C);
  // Even with queue and DMA complete, WFE must keep the final UART bit's
  // clocks running. The sleeping model advances only with those clocks.
  unsigned bits=10;
  assert(picocalc::event_wait([&]{return bits!=0;},[]{},[&]{
   assert((Clocks::first&3)==3 && (Clocks::second&12)==12);--bits;
  })==10);
  Clocks::first|=0x400;Clocks::second|=0x800;
 }
 assert(Clocks::first==0x500 && Clocks::second==0xA00);
 Clocks::first=Clocks::second=UINT32_MAX;
 {SleepClockLease<Clocks> awake(3,12);assert(!awake.temporary());}
 assert(Clocks::first==UINT32_MAX && Clocks::second==UINT32_MAX);
}
struct Bus {
 u8 response=0;int fail_data=-1,reject_data=-1,fail_wait=-1;
 unsigned blocks=0,waits=0,crc_bytes=0,stops=0,starts=0;bool closed=false;
 u16 current_crc=0;std::vector<u8> payload;
 u8 command(u8 op,u32 address){assert(op==25 && address==123);return response;}
 void deselect(){closed=true;}
 u8 byte(u8 value){
  if(crc_bytes){assert(value==(crc_bytes==2?(u8)(current_crc>>8):(u8)current_crc));--crc_bytes;return 0xFF;}
  if(current_crc){assert(value==0xFF);current_crc=0;return (int)blocks-1==reject_data?0x0B:5;}
  if(value==0xFC)++starts;
  else if(value==0xFD)++stops;
  else assert(value==0xFF);
  return 0xFF;
 }
 bool data(const u8* source,u16& crc){
  assert(starts==blocks+1);const unsigned index=blocks++;
  if((int)index==fail_data)return false;
  payload.insert(payload.end(),source,source+512);
  crc=picocalc::sd::crc16(source,512);assert(crc);current_crc=crc;crc_bytes=2;return true;
 }
 bool wait(){return (int)waits++!=fail_wait;}
};
void sd_test(){
 using picocalc::sd::MultiWriteResult;using picocalc::sd::multi_write;
 std::array<u8,3*512> data{};for(unsigned i=0;i<data.size();++i)data[i]=(u8)(i*73+i/11);
 Bus good;assert(multi_write(good,123,data.data(),3)==MultiWriteResult::OK);
 assert(good.closed && good.blocks==3 && good.starts==3 && good.stops==1 && good.waits==4);
 assert(good.payload==std::vector<u8>(data.begin(),data.end()));
 Bus unsupported;unsupported.response=4;assert(multi_write(unsupported,123,data.data(),3)==MultiWriteResult::UNSUPPORTED);
 assert(unsupported.closed && !unsupported.blocks && !unsupported.stops);
 Bus command_error;command_error.response=0xFF;assert(multi_write(command_error,123,data.data(),3)==MultiWriteResult::ERROR);
 assert(command_error.closed && !command_error.blocks && !command_error.stops);
 for(int at=0;at<3;++at){
  Bus crc;crc.reject_data=at;assert(multi_write(crc,123,data.data(),3)==MultiWriteResult::ERROR);
  assert(crc.closed && crc.blocks==(unsigned)at+1 && crc.stops==1);
  Bus partial;partial.fail_data=at;assert(multi_write(partial,123,data.data(),3)==MultiWriteResult::INCOMPLETE);
  assert(partial.closed && partial.blocks==(unsigned)at+1 && !partial.stops);
  Bus busy;busy.fail_wait=at;assert(multi_write(busy,123,data.data(),3)==MultiWriteResult::INCOMPLETE);
  assert(busy.closed && busy.blocks==(unsigned)at+1 && !busy.stops);
 }
 Bus stop;stop.fail_wait=3;assert(multi_write(stop,123,data.data(),3)==MultiWriteResult::INCOMPLETE);
 assert(stop.closed && stop.stops==1);
}
void events(){
 unsigned clear=0,sleep=0;bool pending=false;
 auto clean=[&]{++clear;};auto wait=[&]{++sleep;pending=false;};
 assert(picocalc::event_wait([&]{return pending;},clean,wait)==0 && !clear && !sleep);
 // Completion before clearing a stale event: the persistent predicate keeps
 // the waiter from sleeping after its only notification has been cleared.
 pending=true;assert(picocalc::event_wait([&]{return pending;},[&]{++clear;pending=false;},wait)==0);
 assert(!sleep);
 // Completion immediately after the final predicate load: its event must
 // remain latched and the following sleep must consume it immediately.
 pending=true;bool event=false;unsigned checks=0;
 assert(picocalc::event_wait([&]{const bool old=pending;if(++checks==2){pending=false;event=true;}return old;},
  [&]{event=false;},[&]{assert(event);event=false;++sleep;})==1);
 pending=true;unsigned spurious=0;
 assert(picocalc::event_wait([&]{return pending;},[]{},[&]{if(++spurious==3)pending=false;})==3);
 // Empty software queue is insufficient for flush while the final byte is
 // still in the UART FIFO/shift register.
 bool queue=true,dma=true,wire=true;unsigned phases=0;
 assert(picocalc::event_wait([&]{return queue||dma||wire;},[]{},[&]{
  if(phases==0)queue=false;else if(phases==1)dma=false;else wire=false;++phases;
 })==3);
}
void pixels(){
 std::array<u8,picocalc::lcd::BYTES> frame{};std::array<u8,640+16> output{};
 for(unsigned byte=0;byte<256;++byte){
  std::fill(frame.begin(),frame.end(),(u8)byte);
  for(auto rect:{picocalc::lcd::Rect{0,0,320,1},picocalc::lcd::Rect{8,319,304,1},picocalc::lcd::Rect{3,8,311,1}}){
   output.fill(0xA7);picocalc::lcd::scanline(frame.data(),rect,0,output.data()+8);
   for(unsigned x=0;x<rect.width;++x){const u8 expected=byte&(128U>>((rect.x+x)%8))?0xFF:0;
    assert(output[8+x*2]==expected && output[8+x*2+1]==expected);}
   for(unsigned i=0;i<8;++i)assert(output[i]==0xA7);
   for(unsigned i=8+rect.width*2;i<output.size();++i)assert(output[i]==0xA7);
  }
 }
}
void qpi_completion(){
 using picocalc::psram::stream_idle;
 constexpr unsigned ready=18;
 for(unsigned step=1;step<=64;++step)for(unsigned phase=0;phase<9;++phase){
  bool completed=false;
  for(unsigned sample=0;sample<9;++sample){
   // The PC spends eight cycles on one idle address and one on the other.
   // Sampling at a multiple of nine must work at EVERY starting phase.
   const unsigned pc=(phase+step*sample)%9?ready+1:ready;
   completed|=stream_idle(ready,pc,true,true,true);
  }
  assert(completed);
 }
 assert(stream_idle(ready,ready,false,true,true));
 assert(!stream_idle(ready,ready+1,false,true,true));
 assert(!stream_idle(ready,ready+2,true,true,true));
 assert(!stream_idle(ready,ready,true,false,true));
 assert(!stream_idle(ready,ready+1,true,false,true));
 assert(!stream_idle(ready,ready,true,true,false));
 assert(!stream_idle(ready,ready+1,true,true,false));
}
void color_strips() {
 using namespace picocalc::lcd;
 unsigned cases=0;
 for(unsigned format:{MK61_COLOR_TILE1,MK61_COLOR_TILE8,MK61_COLOR_INDEX4})
  for(unsigned width:{8U,24U,127U,256U,319U,320U})
   for(unsigned height:{8U,16U,79U,192U}) {
    if(format!=MK61_COLOR_INDEX4 && ((width|height)&7U))continue;
    const unsigned pixel_bytes=format==MK61_COLOR_INDEX4?(width+1)/2*height:width*height/8;
    const unsigned tile_bytes=format==MK61_COLOR_INDEX4?0:width*height/64*(format==MK61_COLOR_TILE8?2:1);
    if(pixel_bytes+tile_bytes>MK61_COLOR_SNAPSHOT_BYTES)continue;
    std::vector<u8> bits(pixel_bytes),tiles(tile_bytes);
    for(unsigned i=0;i<bits.size();++i)bits[i]=(u8)(i*73+i/11);
    for(unsigned i=0;i<tiles.size();++i)tiles[i]=(u8)((i*31+i/7)%(format==MK61_COLOR_TILE8?64:256));
    mk61_service_color_frame f{};f.pixels=bits.data();f.tiles=tile_bytes?tiles.data():nullptr;
    f.pixel_bytes=pixel_bytes;f.tile_bytes=tile_bytes;f.x=(320-width)/2;f.y=(320-height)/2;
    f.width=width;f.height=height;f.format=format;
    std::array<u16,64> palette;for(unsigned i=0;i<64;++i)palette[i]=(u16)(i*971+0x1234);
    for(unsigned i=0;i<16;++i)f.palette[i]=palette[i];
    assert(valid_color(f));
    for(unsigned trim:{0U,1U,3U}) {
     Rect r{(u16)(f.x+trim),(u16)(f.y+trim),(u16)(width-trim),(u16)(height-trim)};
     Stream stream;stream.reset(r);std::array<u16,STRIP_ROWS*WIDTH+2> block;block.fill(0xA77A);
     unsigned sent=0;
     for(unsigned i=0;i<stream.count;++i) {
      const auto segment=Stream::prepare(r,i,block.data()+1,[&](unsigned row,u16* out){color_scanline(f,r,row,out,palette.data());});
      const auto* source=(const u16*)segment.source;
      for(unsigned n=0;n<segment.count;++n) {
       const unsigned x=trim+(sent+n)%r.width,y=trim+(sent+n)/r.width;
       unsigned index=0;
       if(format==MK61_COLOR_INDEX4)index=(bits[y*((width+1)/2)+x/2]>>((x&1)?0:4))&15;
       else {
        const bool ink=bits[y*(width/8)+x/8]&(128U>>(x&7));
        const unsigned tile=(y/8)*(width/8)+x/8;
        index=format==MK61_COLOR_TILE8?tiles[tile*2+ink]:(tiles[tile]>>(ink?0:4))&15;
       }
       assert(source[n]==palette[index]);
      }
      sent+=segment.count;assert(block.front()==0xA77A && block.back()==0xA77A);
     }
     assert(sent==r.width*r.height && !stream.segments[stream.count].source);++cases;
    }
   }
 std::printf("LCD color strips: %u TILE1/TILE8/odd INDEX4 cases, offset windows, short tails and guard words PASS\n",cases);
}
}
int main(){sd_test();events();pixels();qpi_completion();sleep_clocks();color_strips();
 using namespace picocalc::lcd;
 std::array<uint8_t,BYTES> frame{};
 for(unsigned i=0;i<BYTES;++i)frame[i]=(uint8_t)(i*73+i/11);
 for(unsigned width:{1U,7U,8U,24U,319U,320U})for(unsigned height:{1U,2U,3U,4U,5U,319U,320U})
  for(unsigned delay=1;delay<=7;++delay) {
   Rect rect{0,0,(uint16_t)width,(uint16_t)height};Stream stream;stream.reset(rect);
   std::array<uint16_t,STRIP_ROWS*WIDTH+2> a,b;a.fill(0xA77A);b.fill(0xA77A);
   auto prepare=[&](unsigned i){stream.segments[i]=Stream::prepare(frame.data(),rect,i,i&1?b.data()+1:a.data()+1);};
   unsigned prepared=stream.count<2?stream.count:2;
   for(unsigned i=0;i<prepared;++i)prepare(i);
   unsigned loaded=0,transferred=0,tick=0;bool stopped=false;
   while(transferred<width*height || !stopped) {
    assert(++tick<100000);
    if(!stopped) {
     const auto segment=stream.segments[loaded++];
     if(!segment.count || !segment.source) stopped=true;
     else {
      const auto* source=(const uint16_t*)segment.source;
      for(unsigned n=0;n<segment.count;++n) {
       const unsigned x=(transferred+n)%width,y=(transferred+n)/width;
       const bool ink=frame[y*STRIDE+x/8]&(0x80U>>(x%8));
       assert(source[n]==(ink?0xFFFF:0));
      }
      transferred+=segment.count;
     }
    }
    // Delay the producer beyond both prepared strips: the null descriptor
    // must stop, and resuming at the drained wire cursor must not duplicate it.
    if(tick%delay==0 && prepared<stream.count && loaded>=prepared) prepare(prepared++);
    const unsigned next=Stream::next(transferred,width);
    if(stopped && next<prepared && loaded>=next+1) {loaded=next;stopped=false;}
   }
   assert(transferred==width*height && loaded==stream.count+1);
   assert(a.front()==0xA77A && a.back()==0xA77A && b.front()==0xA77A && b.back()==0xA77A);
  }
 std::puts("CMD25, UART events/clocks, RGB565 bounded streaming DMA/null-stop/resume and QPI tests PASS");}
