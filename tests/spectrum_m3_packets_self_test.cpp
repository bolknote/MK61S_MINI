#include "psg_packets.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <vector>
using namespace picocalc::psg_packets;
struct Producer {
    std::array<uint8_t,4096> events{};
    std::array<std::array<uint8_t,BODY>,2> psg{};
    uint32_t read=0,write=0,produced=0,time=0;
    uint8_t running=1,dac[3]={0,128,128};
    int32_t dc_in=0,dc_out=0;
    mk61_service_audio_psg request{};
    Producer(unsigned capacity=512) {
        request.local={[](void*)->uint32_t{return 0;},this,25000,100};request.module_path="AY.S3M";
        request.psg[0]=psg[0].data();request.psg[1]=psg[1].data();request.psg_bytes=BODY;request.extensions=7;
        request.events=events.data();request.event_capacity=capacity;request.read=&read;request.write=&write;
        request.produced=&produced;request.time=&time;request.running=&running;request.dac=dac;
        request.dc_input=&dc_in;request.dc_output=&dc_out;assert(valid(request));
    }
    void add(uint32_t at,unsigned device,unsigned reg,unsigned value) {
        assert(write-read<request.event_capacity);
        auto* e=events.data()+(write&(request.event_capacity-1))*8;
        put32(e,at);e[4]=uint8_t(device);e[5]=uint8_t(reg);e[6]=uint8_t(value);++write;
    }
};
int main() {
    std::array<uint8_t,512> packet{};
    { // Sparse AY blocks, repeated envelopes, exact edges, past/future
      // events and unchanged DAC writes, including both counter wraps.
      uint32_t random=12345;
      const auto rnd=[&](){random^=random<<13;random^=random>>17;random^=random<<5;return random;};
      for(unsigned trial=0;trial<10000;++trial) {
          Producer p;p.time=rnd();p.read=p.write=rnd();
          const uint32_t start=p.time,first=p.read;const unsigned count=1+rnd()%120;
          uint32_t at=start-20;
          for(unsigned i=0,n=rnd()%80;i<n;++i) {
              at+=rnd()%600;const unsigned device=rnd()%5;
              p.add(at,device,rnd()%16,device<2?rnd():p.dac[device-2]);
          }
          p.produced=start+count*140;
          const int bytes=prepare(p.request,packet.data(),count,count);
          assert(bytes>=11 && packet[5]==count && !packet[7] && !std::memcmp(packet.data()+8,p.dac,3));
          uint32_t cursor=first;unsigned offset=11;
          for(unsigned sample=0;sample<count;++sample)while(cursor!=p.write) {
              const auto* e=event(p.request,cursor);
              if(int32_t(get32(e)-(start+(sample+1)*140))>0)break;
              if(e[4]<2) {
                  assert(offset+3<=unsigned(bytes) && packet[offset++]==sample);
                  assert(packet[offset++]==e[4]*16+e[5] && packet[offset++]==e[6]);
              }
              ++cursor;
          }
          assert(offset==unsigned(bytes) && p.read==cursor && p.time==p.produced);
      } }
    { // Independent per-sample oracle for the event/run DAC encoder.
      uint32_t random=987654321;
      const auto rnd=[&](){random^=random<<13;random^=random>>17;random^=random<<5;return random;};
      for(unsigned trial=0;trial<10000;++trial) {
          Producer p;p.time=rnd();p.read=p.write=rnd();
          for(auto& value:p.dac)value=uint8_t(rnd());p.dac[0]&=1;
          const uint32_t start=p.time,first=p.read;const unsigned count=1+rnd()%120;
          uint32_t at=start-200;
          for(unsigned i=0,n=rnd()%80;i<n;++i) {
              at+=rnd()%600;const unsigned device=rnd()%5;
              p.add(at,device,rnd()%16,device==2?rnd()&1:rnd());
          }
          p.produced=start+count*140;uint32_t cursor=first;
          std::array<std::array<uint8_t,3>,120> samples{};
          std::vector<uint8_t> ay;uint8_t dac[3];std::memcpy(dac,p.dac,3);
          for(unsigned sample=0;sample<count;++sample) {
              while(cursor!=p.write) {
                  const auto* e=event(p.request,cursor);
                  if(int32_t(get32(e)-(start+(sample+1)*140))>0)break;
                  if(e[4]<2){ay.push_back(uint8_t(sample));ay.push_back(uint8_t(e[4]*16+e[5]));ay.push_back(e[6]);}
                  else dac[e[4]-2]=e[6];
                  ++cursor;
              }
              std::memcpy(samples[sample].data(),dac,3);
          }
          unsigned flags=0;
          for(unsigned sample=1;sample<count;++sample)for(unsigned d=0;d<3;++d)
              if(samples[sample][d]!=samples[0][d])flags|=1u<<d;
          std::vector<uint8_t> expected(11);put32(expected.data(),MAGIC);
          expected[4]=1;expected[5]=uint8_t(count);expected[6]=7;expected[7]=uint8_t(flags);
          std::memcpy(expected.data()+8,samples[0].data(),3);
          if(flags&1) {
              const auto offset=expected.size();expected.resize(offset+(count+7)/8);
              for(unsigned sample=0;sample<count;++sample)expected[offset+sample/8]|=uint8_t(samples[sample][0]<<(sample&7));
          }
          for(unsigned d=1;d<3;++d)if(flags&(1u<<d))for(unsigned sample=0;sample<count;++sample)
              expected.push_back(samples[sample][d]);
          expected.insert(expected.end(),ay.begin(),ay.end());assert(expected.size()<=512);
          const int bytes=prepare(p.request,packet.data(),count,count);
          assert(bytes==int(expected.size()) && !std::memcmp(packet.data(),expected.data(),expected.size()));
          assert(p.read==cursor && p.time==p.produced && !std::memcmp(p.dac,dac,3));
      } }
    { Producer p;p.produced=120*140;p.running=0;assert(!prepare(p.request,packet.data()) && !p.read && !p.time);
      p.running=1;p.produced=119*140;assert(!prepare(p.request,packet.data()) && !p.time);
      p.produced=120*140;assert(prepare(p.request,packet.data())==11);
      assert(packet[5]==120 && !packet[7] && packet[8]==0 && packet[9]==128 && packet[10]==128 && p.time==120*140); }
    { Producer p;p.time=0xfffffff0u;p.read=p.write=0xfffffffdu;const uint32_t start=p.time;
      for(unsigned i=0;i<120;++i) {
          const uint32_t at=start+(i+1)*140;
          p.add(at,2,0,i&1);p.add(at,3,0,i);p.add(at,4,0,255-i);
          if(i%10==0){p.add(at,0,13,10);p.add(at,0,13,10);}
      }
      p.produced=start+120*140;
      assert(prepare(p.request,packet.data())==11+15+120+120+24*3);
      assert(packet[5]==120 && packet[7]==7 && packet[8]==0 && packet[9]==0 && packet[10]==255);
      for(unsigned i=0;i<120;++i) {
          assert(((packet[11+i/8]>>(i&7))&1)==(i&1));
          assert(packet[26+i]==i && packet[146+i]==255-i);
      }
      for(unsigned i=0;i<24;++i){const auto* e=packet.data()+266+i*3;assert(e[0]==(i/2)*10 && e[1]==13 && e[2]==10);}
      assert(p.read==p.write && p.time==p.produced && p.dac[0]==1 && p.dac[1]==119 && p.dac[2]==136); }
    { Producer p(256);for(unsigned i=0;i<256;++i)p.add((i+1)*16,1,i&15,i);
      p.produced=256*16;const int n=prepare(p.request,packet.data());
      assert(n>11 && n<=512 && packet[5]>0 && packet[5]<120 && p.read>0 && p.read<256);
      assert(p.time==uint32_t(packet[5])*140);
      for(unsigned at=11;at<unsigned(n);at+=3)assert(packet[at]<packet[5] && packet[at+1]>=16 && packet[at+1]<32); }
    { Producer p;p.add(140,3,0,37);p.add(3500,3,0,250);p.produced=120*140;
      assert(prepare(p.request,packet.data())==131 && packet[7]==2 && packet[9]==37);
      assert(packet[11]==37 && packet[34]==37 && packet[35]==250 && p.dac[1]==250); }
    { Producer p;p.produced=120*140;p.add(1,5,0,0);
      assert(prepare(p.request,packet.data())==-1 && p.time==0 && p.read==0); }
    { Producer p;
      for(unsigned i=0;i<BODY;++i){p.psg[0][i]=uint8_t(i);p.psg[1][i]=uint8_t(255-i);}
      p.dc_in=-11000;p.dc_out=12345;p.dac[0]=1;
      assert(config(p.request,packet.data())==STATE && get32(packet.data())==MAGIC && !get32(packet.data()+4));
      put32(packet.data(),STATE_MAGIC);put32(packet.data()+4,BODY);
      const auto old=p.psg;p.psg[0].fill(0);p.psg[1].fill(0);p.dc_in=p.dc_out=0;p.dac[0]=0;
      assert(restore(p.request,packet.data(),STATE) && p.psg==old && p.dc_in==-11000 && p.dc_out==12345 && p.dac[0]==1);
      packet[0]^=1;assert(!restore(p.request,packet.data(),STATE) && p.psg==old);
      auto bad=p.request;bad.psg_bytes=131;assert(!valid(bad));bad=p.request;bad.event_capacity=255;assert(!valid(bad));
      bad=p.request;bad.read=reinterpret_cast<uint32_t*>(reinterpret_cast<uint8_t*>(&p.read)+1);assert(!valid(bad)); }
    std::puts("M3 PSG packets: sparse DAC compression, exact sample edges, repeated envelopes, ring/time wrap, full-ring liveness, bounds and state restore PASS");
}
