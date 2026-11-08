/**
 * emu2149 v1.42
 * https://github.com/digital-sound-antiques/emu2149
 * Copyright (C) 2001-2022 Mitsutaka Okazaki
 *
 * This source refers to the following documents. The author would like to thank all the authors who have
 * contributed to the writing of them.
 * - psg.vhd        -- 2000 written by Kazuhiro Tsujikawa.
 * - s_fme7.c       -- 1999,2000 written by Mamiya (NEZplug).
 * - ay8910.c       -- 1998-2001 Author unknown (MAME).
 * - MSX-Datapack   -- 1991 ASCII Corp.
 * - AY-3-8910 data sheet
 */
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include "emu2149.h"

static uint32_t voltbl[2][32] = {
  /* YM2149 - 32 steps */
  {0x00, 0x01, 0x01, 0x02, 0x02, 0x03, 0x03, 0x04, 0x05, 0x06, 0x07, 0x09,
   0x0B, 0x0D, 0x0F, 0x12,
   0x16, 0x1A, 0x1F, 0x25, 0x2D, 0x35, 0x3F, 0x4C, 0x5A, 0x6A, 0x7F, 0x97,
   0xB4, 0xD6, 0xFF, 0xFF},
  /* AY-3-8910 - 16 steps */
  {0x00, 0x00, 0x03, 0x03, 0x04, 0x04, 0x06, 0x06, 0x09, 0x09, 0x0D, 0x0D,
   0x12, 0x12, 0x1D, 0x1D,
   0x22, 0x22, 0x37, 0x37, 0x4D, 0x4D, 0x62, 0x62, 0x82, 0x82, 0xA6, 0xA6,
   0xD0, 0xD0, 0xFF, 0xFF}
};

static const uint8_t regmsk[16] = {
    0xff, 0x0f, 0xff, 0x0f, 0xff, 0x0f, 0x1f, 0xff,
    0x1f, 0x1f, 0x1f, 0xff, 0xff, 0x0f, 0xff, 0xff
};

#define GETA_BITS 24

static void
internal_refresh (PSG * psg)
{
  uint32_t f_master = psg->clk;
  
  if (psg->clk_div)
    f_master /= 2;

  if (psg->quality)
  {
    psg->base_incr = 1 << GETA_BITS;
    psg->realstep = f_master;
    psg->psgstep = psg->rate * 8;
    psg->psgtime = 0;
    psg->freq_limit = (uint32_t)(f_master / 16 / (psg->rate / 2));
  }
  else
  {
    psg->base_incr = (uint32_t)((double)f_master * (1 << GETA_BITS) / 8 / psg->rate);
    psg->freq_limit = 0;
  }
}

void 
PSG_setClock(PSG *psg, uint32_t clock)
{
  if (psg->clk != clock) {
    psg->clk = clock;
    internal_refresh(psg);
  }
}

void 
PSG_setClockDivider(PSG *psg, uint8_t enable)
{
  if (psg->clk_div != enable) {
    psg->clk_div = enable;  
    internal_refresh (psg);
  }
}

void
PSG_setRate (PSG * psg, uint32_t rate)
{
  uint32_t r = rate ? rate : 44100;
  if (psg->rate != r) {
    psg->rate = r;
    internal_refresh(psg);
  }
}

void
PSG_setQuality (PSG * psg, uint8_t q)
{
  if (psg->quality != q) {
    psg->quality = q;
    internal_refresh(psg);
  }
}

PSG *
PSG_new (uint32_t clock, uint32_t rate)
{
  PSG *psg;

  psg = (PSG *) calloc (1, sizeof (PSG));
  if (psg == NULL)
    return NULL;

  PSG_setVolumeMode(psg, 0);
  psg->clk = clock;
  psg->clk_div = 0;
  psg->rate = rate ? rate : 44100;
  psg->quality = 0;
  internal_refresh(psg);
  PSG_setMask(psg, 0x00);
  return psg;
}

