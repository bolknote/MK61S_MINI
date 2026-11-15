#!/usr/bin/env python3
"""Test the production heap event recorder using host locks and two cores."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='picocalc-heap-trace-') as directory:
    work=Path(directory);(work/'pico').mkdir()
    (work/'pico/critical_section.h').write_text('''#pragma once
#include <mutex>
struct critical_section_t { std::mutex mutex; };
inline void critical_section_init(critical_section_t*) {}
inline void critical_section_enter_blocking(critical_section_t* p) { p->mutex.lock(); }
inline void critical_section_exit(critical_section_t* p) { p->mutex.unlock(); }
''')
    (work/'pico/multicore.h').write_text('''#pragma once
extern thread_local unsigned test_core;
inline unsigned get_core_num() { return test_core; }
''')
    (work/'pico.h').write_text('#pragma once\n#define PICO_USE_MALLOC_MUTEX 1\n')
    (work/'pico/malloc.h').write_text('#pragma once\n')
    (work/'pico/mutex.h').write_text('''#pragma once
#include <mutex>
#define auto_init_mutex(name) std::mutex name
inline void mutex_enter_blocking(std::mutex* p) { p->lock(); }
inline void mutex_exit(std::mutex* p) { p->unlock(); }
''')
    (work/'reent.h').write_text('struct _reent {};\n')
    cmd=[os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread',
         '-I'+str(work),'-I'+str(ROOT/'ports/picocalc')]
    if os.environ.get('MK61_TEST_SANITIZERS')=='1':
        cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    cmd += [str(ROOT/'ports/picocalc/heap_trace.cpp'),str(ROOT/'tests/picocalc_heap_trace_self_test.cpp'),'-o',str(work/'test')]
    subprocess.run(cmd,check=True);subprocess.run([str(work/'test')],check=True)
    cmd=cmd[:-3]+[str(ROOT/'ports/picocalc/heap_trace_malloc.cpp'),
                   str(ROOT/'tests/picocalc_heap_trace_malloc_self_test.cpp'),'-o',str(work/'wrappers')]
    subprocess.run(cmd,check=True);subprocess.run([str(work/'wrappers')],check=True)
