#!/usr/bin/env python3
"""Exercise production audio ownership against a serialized core-1 fixture."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEADER = r"""
#pragma once
#include <cstdint>
struct repeating_timer;
using repeating_timer_t=repeating_timer;
using repeating_timer_callback_t=bool(*)(repeating_timer*);
struct repeating_timer { repeating_timer_callback_t callback=nullptr; };
struct alarm_pool_t {};
alarm_pool_t* alarm_pool_create_with_unused_hardware_alarm(unsigned);
bool alarm_pool_add_repeating_timer_us(alarm_pool_t*,int64_t,repeating_timer_callback_t,void*,repeating_timer*);
bool cancel_repeating_timer(repeating_timer*);
enum { GPIO_OUT=1,GPIO_FUNC_PWM=4 };
void gpio_init(unsigned);void gpio_set_dir(unsigned,bool);void gpio_put(unsigned,bool);void gpio_set_function(unsigned,unsigned);
unsigned pwm_gpio_to_slice_num(unsigned);
void pwm_set_both_levels(unsigned,uint16_t,uint16_t);void pwm_set_enabled(unsigned,bool);
void pwm_set_clkdiv_int_frac4(unsigned,unsigned,unsigned);void pwm_set_wrap(unsigned,unsigned);
"""

with tempfile.TemporaryDirectory(prefix="picocalc-audio-") as temp:
    build = Path(temp)
    for name in ("pico/stdlib.h", "hardware/pwm.h"):
        path = build / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(HEADER if name.startswith("pico") else '#include "pico/stdlib.h"\n')
    command = ["clang++", "-std=c++17", "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
               "-I" + str(build), "-I" + str(ROOT / "ports/picocalc"), "-I" + str(ROOT / "code")]
    if os.environ.get("MK61_TEST_SANITIZERS") == "1":
        command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    subprocess.run(command + [str(ROOT / "tests/picocalc_audio_self_test.cpp"), "-o", str(build / "test")], check=True)
    subprocess.run([str(build / "test")], check=True)