void
PSG_setVolumeMode (PSG * psg, int type)
{
  switch (type)
  {
  case 1:
    psg->voltbl = voltbl[0]; /* YM2149 */
    break;
  case 2:
    psg->voltbl = voltbl[1]; /* AY-3-8910 */
    break;
  default:
    psg->voltbl = voltbl[0]; /* fallback: YM2149 */
    break;
  }
}

uint32_t
PSG_setMask (PSG *psg, uint32_t mask)
{
  uint32_t ret = 0;
  if(psg)
  {
    ret = psg->mask;
    psg->mask = mask;
  }  
  return ret;
}

uint32_t
PSG_toggleMask (PSG *psg, uint32_t mask)
{
  uint32_t ret = 0;
  if(psg)
  {
    ret = psg->mask;
    psg->mask ^= mask;
  }
  return ret;
}

void
PSG_reset (PSG * psg)
{
  int i;

  psg->base_count = 0;

  for (i = 0; i < 3; i++)
  {
    psg->count[i] = 0;
    psg->freq[i] = 0;
    psg->edge[i] = 0;
    psg->volume[i] = 0;
    psg->ch_out[i] = 0;
  }

  psg->mask = 0;

  for (i = 0; i < 16; i++)
    psg->reg[i] = 0;
  psg->adr = 0;

  psg->noise_seed = 0xffff;
  psg->noise_scaler = 0;
  psg->noise_count = 0;
  psg->noise_freq = 0;

  psg->env_ptr = 0;
  psg->env_freq = 0;
  psg->env_count = 0;
  psg->env_pause = 1;

  psg->out = 0;

}

void
PSG_delete (PSG * psg)
{
  free (psg);
}

uint8_t
PSG_readIO (PSG * psg)
{
  return (uint8_t) (psg->reg[psg->adr]);
}

uint8_t
PSG_readReg (PSG * psg, uint32_t reg)
{
  return (uint8_t) (psg->reg[reg & 0x1f]);
}

void
PSG_writeIO (PSG * psg, uint32_t adr, uint32_t val)
{
  if (adr & 1)
    PSG_writeReg (psg, psg->adr, val);
  else
    psg->adr = val & 0x1f;
}

static inline void
update_output (PSG * psg)
{

  int i, noise;
  uint8_t incr;

  psg->base_count += psg->base_incr;
  incr = (psg->base_count >> GETA_BITS);
  psg->base_count &= (1 << GETA_BITS) - 1;

  /* Envelope */
  psg->env_count += incr;

  if (psg->env_count >= psg->env_freq)
  {
    if (!psg->env_pause)
    {
      if(psg->env_face)
        psg->env_ptr = (psg->env_ptr + 1) & 0x3f ; 
      else
        psg->env_ptr = (psg->env_ptr + 0x3f) & 0x3f;
    }

    if (psg->env_ptr & 0x20) /* if carry or borrow */
    {
      if (psg->env_continue)
      {
        if (psg->env_alternate^psg->env_hold) psg->env_face ^= 1;
        if (psg->env_hold) psg->env_pause = 1;
        psg->env_ptr = psg->env_face ? 0 : 0x1f;       
      }
      else
      {
        psg->env_pause = 1;
        psg->env_ptr = 0;
      }
    }

    if (psg->env_freq >= incr) 
      psg->env_count -= psg->env_freq;
    else
      psg->env_count = 0;
  }

  /* Noise */
  psg->noise_count += incr;
  if (psg->noise_count >= psg->noise_freq)
  {
    psg->noise_scaler ^= 1;
    if (psg->noise_scaler) 
    { 
      if (psg->noise_seed & 1)
        psg->noise_seed ^= 0x24000;
      psg->noise_seed >>= 1;
    }
    
    if (psg->noise_freq >= incr)
      psg->noise_count -= psg->noise_freq;
    else
      psg->noise_count = 0;
  }
  noise = psg->noise_seed & 1;

  /* Tone */
  for (i = 0; i < 3; i++)
  {
    psg->count[i] += incr;
    if (psg->count[i] >= psg->freq[i])
    {
      psg->edge[i] = !psg->edge[i];

      if (psg->freq[i] >= incr) 
        psg->count[i] -= psg->freq[i];
      else
        psg->count[i] = 0;
    }

    if (0 < psg->freq_limit && psg->freq[i] <= psg->freq_limit && psg->nmask[i] && !psg->tmask[i])
    {
      /* Mute the channel if the pitch is higher than the Nyquist frequency at the current sample rate, 
       * to prevent aliased or broken tones from being generated. Of course, this logic doesn't exist 
       * on the actual chip, but practically all tones higher than the Nyquist frequency are usually 
       * removed by a low-pass circuit somewhere, so we here halt the output. */
      psg->ch_out[i] = 0;
      continue;
    }

    if (psg->mask & PSG_MASK_CH(i)) 
    {
      psg->ch_out[i] = 0;
      continue;
    }

    if ((psg->tmask[i]||psg->edge[i]) && (psg->nmask[i]||noise))
    {
      if (!(psg->volume[i] & 32)) 
        psg->ch_out[i] = (psg->voltbl[psg->volume[i] & 31] << 4);
      else 
        psg->ch_out[i] = (psg->voltbl[psg->env_ptr] << 4);
    }
    else 
    {
      psg->ch_out[i] = 0;
    }
  }
}

