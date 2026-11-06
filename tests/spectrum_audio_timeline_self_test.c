#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static spectrum lagging,reference;
static uint8_t ram[2][49152],rom[16384];
static unsigned yields;
static void configure(spectrum* s,uint8_t* bytes) {
    spectrum_init(s,bytes,rom);
    spectrum_sound_write(s,0,0,70);spectrum_sound_write(s,0,1,0);
    spectrum_sound_write(s,0,7,0x3E);spectrum_sound_write(s,0,8,15);
}
static void timeline_keeps_running(void) {
    configure(&lagging,ram[0]);configure(&reference,ram[1]);
    spectrum_sound_begin(&lagging,NULL,NULL);spectrum_sound_begin(&reference,NULL,NULL);
    reference.cpu.cyc=400*140;spectrum_sound_publish(&reference);
    bool varied=false;uint32_t previous=0;
    for(unsigned i=0;i<400;++i) {
        const uint32_t a=spectrum_sound_render(&lagging),b=spectrum_sound_render(&reference);
        assert(a==b);if(i && a!=previous)varied=true;previous=a;
    }
    assert(varied && lagging.sound.time==56000 && reference.sound.time==56000);
    assert(atomic_load(&lagging.sound.starved)==400 && !atomic_load(&reference.sound.starved));
    spectrum_sound_end(&lagging);spectrum_sound_end(&reference);
}
static void render_late(void* unused) {
    (void)unused;assert(++yields<=2);(void)spectrum_sound_render(&lagging);
}
static void late_full_queue_can_drain(void) {
    configure(&lagging,ram[0]);spectrum_sound_begin(&lagging,render_late,NULL);
    // A slow producer may publish events behind the free-running sample clock.
    lagging.sound.time=56000;yields=0;
    for(unsigned i=0;i<=SPECTRUM_SOUND_QUEUE_EVENTS;++i) { lagging.cpu.cyc+=12;spectrum_sound_write(&lagging,0,8,i&15); }
    assert(yields==1);spectrum_sound_publish(&lagging);(void)spectrum_sound_render(&lagging);
    assert(atomic_load(&lagging.sound.read)==atomic_load(&lagging.sound.write) && lagging.ay.reg[8]==0);
    spectrum_sound_end(&lagging);
}
static void unpublished_and_wrapping_events(void) {
    configure(&lagging,ram[0]);spectrum_sound_begin(&lagging,NULL,NULL);
    lagging.cpu.cyc=12;spectrum_sound_write(&lagging,0,8,7);
    (void)spectrum_sound_render(&lagging);
    assert(!atomic_load(&lagging.sound.read) && lagging.ay.reg[8]==15);
    spectrum_sound_publish(&lagging);(void)spectrum_sound_render(&lagging);
    assert(atomic_load(&lagging.sound.read)==1 && lagging.ay.reg[8]==7 && lagging.sound.time==280);
    spectrum_sound_end(&lagging);
    lagging.cpu.cyc=UINT32_MAX-80;spectrum_sound_begin(&lagging,NULL,NULL);
    (void)spectrum_sound_render(&lagging);(void)spectrum_sound_render(&lagging);
    assert(lagging.sound.time==(uint32_t)(UINT32_MAX-80U+280U));
    lagging.cpu.cyc+=12;spectrum_sound_write(&lagging,1,8,9);spectrum_sound_publish(&lagging);
    (void)spectrum_sound_render(&lagging);assert(lagging.ay2.reg[8]==9);
    spectrum_sound_end(&lagging);
}
static void startup_gate(void) {
    configure(&lagging,ram[0]);configure(&reference,ram[1]);
    spectrum_sound_begin(&lagging,NULL,NULL);spectrum_sound_begin(&reference,NULL,NULL);
    spectrum_sound_clock(&lagging,false);
    for(unsigned i=0;i<500;++i)assert(!spectrum_sound_render(&lagging));
    assert(!lagging.sound.time && !atomic_load(&lagging.sound.starved));
    for(unsigned i=1;i<=20;++i) {
        lagging.cpu.cyc=reference.cpu.cyc=i*100;
        spectrum_sound_write(&lagging,2,0,i&1);spectrum_sound_write(&reference,2,0,i&1);
    }
    lagging.cpu.cyc=reference.cpu.cyc=14000;spectrum_sound_publish(&lagging);spectrum_sound_publish(&reference);
    spectrum_sound_clock(&lagging,true);
    for(unsigned i=0;i<SPECTRUM_SOUND_START_SAMPLES;++i)assert(!spectrum_sound_render(&lagging));
    assert(!lagging.sound.time && !atomic_load(&lagging.sound.read));
    for(unsigned i=0;i<100;++i)assert(spectrum_sound_render(&lagging)==spectrum_sound_render(&reference));
    assert(lagging.sound.time==14000);spectrum_sound_end(&lagging);spectrum_sound_end(&reference);
}
int main(int argc,char** argv) {
    if(argc==2 && !strcmp(argv[1],"late-full"))late_full_queue_can_drain();
    else {timeline_keeps_running();late_full_queue_can_drain();unpublished_and_wrapping_events();startup_gate();}
    puts("Audio clock: AY phase continues through underrun, late full queue drains, unpublished events stay queued, timestamps wrap: PASS");
}
