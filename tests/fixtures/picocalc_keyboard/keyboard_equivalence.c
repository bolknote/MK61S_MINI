
#include "keyboard.h"
#include "regs.h"
#include "probe.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
GPIO_TypeDef fake_ports[3]={{0},{1},{2}};
struct Token {uint32_t kind,a,b;};
struct Run {struct Token trace[4096];unsigned used,gpio,time_calls;uint32_t now;int column;} run[2];
static unsigned current,frame;static uint32_t step_time,cfg,frequency,noise,seed=0x4b455953;static uint8_t pressed[68];
static void log_event(unsigned kind,uint32_t a,uint32_t b){struct Run*r=&run[current];assert(r->used<4096);r->trace[r->used++]=(struct Token){kind,a,b};}
static uint32_t rnd(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static unsigned pin(uint32_t mask){assert(mask && !(mask&(mask-1)));return(unsigned)__builtin_ctz(mask);}
uint32_t uptime_ms(void){uint32_t now=run[current].now;run[current].now+=step_time;++run[current].time_calls;log_event(3,now,0);return now;}
uint8_t reg_get_value(enum reg_id id){uint8_t value=id==REG_ID_FRQ?(uint8_t)frequency:id==REG_ID_SYS_CFG?(uint8_t)cfg:0;log_event(4,id,value);return value;}
uint8_t reg_is_bit_set(enum reg_id id,uint8_t bit){uint8_t value=(uint8_t)((id==REG_ID_SYS_CFG?cfg:0)&bit);log_event(5,id,bit);return value;}
uint32_t LL_GPIO_IsInputPinSet(GPIO_TypeDef*port,uint32_t mask){
 unsigned n=pin(mask),key;
 if(port->id==0){assert(run[current].column>=0 && n<7);key=n*8+(unsigned)run[current].column;}
 else{assert(port->id==2 && n<12);key=56+n;}
 unsigned value=pressed[key];
 if(noise){uint32_t x=key*0x9e3779b9u+run[current].gpio*0x45d9f3bu+frame;x^=x>>16;if((x&31)==0)value^=1;}
 ++run[current].gpio;log_event(1,(port->id<<16)|mask,value);return !value;
}
void LL_GPIO_ResetOutputPin(GPIO_TypeDef*p,uint32_t m){assert(p->id==1);run[current].column=(int)pin(m);log_event(2,m,0);}
void LL_GPIO_SetOutputPin(GPIO_TypeDef*p,uint32_t m){assert(p->id==1);run[current].column=-1;log_event(2,m,1);}
void lcd_backlight_update_up(void){log_event(8,1,0);}void lcd_backlight_update_down(void){log_event(8,2,0);}
void kbd_backlight_update_loop(void){log_event(8,3,0);}void show_bat_segs(void){log_event(8,4,0);}
static void key_cb(char c,enum key_state s){log_event(6,(unsigned char)c,(uint32_t)s);}static void lock_cb(uint8_t c,uint8_t n){log_event(7,c,n);}
#define DECLARE(p) void p##_keyboard_process(void);void p##_keyboard_reset(void);void p##_keyboard_set_key_callback(key_callback);void p##_keyboard_set_lock_callback(lock_callback);void p##_keyboard_set_hold_period(uint16_t);void p##_probe_snapshot(struct Probe*);
DECLARE(ref) DECLARE(new)
int main(void){
 uint32_t base=0xffffff00u;unsigned total_gpio=0,total_events=0,scans=0,skips=0;
 for(frame=0;frame<25000;++frame){
  if(frame<68*6){memset(pressed,0,sizeof(pressed));unsigned key=frame/6;unsigned phase=frame%6;pressed[key]=(uint8_t)(phase<4);base+=phase==2?350:phase==3?120:20;frequency=16;cfg=192;step_time=0;noise=0;}
  else{
   base+=rnd()%501;frequency=(uint32_t[]){0,1,16,255}[rnd()&3];cfg=(uint32_t[]){0,64,128,192}[rnd()&3];step_time=(rnd()&7)==0?1:0;noise=(rnd()&7)==0;
   for(unsigned n=0;n<1+(rnd()%6);++n){unsigned key=rnd()%68;pressed[key]^=1;}
   if(frame%113==0)memset(pressed,(frame/113)&1,sizeof(pressed));
  }
  struct Probe state[2];
  for(current=0;current<2;++current){
   memset(&run[current],0,sizeof(run[current]));run[current].now=base;run[current].column=-1;
   if(frame%97==0){if(current) new_keyboard_reset();else ref_keyboard_reset();}
   if(current){new_keyboard_set_key_callback((frame%11)?key_cb:NULL);new_keyboard_set_lock_callback((frame%13)?lock_cb:NULL);new_keyboard_set_hold_period((uint16_t)((frame%7)*100));new_keyboard_process();new_probe_snapshot(&state[1]);}
   else{ref_keyboard_set_key_callback((frame%11)?key_cb:NULL);ref_keyboard_set_lock_callback((frame%13)?lock_cb:NULL);ref_keyboard_set_hold_period((uint16_t)((frame%7)*100));ref_keyboard_process();ref_probe_snapshot(&state[0]);}
  }
  if(run[0].used!=run[1].used || memcmp(run[0].trace,run[1].trace,run[0].used*sizeof(struct Token)) || memcmp(&state[0],&state[1],sizeof(struct Probe))){fprintf(stderr,"keyboard mismatch frame=%u events=%u/%u gpio=%u/%u base=%u frequency=%u config=%u\n",frame,run[0].used,run[1].used,run[0].gpio,run[1].gpio,base,frequency,cfg);return 1;}
  assert(run[0].gpio==0 || run[0].gpio==152);total_gpio+=run[0].gpio;total_events+=run[0].used;if(run[0].gpio)++scans;else++skips;
 }
 printf("PASS frames=%u scans=%u skips=%u exact_GPIO_reads=%u exact_trace_events=%u\n",frame,scans,skips,total_gpio,total_events);
 return 0;
}