static inline int16_t 
mix_output(PSG *psg) 
{
  return (int16_t)(psg->ch_out[0] + psg->ch_out[1] + psg->ch_out[2]);
}

static int16_t
calc_reference (PSG * psg)
{
  if (!psg->quality) 
  {
    update_output(psg);
    psg->out = mix_output(psg);
  }
  else
  {
    /* Simple rate converter (See README for detail). */
    while (psg->realstep > psg->psgtime)
    {
      psg->psgtime += psg->psgstep;
      update_output(psg);
      psg->out += mix_output(psg);
      psg->out >>= 1;
    }
    psg->psgtime -= psg->realstep;
  }
  return psg->out;
}

/* With all three volumes zero, oversampling cannot change the output.
 * Advance the same counters/LFSR/envelope and decay the same IIR filter,
 * without evaluating the silent mixer eight or nine times per sample. */
static unsigned advance_counter(uint32_t* count,unsigned period,unsigned ticks)
{
  if (!period) { *count=0; return ticks; }
  unsigned events=0;
  while(ticks && *count>=period) { ++*count;*count-=period;--ticks;++events; }
  if(!ticks) return events;
  *count+=ticks;
  if(*count>=period) {
    if(*count<period*2) { *count-=period;++events; }
    else { const unsigned quotient=*count/period;events+=quotient;*count-=quotient*period; }
  }
  return events;
}
static void advance_envelope(PSG* psg,unsigned ticks)
{
  unsigned steps=advance_counter(&psg->env_count,psg->env_freq,ticks);
  while(steps-- && !psg->env_pause) {
    psg->env_ptr=(psg->env_ptr+(psg->env_face?1:0x3F))&0x3F;
    if(psg->env_ptr&0x20) {
      if(psg->env_continue) {
        if(psg->env_alternate^psg->env_hold) psg->env_face^=1;
        if(psg->env_hold) psg->env_pause=1;
        psg->env_ptr=psg->env_face?0:0x1F;
      } else { psg->env_pause=1;psg->env_ptr=0; }
    }
  }
}
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
static inline __attribute__((always_inline)) uint32_t advance_noise(uint32_t seed,unsigned shifts)
{
  do {
    /* During these shifts feedback cannot reach the consumed low bits.
     * Advance both taps of x^17+x^14+1 together, including overlaps via XOR. */
    const unsigned n=shifts>8?8:shifts;
    const uint32_t feedback=seed&((1u<<n)-1);
    seed=(seed>>n)^(feedback<<(17-n))^(feedback<<(14-n));shifts-=n;
  } while(shifts);
  return seed;
}
#endif
static void advance_state(PSG* psg,unsigned ticks)
{
  for(unsigned i=0;i<3;++i) {
    uint32_t count=psg->count[i];const unsigned edges=advance_counter(&count,psg->freq[i],ticks);
    psg->count[i]=(uint16_t)count;if(edges&1) psg->edge[i]=!psg->edge[i];
  }
  uint32_t count=psg->noise_count;
  const unsigned edges=advance_counter(&count,psg->noise_freq,ticks);
  unsigned shifts=(edges+(psg->noise_scaler?0:1))/2;
  psg->noise_count=(uint8_t)count;psg->noise_scaler^=edges&1;
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
  psg->noise_seed=advance_noise(psg->noise_seed,shifts);
#else
  while(shifts--) { if(psg->noise_seed&1) psg->noise_seed^=0x24000;psg->noise_seed>>=1; }
#endif
  advance_envelope(psg,ticks);
}
static unsigned output_ticks(PSG* psg)
{
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
  /* Cortex-M3 has UDIV: replace the internal-tick loop by its exact count. */
  const unsigned ticks=psg->realstep>psg->psgtime?
    (psg->realstep-psg->psgtime-1)/psg->psgstep+1:0;
  psg->psgtime+=ticks*psg->psgstep;psg->psgtime-=psg->realstep;return ticks;
#else
  unsigned ticks=0;
  while(psg->realstep>psg->psgtime) { psg->psgtime+=psg->psgstep;++ticks; }
  psg->psgtime-=psg->realstep;return ticks;
#endif
}
static int16_t calc_silent(PSG* psg,unsigned ticks)
{
  advance_state(psg,ticks);
  for(unsigned i=0;i<3;++i)psg->ch_out[i]=0;
  psg->out>>=ticks<31?ticks:31;return psg->out;
}
/* For N ticks, repeated floor((out+mix)/2) is exactly
 * floor((out0 + sum(mix[i]*2^i))/2^N). With fixed channel amplitudes,
 * three hardware32-bit multiplies replace all intermediate mixer steps.
 * Oscillator/noise masks preserve every internal tick and final state. */
