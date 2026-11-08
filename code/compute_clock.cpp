#include "compute_clock.hpp"
#if MK61_COMPUTE_CLOCK_SUPPORTED
#include "loadable_app_services.h"

namespace compute_clock {
namespace {
Demand demand;
Owner* owner=nullptr;
uint16_t generation=0;
uint8_t profile=0;
bool fast=false;
bool configured=false;
void apply(uint32_t now) {
  const bool wanted=demand.wanted(now);
  if(wanted!=fast && backend::set_fast(wanted))fast=wanted;
}
}
uint8_t active_profile(){return profile;}
uint32_t frequency_hz(){return backend::hz();}
bool configure(uint8_t value) {
  if(configured)return value==profile;
  if(demand.users || demand.waits || demand.holds || owner ||
     value!=normalize(platform(),value) || !backend::configure(value))return false;
  profile=value;fast=false;demand.cooling=false;configured=true;return true;
}
void poll(uint32_t now){if(profile)apply(now);}
bool acquire() {
  if(!profile || !demand.acquire())return false;
  apply(backend::now_ms());return true;
}
void release(){demand.release(1,backend::now_ms());}
bool pause() {
  if(!profile || demand.waits==UINT16_MAX)return false;
  ++demand.waits;apply(backend::now_ms());return true;
}
void resume(){if(demand.waits)--demand.waits;apply(backend::now_ms());}
void audio_floor(bool active) {
  if(!profile)return;
  demand.holds=active?1:0;
  if(!active && !demand.users){demand.cooling=true;demand.release_at=backend::now_ms()+4;}
  apply(backend::now_ms());
}
Owner::Owner(bool join):previous(owner),generation(0),depth(0) {
  if(join && owner)return;
  generation=++compute_clock::generation;
  if(!generation)generation=++compute_clock::generation;
  owner=this;
}
Owner::~Owner(){if(generation){demand.release(depth,backend::now_ms());owner=previous;}}
uint32_t service(uint32_t operation,uint32_t token) {
  if(operation!=MK61_COMPUTE_END && token)return 0;
  switch(operation) {
    case MK61_COMPUTE_PROBE:return MK61_COMPUTE_MAGIC;
    case MK61_COMPUTE_HZ:return frequency_hz();
    case MK61_COMPUTE_BEGIN:
      if(token || !owner || owner->depth==UINT16_MAX || !demand.acquire())return 0;
      ++owner->depth;
      if(profile)apply(backend::now_ms());
      return uint32_t(owner->generation)<<16 | owner->depth;
    case MK61_COMPUTE_END:
      if(!owner || !owner->depth || uint16_t(token>>16)!=owner->generation ||
         uint16_t(token)!=owner->depth)return 0;
      --owner->depth;demand.release(1,backend::now_ms());return 1;
    default:return 0;
  }
}
}
#endif
