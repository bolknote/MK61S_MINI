#!/usr/bin/env python3
"""Reject warnings except the explicitly qualified STM32 build diagnostics."""

import argparse
import json
from pathlib import Path
import re
import sys
from analyze_stack_usage import entry_arguments


RTC_WARNING = re.compile(
    r'.*STM32RTC\.cpp:[0-9]+:[0-9]+: warning: #warning '
    r'"only BCD mode is supported"(?: \[-Wcpp\])?')
LTO_WARNING = re.compile(
    r'lto-wrapper: warning: using serial compilation of [0-9]+ LTRANS jobs')
PINNED_TONE_SOURCE = '/packages/STMicroelectronics/hardware/stm32/2.12.0/cores/arduino/Tone.cpp'
TONE_MESSAGE = '#warning "TIMER_TONE or HAL_TIM_MODULE_ENABLED not defined"'


def unexpected_warnings(log: str, commands: list[dict]) -> list[str]:
    tone_sources = set()
    lto = False
    for command in commands:
        arguments = entry_arguments(command) if command.get('arguments') or command.get('command') else []
        lto |= any(arg == '-flto' or arg.startswith('-flto=') for arg in arguments)
        source = command.get('file', '').replace('\\', '/')
        if source.endswith(PINNED_TONE_SOURCE) and any(
                arg == '-DHAL_TIM_MODULE_ONLY' or
                arg.startswith('-DHAL_TIM_MODULE_ONLY=') for arg in arguments):
            tone_sources.add(source)

    unexpected = []
    for line in log.splitlines():
        if 'warning:' not in line:
            continue
        normalized = line.replace('\\', '/')
        if RTC_WARNING.fullmatch(normalized):
            continue
        if lto and LTO_WARNING.fullmatch(normalized):
            continue
        # The exact pinned Core warning is expected when our direct drivers
        # deliberately remove Arduino tone(). Require its actual compile
        # command to carry the flag; a new Tone warning is still a failure.
        if any(normalized in (
                f'{source}:135:2: warning: {TONE_MESSAGE}',
                f'{source}:135:2: warning: {TONE_MESSAGE} [-Wcpp]')
               for source in tone_sources):
            continue
        unexpected.append(line)
    return unexpected


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--compile-commands', type=Path, required=True)
    args = parser.parse_args()
    commands = json.loads(args.compile_commands.read_text(encoding='utf-8'))
    warnings = unexpected_warnings(args.log.read_text(encoding='utf-8'), commands)
    if warnings:
        print(f'Unexpected compiler warnings in {args.log}:', file=sys.stderr)
        print('\n'.join(warnings), file=sys.stderr)
        raise SystemExit(1)