static bool weighted_eligible(const PSG* psg,unsigned ticks)
{
  if(!ticks || ticks>16 || psg->out < -32768 || psg->out>32767 ||
     (psg->voltbl!=voltbl[0] && psg->voltbl!=voltbl[1]))return false;
#if !defined(EMU2149_M3_AUDIO) || !EMU2149_M3_AUDIO
  if(((psg->volume[0]|psg->volume[1]|psg->volume[2])&32) && !psg->env_pause &&
     (psg->env_freq<=psg->env_count || psg->env_freq-psg->env_count<=ticks))return false;
#endif
  return psg->env_ptr<32;
}
static uint32_t tone_mask(PSG* psg,unsigned channel,unsigned ticks,uint32_t all)
{
  uint16_t count=psg->count[channel];const uint16_t period=psg->freq[channel];
  unsigned edge=psg->edge[channel];uint32_t bits=0;
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
  if(!period) {
    bits=0x5555u;if(edge)bits^=all;
    psg->count[channel]=0;psg->edge[channel]=(uint8_t)(edge^(ticks&1));return bits&all;
  }
  if(count<period) {
    if(period>=ticks) {
      const unsigned remaining=period-count;
      bits=edge?all:0;count=(uint16_t)(count+ticks);
      if(remaining<=ticks){bits^=(all<<(remaining-1))&all;count=(uint16_t)(count-period);edge^=1;}
    } else {
      /* Internal tick i observes phase count+i+1. Short square waves fit
       * in a32-bit word; M3 UDIV advances the final phase exactly. */
      static const uint32_t waves[16]={0,0xaaaaaaaau,0xccccccccu,0x38e38e38u,
        0xf0f0f0f0u,0x3e0f83e0u,0xc0fc0fc0u,0x0fe03f80u,0xff00ff00u,
        0xf803fe00u,0xc00ffc00u,0x003ff800u,0x00fff000u,0x03ffe000u,
        0x0fffc000u,0x3fff8000u};
      bits=(waves[period]>>(count+1))&all;if(edge)bits^=all;
      const unsigned total=count+ticks,edges=total/period;
      count=(uint16_t)(total-edges*period);edge^=edges&1;
    }
    psg->count[channel]=count;psg->edge[channel]=(uint8_t)edge;return bits;
  }
#endif
  if(count<period && (unsigned)(period-count)>ticks) {
    count=(uint16_t)(count+ticks);bits=edge?all:0;
  } else for(unsigned i=0;i<ticks;++i) {
    ++count;if(count>=period) {edge=!edge;count=period?(uint16_t)(count-period):0;}
    if(edge)bits|=1U<<i;
  }
  psg->count[channel]=count;psg->edge[channel]=(uint8_t)edge;return bits;
}
static uint32_t noise_mask(PSG* psg,unsigned ticks,uint32_t all)
{
  uint8_t count=psg->noise_count;const unsigned period=psg->noise_freq;
  unsigned scaler=psg->noise_scaler;uint32_t seed=psg->noise_seed,bits=0;
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
  if(period<=1 && (!period || !count)) {
    /* The next eight LFSR low bits precede any feedback bit. Spread them
     * to two ticks each; no per-tick noise branches or output stores. */
    uint32_t spread=(seed>>(scaler?0:1))&0x1ffu;
    spread=(spread|(spread<<8))&0x00ff00ffu;
    spread=(spread|(spread<<4))&0x0f0f0f0fu;
    spread=(spread|(spread<<2))&0x33333333u;
    spread=(spread|(spread<<1))&0x55555555u;
    bits=spread|(spread<<1);if(scaler)bits>>=1;
    unsigned shifts=(ticks+(scaler?0:1))/2;
    seed=advance_noise(seed,shifts);
    psg->noise_count=0;psg->noise_scaler=(uint8_t)(scaler^(ticks&1));psg->noise_seed=seed;return bits&all;
  }
#endif
  if(count<period && period-count>ticks) {count=(uint8_t)(count+ticks);bits=(seed&1)?all:0;}
  else for(unsigned i=0;i<ticks;++i) {
    ++count;if(count>=period) {
      scaler^=1;if(scaler) {if(seed&1)seed^=0x24000;seed>>=1;}
      count=period?(uint8_t)(count-period):0;
    }
    bits|=(seed&1)<<i;
  }
  psg->noise_count=count;psg->noise_scaler=(uint8_t)scaler;psg->noise_seed=seed;return bits;
}
static int16_t calc_weighted(PSG* psg,unsigned ticks)
{
  const uint32_t all=(1U<<ticks)-1,noise=noise_mask(psg,ticks,all);
  int32_t sum=psg->out;
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
  const bool changing=((psg->volume[0]|psg->volume[1]|psg->volume[2])&32) && !psg->env_pause &&
    (psg->env_freq<=psg->env_count || psg->env_freq-psg->env_count<=ticks);
  uint32_t envelopes[3]={0,0,0};
#endif
  for(unsigned i=0;i<3;++i) {
    uint32_t bits=tone_mask(psg,i,ticks,all);
    bits=(psg->tmask[i]?all:bits)&(psg->nmask[i]?all:noise);
    if((psg->mask&PSG_MASK_CH(i)) ||
       (psg->freq_limit && psg->freq[i]<=psg->freq_limit && psg->nmask[i] && !psg->tmask[i]))bits=0;
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
    if(changing && (psg->volume[i]&32)){envelopes[i]=bits;continue;}
#endif
    const unsigned amplitude=psg->voltbl[(psg->volume[i]&32)?psg->env_ptr:psg->volume[i]&31]<<4;
    sum+=(int32_t)(amplitude*bits);psg->ch_out[i]=(bits&(1U<<(ticks-1)))?(int16_t)amplitude:0;
  }
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
  if(changing) {
    /* All envelope channels share one amplitude at a tick. Preserve the
     * exact IIR weights while advancing the envelope once, rather than
     * repeating all oscillator/mixer work for each internal tick. */
    unsigned count=psg->env_count,ptr=psg->env_ptr,face=psg->env_face,pause=psg->env_pause;
    const unsigned period=psg->env_freq;
    for(unsigned tick=0;tick<ticks;++tick) {
      if(++count>=period) {
        count=period?count-period:0;
        if(!pause) {
          ptr=(ptr+(face?1:63))&63;
          if(ptr&32) {
            if(psg->env_continue) {
              if(psg->env_alternate^psg->env_hold)face^=1;
              if(psg->env_hold)pause=1;
              ptr=face?0:31;
            } else {pause=1;ptr=0;}
          }
        }
      }
      const unsigned gates=((envelopes[0]>>tick)&1)+((envelopes[1]>>tick)&1)+((envelopes[2]>>tick)&1);
      sum+=(int32_t)((psg->voltbl[ptr]<<4)*(gates<<tick));
    }
    psg->env_count=count;psg->env_ptr=(uint8_t)ptr;psg->env_face=(uint8_t)face;psg->env_pause=(uint8_t)pause;
    for(unsigned i=0;i<3;++i)if(psg->volume[i]&32)
      psg->ch_out[i]=(envelopes[i]&(1U<<(ticks-1)))?(int16_t)(psg->voltbl[psg->env_ptr]<<4):0;
  } else
#endif
  advance_envelope(psg,ticks);
  psg->out=sum>>ticks;return (int16_t)psg->out;
}
static int16_t calc_quality(PSG* psg,unsigned ticks)
{
  if(weighted_eligible(psg,ticks))return calc_weighted(psg,ticks);
  while(ticks--) { update_output(psg);psg->out=(psg->out+mix_output(psg))>>1; }
  return psg->out;
}
int16_t PSG_calc(PSG* psg)
{
  if(psg->quality && psg->base_incr==(1U<<GETA_BITS)) {
    const unsigned ticks=output_ticks(psg);if(!ticks)return (int16_t)psg->out;
    if(!(psg->volume[0]|psg->volume[1]|psg->volume[2]))return calc_silent(psg,ticks);
    return calc_quality(psg,ticks);
  }
  return calc_reference(psg);
}
/* Host equivalence checks; linker discards this unused entry from APPs. */
int16_t PSG_calc_reference(PSG* psg) { return calc_reference(psg); }

