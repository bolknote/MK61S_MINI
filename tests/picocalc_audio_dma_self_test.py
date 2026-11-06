#!/usr/bin/env python3
"""Run the production chained-DMA synth against a paced hardware fixture."""
import ast
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
module=ast.parse((ROOT/'tests/picocalc_audio_self_test.py').read_text())
HEADER=next(ast.literal_eval(node.value) for node in module.body
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HEADER' for t in node.targets))
DMA_HEADER=r'''
#pragma once
#include "pico/stdlib.h"
enum { DMA_IRQ_1=12,DMA_SIZE_32=2,PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY=128,clk_sys=0 };
struct dma_channel_config { unsigned channel=0,chain=0,dreq=0,ring=0,size=0;bool enabled=true,read_increment=false,write_increment=false; };
struct fake_dma_hw { uint32_t ints1=0; };
struct fake_pwm_slice { uint32_t cc=0; };
struct fake_pwm_hw { fake_pwm_slice slice[8]; };
extern fake_dma_hw* dma_hw;
extern fake_pwm_hw* pwm_hw;
unsigned clock_get_hz(unsigned);
int dma_claim_unused_channel(bool);int dma_claim_unused_timer(bool);
void dma_channel_unclaim(unsigned);void dma_timer_unclaim(unsigned);
void dma_timer_set_fraction(unsigned,uint16_t,uint16_t);
unsigned dma_get_timer_dreq(unsigned);
dma_channel_config dma_channel_get_default_config(unsigned);
void channel_config_set_enable(dma_channel_config*,bool);
void channel_config_set_chain_to(dma_channel_config*,unsigned);
void channel_config_set_transfer_data_size(dma_channel_config*,unsigned);
void channel_config_set_read_increment(dma_channel_config*,bool);
void channel_config_set_write_increment(dma_channel_config*,bool);
void channel_config_set_dreq(dma_channel_config*,unsigned);
void channel_config_set_ring(dma_channel_config*,bool,unsigned);
void dma_channel_set_irq1_enabled(unsigned,bool);
void dma_channel_set_config(unsigned,const dma_channel_config*,bool);
void dma_channel_set_read_addr(unsigned,const volatile void*,bool);
void dma_channel_set_trans_count(unsigned,uint32_t,bool);
void dma_channel_configure(unsigned,const dma_channel_config*,volatile void*,const volatile void*,unsigned,bool);
void dma_start_channel_mask(uint32_t);void dma_channel_abort(unsigned);
void dma_channel_acknowledge_irq1(unsigned);bool dma_channel_is_busy(unsigned);
void irq_add_shared_handler(unsigned,void(*)(),unsigned);
void irq_remove_handler(unsigned,void(*)());void irq_set_enabled(unsigned,bool);
inline void __dmb() { std::atomic_thread_fence(std::memory_order_seq_cst); }
'''
with tempfile.TemporaryDirectory(prefix='picocalc-audio-dma-') as temp:
    build=Path(temp)
    for name in ('pico/stdlib.h','hardware/pwm.h','hardware/clocks.h','hardware/dma.h','hardware/irq.h','hardware/sync.h'):
        path=build/name;path.parent.mkdir(exist_ok=True)
        path.write_text(HEADER if name.startswith('pico') else DMA_HEADER if name=='hardware/dma.h' else '#include "hardware/dma.h"\n')
    command=['clang++','-std=c++17','-O2','-pthread','-Wall','-Wextra','-Werror','-DMK61_PICOCALC_AUDIO_DMA=1',
             '-I'+str(build),'-I'+str(ROOT/'ports/picocalc'),'-I'+str(ROOT/'code')]
    if os.environ.get('MK61_TEST_SANITIZERS')=='1':
        command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    for mhz in (125,200,250,'auto'):
        extra=['-DMK61_PICOCALC_AUDIO_CLOCK=1'] if mhz=='auto' else ['-DMK61_PICOCALC_COSMIC_CLOCK_DIAG=1',f'-DTEST_CLOCK_MHZ={mhz}']
        binary=build/f'test-{mhz}'
        subprocess.run(command+extra+[str(ROOT/'tests/picocalc_audio_dma_self_test.cpp'),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
