
#include "probe.h"
#include <string.h>
void probe_snapshot(struct Probe*out){
 memset(out,0,sizeof(*out));
 for(unsigned i=0;i<10;++i){
  out->key[i]=-1;
  for(unsigned k=0;k<56;++k)if(keys_list[i].p_entry==&((const struct entry*)kbd_entries)[k])out->key[i]=(int32_t)k;
  for(unsigned k=0;k<12;++k)if(keys_list[i].p_entry==&btn_entries[k])out->key[i]=(int32_t)(56+k);
  out->hold[i]=keys_list[i].hold_start_time;out->repeat[i]=keys_list[i].last_repeat_time;out->state[i]=keys_list[i].state;
  memcpy(out->item_mods[i],keys_list[i].mods,sizeof(keys_list[i].mods));
 }
 out->last_process=last_process_time;out->hold_period=hold_period;memcpy(out->mods,mods,sizeof(mods));
 out->caps_changed=capslock_changed;out->caps=capslock;out->num_changed=numlock_changed;out->num=numlock;
 memcpy(out->matrix,io_matrix,9);out->joystick=js_bits;
}