void
PSG_writeReg (PSG * psg, uint32_t reg, uint32_t val)
{
  int c;

  if (reg > 15) return;

  val &= regmsk[reg];

  psg->reg[reg] = (uint8_t) val;

  switch (reg)
  {
  case 0:
  case 2:
  case 4:
  case 1:
  case 3:
  case 5:
    c = reg >> 1;
    psg->freq[c] = ((psg->reg[c * 2 + 1] & 15) << 8) + psg->reg[c * 2];
    break;

  case 6:
    psg->noise_freq = val & 31;
    break;

  case 7:
    psg->tmask[0] = (val & 1);
    psg->tmask[1] = (val & 2);
    psg->tmask[2] = (val & 4);
    psg->nmask[0] = (val & 8);
    psg->nmask[1] = (val & 16);
    psg->nmask[2] = (val & 32);
    break;

  case 8:
  case 9:
  case 10:
    psg->volume[reg - 8] = val << 1;
    break;
 
  case 11:
  case 12:
    psg->env_freq = (psg->reg[12] << 8) + psg->reg[11];
    break;

  case 13:
    psg->env_continue = (val >> 3) & 1;
    psg->env_attack = (val >> 2) & 1;
    psg->env_alternate = (val >> 1) & 1;
    psg->env_hold = val & 1;
    psg->env_face = psg->env_attack;
    psg->env_pause = 0;
    psg->env_ptr = psg->env_face ? 0 : 0x1f;
    break;

  case 14:
  case 15:
  default:
    break;
  }

  return;
}
