#!/usr/bin/env python3
"""Run the production Pico DMA waits/CRC against a timed SDK endpoint."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SDK=r'''
#pragma once
#include <algorithm>
#include <cassert>
#include <cstdint>
namespace endpoint {
inline uint64_t now=0,complete[12]{};
inline bool stuck[12]{};
inline unsigned core=0,aborts=0,services=0,max_gap=0;
inline uint64_t serviced=0;
inline bool available=true,locked=false;
inline uint32_t accumulator=0;
inline uint32_t crc(const uint8_t* p,unsigned n) {
    uint32_t c=0xffffffff;
    for(unsigned i=0;i<n;++i) {
        c^=p[i];for(unsigned bit=0;bit<8;++bit)c=(c>>1)^((c&1)?0xedb88320u:0);
    }
    return c^0xffffffff;
}
inline void progress() {
    const auto gap=unsigned(now-serviced);if(gap>max_gap)max_gap=gap;
    serviced=now;++services;now+=50;
}
inline void reset_progress() {services=max_gap=0;serviced=now;}
}
struct mock_dma_hw { uint32_t ints0=0,ints1=0; };
inline mock_dma_hw registers;
inline auto* dma_hw=&registers;
inline unsigned get_core_num() {return endpoint::core;}
#define __sev() ((void)0)
inline uint64_t time_us_64() {return endpoint::now;}
inline uint64_t make_timeout_time_us(unsigned n) {return endpoint::now+n;}
inline void best_effort_wfe_or_timeout(uint64_t deadline) {
    for(unsigned i=0;i<12;++i)if(!endpoint::stuck[i] && endpoint::complete[i]>endpoint::now)
        deadline=std::min(deadline,endpoint::complete[i]);
    endpoint::now=deadline;
}
inline bool dma_channel_is_busy(unsigned c) {return endpoint::stuck[c] || endpoint::now<endpoint::complete[c];}
inline void dma_channel_abort(unsigned c) {endpoint::stuck[c]=false;endpoint::complete[c]=0;++endpoint::aborts;}
inline int dma_claim_unused_channel(bool) {return endpoint::available?2:-1;}
inline void dma_channel_set_irq0_enabled(unsigned,bool) {}
inline void dma_channel_set_irq1_enabled(unsigned,bool) {}
inline constexpr unsigned DMA_IRQ_0=0,DMA_IRQ_1=1,PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY=0;
inline void irq_add_shared_handler(unsigned,void(*)(),unsigned) {}
inline void irq_set_enabled(unsigned,bool) {}
struct mutex_t {};
#define auto_init_mutex(name) mutex_t name
inline bool mutex_try_enter(mutex_t*,uint32_t*) {
    if(endpoint::locked)return false;endpoint::locked=true;return true;
}
inline void mutex_exit(mutex_t*) {assert(endpoint::locked);endpoint::locked=false;}
inline constexpr unsigned DMA_SNIFF_CTRL_CALC_VALUE_CRC32R=1,DMA_SNIFF_CTRL_CALC_VALUE_CRC16=2,DMA_SIZE_8=0;
inline void dma_sniffer_disable() {}
inline void dma_sniffer_set_byte_swap_enabled(bool b) {assert(!b);}
inline void dma_sniffer_set_output_reverse_enabled(bool) {}
inline void dma_sniffer_set_output_invert_enabled(bool) {}
inline void dma_sniffer_set_data_accumulator(uint32_t n) {endpoint::accumulator=n;}
inline void dma_sniffer_enable(unsigned,unsigned,bool) {}
inline uint32_t dma_sniffer_get_data_accumulator() {return endpoint::accumulator;}
struct dma_channel_config {bool read=false,write=true,sniff=false;unsigned size=99;};
inline dma_channel_config dma_channel_get_default_config(unsigned) {return {};}
inline void channel_config_set_transfer_data_size(dma_channel_config* c,unsigned n) {c->size=n;}
inline void channel_config_set_read_increment(dma_channel_config* c,bool b) {c->read=b;}
inline void channel_config_set_write_increment(dma_channel_config* c,bool b) {c->write=b;}
inline void channel_config_set_sniff_enable(dma_channel_config* c,bool b) {c->sniff=b;}
inline void dma_channel_configure(unsigned channel,const dma_channel_config* c,uint8_t*,const uint8_t* p,unsigned n,bool start) {
    assert(c->read && !c->write && c->sniff && c->size==DMA_SIZE_8 && start);
    endpoint::accumulator=endpoint::crc(p,n);endpoint::complete[channel]=endpoint::now+1250;
}
'''
TEST=r'''
#include "mock_sdk.hpp"
#include "dma_support.hpp"
#include <array>
#include <cstdio>
using namespace picocalc::dma_support;
int main() {
    using namespace endpoint;
    complete[0]=1250;reset_progress();assert(wait(0,-1,progress));
    assert(now==1250 && services==25 && max_gap<=50 && !aborts);
    const auto old=now;complete[0]=now+1250;assert(wait(0u));assert(now-old==1250);
    stuck[0]=stuck[1]=true;const auto start=now;reset_progress();
    assert(!wait(0,1,progress));assert(now-start==1000000 && aborts==2 && max_gap<=50);
    std::array<uint8_t,7501> data{};for(unsigned i=0;i<data.size();++i)data[i]=uint8_t(i*13+(i>>4));
    reset_progress();assert(crc32(data.data(),data.size(),progress)==crc(data.data(),data.size()));
    assert(services==25 && max_gap<=50 && !locked);
    assert(crc32(reinterpret_cast<const uint8_t*>("123456789"),9)==0xcbf43926);
    assert(!crc32(data.data(),0,progress));
    assert(begin_crc(3,true));reset_progress();
    assert(crc32(data.data(),data.size(),progress)==crc(data.data(),data.size()));
    assert(services==(data.size()+255)/256 && locked);end_crc();
    core=1;available=false;reset_progress();
    assert(crc32(data.data(),data.size(),progress)==crc(data.data(),data.size()));
    assert(services==(data.size()+255)/256 && !locked);
    const auto s=statistics();assert(s.timeouts==1 && s.crc32_calls==2 && s.crc_fallbacks==1);
    std::puts("Production DMA: 50-us service, completion, bounded abort, exact CRC, serviced contention/no-channel fallback PASS");
}
'''
with tempfile.TemporaryDirectory(prefix='picocalc-dma-support-') as directory:
    folder=Path(directory)
    (folder/'mock_sdk.hpp').write_text(SDK)
    for name in ('hardware/dma.h','hardware/irq.h','pico/mutex.h','pico/stdlib.h'):
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('#include "mock_sdk.hpp"\n')
    (folder/'test.cpp').write_text(TEST)
    subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                    '-DPICO_ON_DEVICE','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                    '-I'+str(folder),'-I'+str(ROOT/'ports/picocalc'),'-I'+str(ROOT/'code'),
                    str(folder/'test.cpp'),str(ROOT/'ports/picocalc/dma_support.cpp'),'-o',str(folder/'test')],check=True)
    subprocess.run([str(folder/'test')],check=True)
