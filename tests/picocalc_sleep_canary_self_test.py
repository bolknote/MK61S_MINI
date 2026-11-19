#!/usr/bin/env python3
"""Check the hardware probe detects lost RAM, missing expiry and active modules."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'tests/picocalc_m3_sleep_canary_app.c').read_text()
run = source[source.index('static int run(void)'):source.index('\nint main(void)')]
pattern = source[source.index('static uint8_t pattern('):source.index('\nstatic uint32_t micros(')]
fixture = r'''
#include "mk61_app.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static volatile uint32_t globals[256];
typedef struct { uint32_t waits,us,expired; } Counters;
static uint8_t external_bytes[4096];
static uint32_t clock_us, expiry_at;
static unsigned services, samples, resumes;
static int fault;
static Counters measured;
static uint32_t micros(void *p) { (void)p; clock_us+=100000; return clock_us; }
static int counters(Counters *out) {
    ++samples;
    if (expiry_at && clock_us >= expiry_at && fault!=3) {
        ++measured.expired; expiry_at=0;
    }
    *out=measured;return 0;
}
static void line(const char *s) { if(strstr(s,"SLEEPCAN RESUME")) ++resumes; }
static void service(void) {
    ++services;clock_us+=2000000;
    if(!SLEEP_KEEP_MODULE || fault==4) { measured.waits+=100;measured.us+=1700000; }
    expiry_at=clock_us+1500000;
    if(fault==1) globals[9]^=1;
    if(fault==2) external_bytes[2877]^=1;
}
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void *p) {
    (void)b;(void)c;
    if(op==MK61_SERVICE_CAPABILITIES) return MK61_SERVICE_CAP_BUFFERS;
    assert(op==MK61_SERVICE_BUFFER);
    mk61_service_buffer *r=p;
    if(a==MK61_BUFFER_ACQUIRE) {
        assert(r->size==4096 && r->access==MK61_BUFFER_EXTERNAL);
        r->handle=1;r->storage=MK61_BUFFER_PSRAM;return 1;
    }
    assert(r->handle==1);
    if(a==MK61_BUFFER_RELEASE) return 1;
    assert(r->offset+r->size<=sizeof(external_bytes));
    if(a==MK61_BUFFER_READ) memcpy(r->data,external_bytes+r->offset,r->size);
    else { assert(a==MK61_BUFFER_WRITE);memcpy(external_bytes+r->offset,r->data,r->size); }
    return 1;
}
static int format(char *out,uint32_t n,const char *f,va_list args) { return vsnprintf(out,n,f,args); }
static const mk61_app_services api_services={.call=call,.format=format};
static const mk61_app_services *svc=&api_services;
static const mk61_app_api api={.service=service};
const mk61_app_api *mk61_api=&api;
PATTERN
RUN
int main(void) {
    for(fault=0;fault<=4;++fault) {
        if(fault==4 && !SLEEP_KEEP_MODULE) continue;
        clock_us=expiry_at=services=samples=resumes=0;
        memset(&measured,0,sizeof(measured));
        const int result=run();
        const int expected=fault==0 ? 0 : fault==1 ? -9 : fault==2 ? -11 :
            fault==3 ? (SLEEP_KEEP_MODULE?0:-8) : -12;
        assert(result==expected);
        if(!result) assert(services==2 && resumes==2);
        if(!result && !SLEEP_KEEP_MODULE) assert(measured.expired==1 && samples==4);
    }
    return 0;
}
'''.replace('PATTERN', pattern).replace('RUN', run)
with tempfile.TemporaryDirectory(prefix='sleep-canary-') as temp:
    temp = Path(temp)
    (temp / 'test.c').write_text(fixture)
    for hold in (0, 1):
        exe = temp / f'test-{hold}'
        subprocess.run(['clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        f'-DSLEEP_KEEP_MODULE={hold}', '-I'+str(ROOT/'code'),
                        '-I'+str(ROOT/'sdk/portable/include'), str(temp/'test.c'),
                        '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
print('Sleep canary PASS: RAM/PSRAM corruption, missing expiry and module WFI detected')
