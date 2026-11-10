#pragma once
#include <stdint.h>
struct Probe {int32_t key[10];uint32_t hold[10],repeat[10],state[10],last_process;uint16_t hold_period;uint8_t item_mods[10][7],mods[7],caps_changed,caps,num_changed,num,matrix[9],joystick;};
