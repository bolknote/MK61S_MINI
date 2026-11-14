#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint8_t backing[SPECTRUM_EXTERNAL_BYTES],cache[49152],rom[16384],font[768];
static spectrum machine;
static spectrum_memory memory;
static uint8_t disk[655360],disk_cache[SPECTRUM_DISK_CACHE_BYTES],small_pages[2*SPECTRUM_CACHE_PAGE_BYTES];
static unsigned mapped_backend;
static bool rd(void* p,uint32_t at,uint8_t* out,uint32_t n) { memcpy(out,(uint8_t*)p+at,n);return true; }
static bool wr(void* p,uint32_t at,const uint8_t* in,uint32_t n) { memcpy((uint8_t*)p+at,in,n);return true; }
static bool clear(void* p,uint32_t at,uint32_t n) { memset((uint8_t*)p+at,0,n);return true; }
static void fdc_test(void) {
    spectrum_fdc f={0};f.io=(spectrum_disk_io){disk,sizeof(disk),rd,wr,false,80,2};
    spectrum_fdc_reset(&f);for(unsigned i=0;i<256;++i) disk[i]=(uint8_t)i;
    spectrum_fdc_write(&f,0x1F,0x80,0);
    for(unsigned i=0;i<256;++i) assert(spectrum_fdc_read(&f,0x7F,700+i*112)==(uint8_t)i);
    assert(!f.busy && f.irq);
    spectrum_fdc_write(&f,0x5F,2,30000);spectrum_fdc_write(&f,0x1F,0xA0,30000);
    for(unsigned i=0;i<256;++i) spectrum_fdc_write(&f,0x7F,(uint8_t)~i,30700+i*112);
    assert(!f.busy && !f.status);for(unsigned i=0;i<256;++i) assert(disk[256+i]==(uint8_t)~i);
    f.io.readonly=true;spectrum_fdc_write(&f,0x1F,0xA0,60000);assert(!f.busy && (f.status&64));
    f.io.readonly=false;spectrum_fdc_write(&f,0x1F,0x80,61000);
    assert(spectrum_fdc_read(&f,0xFF,61700)&64);
    assert(spectrum_fdc_read(&f,0x1F,63000)&4);assert(!f.busy);
    spectrum_fdc_write(&f,0x7F,1,64000);spectrum_fdc_write(&f,0x1F,0x10,64000);
    assert(f.head==1 && f.track==1 && f.busy);spectrum_fdc_read(&f,0x1F,85000);assert(!f.busy);
    spectrum_fdc_write(&f,0x1F,0,90000);spectrum_fdc_read(&f,0x1F,111000);assert(!f.head && !f.track);
    /* Side select is inverted on Beta 128. */
    disk[4096]=0xA9;spectrum_fdc_write(&f,0xFF,0x2C,112000);spectrum_fdc_write(&f,0x5F,1,112000);
    spectrum_fdc_write(&f,0x1F,0x80,112000);assert(spectrum_fdc_read(&f,0x7F,112700)==0xA9);
    spectrum_fdc_write(&f,0x1F,0xD0,112800);assert(!f.busy && !f.drq);
    spectrum_fdc_reset(&f);spectrum_fdc_write(&f,0x1F,0x90,0);
    for(unsigned i=0;i<512;++i) {
        const unsigned time=i<256?700+i*112:700+255*112+700+(i-256)*112;
        assert(spectrum_fdc_read(&f,0x7F,time)==disk[i]);
    }
    spectrum_fdc_write(&f,0x1F,0xD0,60000);
    spectrum_fdc_write(&f,0x1F,0xC0,60001);
    uint16_t crc=0xFFFF;const uint8_t id[]={0xA1,0xA1,0xA1,0xFE,0,0,3,1};
    for(unsigned i=0;i<sizeof(id);++i) crc=spectrum_crc16(crc,id[i]);
    uint8_t address[6];for(unsigned i=0;i<6;++i) address[i]=spectrum_fdc_read(&f,0x7F,60701+i*112);
    assert(address[0]==0 && address[1]==0 && address[2]==3 && address[3]==1 && address[4]==(crc>>8) && address[5]==(crc&255));
    assert(f.sector==0);
    /* Format a complete track using WD1793 address/data mark conventions. */
    uint8_t track[6250];memset(track,0x4E,sizeof(track));
    for(unsigned sector=0;sector<16;++sector) {
        unsigned at=146+sector*372;track[at+15]=0xFE;track[at+16]=0;track[at+17]=0;track[at+18]=(uint8_t)(sector+1);track[at+19]=1;
        track[at+20]=0xF7;track[at+59]=0xFB;memset(track+at+60,0xE5,256);track[at+316]=0xF7;
    }
    spectrum_fdc_write(&f,0x1F,0xF0,70000);
    for(unsigned i=0;i<6250;++i) spectrum_fdc_write(&f,0x7F,track[i],70700+i*112);
    assert(!f.busy && !f.status);for(unsigned i=0;i<4096;++i) assert(disk[i]==0xE5);
    spectrum_fdc_write(&f,0x1F,0xE0,800000);
    for(unsigned i=0;i<6250;++i) {
        const uint8_t v=spectrum_fdc_read(&f,0x7F,800700+i*112);
        if(i==146+15) assert(v==0xFE);if(i==146+59) assert(v==0xFB);if(i==146+60) assert(v==0xE5);
    }
    assert(!f.busy && !f.status);
    puts("Beta Disk seek, sectors, writes, side, DRQ deadline, write protection: PASS");
}
static uint8_t spi_command(spectrum_spi* s,unsigned command,uint32_t arg,unsigned crc) {
    const uint8_t bytes[]={(uint8_t)(0x40|command),(uint8_t)(arg>>24),(uint8_t)(arg>>16),(uint8_t)(arg>>8),(uint8_t)arg,(uint8_t)crc};
    for(unsigned i=0;i<6;++i) spectrum_spi_transfer(s,bytes[i]);
    return spectrum_spi_transfer(s,255);
}
static void spi_test(void) {
    spectrum_spi s={0};s.io=(spectrum_disk_io){disk,sizeof(disk),rd,wr,false,0,0};
    spectrum_spi_reset(&s);assert(spectrum_spi_transfer(&s,0)==255);spectrum_spi_select(&s,0xFE);
    assert(spi_command(&s,0,0,0x95)==1);assert(spi_command(&s,8,0x1AA,0x87)==1);
    assert(spectrum_spi_transfer(&s,255)==0);assert(spectrum_spi_transfer(&s,255)==0);
    assert(spectrum_spi_transfer(&s,255)==1);assert(spectrum_spi_transfer(&s,255)==0xAA);
    assert(spi_command(&s,55,0,255)==1);assert(spi_command(&s,41,0x40000000,255)==0);
    assert(spi_command(&s,17,0,255)==0);assert(spectrum_spi_transfer(&s,255)==0xFE);
    uint16_t crc=0;
    for(unsigned i=0;i<512;++i) { uint8_t v=spectrum_spi_transfer(&s,255);assert(v==disk[i]);crc=spectrum_crc16(crc,v); }
    assert(spectrum_spi_transfer(&s,255)==(crc>>8));assert(spectrum_spi_transfer(&s,255)==(crc&255));
    assert(spi_command(&s,24,2,255)==0);spectrum_spi_transfer(&s,0xFE);
    for(unsigned i=0;i<512;++i) spectrum_spi_transfer(&s,(uint8_t)(i^0xA5));
    spectrum_spi_transfer(&s,255);spectrum_spi_transfer(&s,255);assert(spectrum_spi_transfer(&s,255)==5);
    assert(spectrum_spi_transfer(&s,255)==0);assert(spectrum_spi_transfer(&s,255)==255);
    for(unsigned i=0;i<512;++i) assert(disk[1024+i]==(uint8_t)(i^0xA5));
    assert(s.reads==1 && s.writes==1);spectrum_spi_select(&s,255);assert(spectrum_spi_transfer(&s,0)==255);
    spectrum_spi_select(&s,0xFE);assert(spi_command(&s,18,0,255)==0);
    for(unsigned block=0;block<2;++block) {
        assert(spectrum_spi_transfer(&s,255)==0xFE);
        for(unsigned i=0;i<512;++i) assert(spectrum_spi_transfer(&s,255)==disk[block*512+i]);
        spectrum_spi_transfer(&s,255);spectrum_spi_transfer(&s,255);
    }
    assert(spi_command(&s,12,0,255)==255);assert(spectrum_spi_transfer(&s,255)==0);
    assert(spectrum_spi_transfer(&s,255)==255);
    assert(spi_command(&s,25,3,255)==0);
    for(unsigned block=0;block<2;++block) {
        spectrum_spi_transfer(&s,0xFC);for(unsigned i=0;i<512;++i) spectrum_spi_transfer(&s,(uint8_t)(block+31));
        spectrum_spi_transfer(&s,255);spectrum_spi_transfer(&s,255);assert(spectrum_spi_transfer(&s,255)==5);
        spectrum_spi_transfer(&s,255);spectrum_spi_transfer(&s,255);
    }
    spectrum_spi_transfer(&s,0xFD);assert(!s.write_mode && s.writes==3 && disk[1536]==31 && disk[2048]==32);
    s.io.readonly=true;assert(spi_command(&s,24,0,255)==4 && !s.write_mode);
    assert(spi_command(&s,59,1,255)==0);assert(spi_command(&s,17,0,0)==8);
    puts("DivMMC SDHC initialization, sector CRC, read/write, chip select: PASS");
}
static void load(const char* dir,const char* name,uint8_t* out,unsigned n) {
    char path[1024];snprintf(path,sizeof(path),"%s/%s",dir,name);FILE* f=fopen(path,"rb");assert(f);
    assert(fread(out,1,n,f)==n);fclose(f);
}
static void setup(void) {
    memset(&machine,0,sizeof(machine));machine.ram=cache;machine.rom=rom;
    const spectrum_memory_io io={backing,rd,wr,clear};
    if(mapped_backend==2) {
        uint8_t* tails[]={cache+15360,cache+31744,cache+40960};
        assert(spectrum_memory_init_external_rom(&memory,cache,cache+16384,tails,cache+32768,io));
    } else if(mapped_backend) assert(spectrum_memory_init_mapped(&memory,cache,small_pages,cache+32768,backing+SPECTRUM_ROM_BASE,backing+SPECTRUM_ROM_BASE+16384,io));
    else assert(spectrum_memory_init(&memory,cache,rom,io));
    spectrum_attach_memory(&machine,&memory);machine.pentagon=false;
    if(mapped_backend==1) { machine.disk.direct_rom[SPECTRUM_DISK_BETA]=backing+SPECTRUM_TRDOS_ROM;machine.disk.direct_rom[SPECTRUM_DISK_DIVMMC]=backing+SPECTRUM_DIV_ROM; }
}
static char display[24*33+1];
static void screen(void) {
    for(unsigned row=0;row<24;++row) {
        char line[33];line[32]=0;
        for(unsigned col=0;col<32;++col) {
            int best=-1;
            for(unsigned c=32;c<128;++c) {
                bool match=true;
                for(unsigned y=0;y<8;++y) {
                    const unsigned py=row*8+y,at=((py&192)<<5)|((py&7)<<8)|((py&56)<<2)|col;
                    if(cache[at]!=font[(c-32)*8+y]) match=false;
                }
                if(match) { best=(int)c;break; }
            }
            line[col]=best<0?'?':(char)best;
        }
        memcpy(display+row*33,line,32);display[row*33+32]='\n';
    }
}
static void tap(unsigned key) {
    uint8_t keys[32]={0};keys[key/8]|=1U<<(key&7);spectrum_keyboard(&machine,keys);spectrum_run(&machine,4*69888);
    memset(keys,0,32);spectrum_keyboard(&machine,keys);spectrum_run(&machine,4*69888);
}
static void real_boot(const char* romdir,const char* extras) {
    load(romdir,"48.rom",backing+SPECTRUM_ROM_BASE,16384);memcpy(backing+SPECTRUM_ROM_BASE+16384,backing+SPECTRUM_ROM_BASE,16384);
    memcpy(font,backing+SPECTRUM_ROM_BASE+0x3D00,768);
    load(extras,"trdos.rom",backing+SPECTRUM_TRDOS_ROM,16384);
    load(extras,"esxmmc.rom",backing+SPECTRUM_DIV_ROM,8192);setup();
    machine.disk.fdc.io=(spectrum_disk_io){disk,sizeof(disk),rd,wr,false,80,2};
    memset(disk,0,sizeof(disk));disk[0x8E2]=1;disk[0x8E3]=0x16;disk[0x8E5]=0xF0;disk[0x8E6]=9;disk[0x8E7]=0x10;
    assert(spectrum_disk_mode(&machine,SPECTRUM_DISK_BETA));assert(spectrum_disk_cache_begin(&machine,disk_cache));spectrum_run(&machine,200*69888);
    /* Enter TR-DOS through its standard BASIC entry point after ROM init. */
    machine.cpu.pc=15616;spectrum_run(&machine,250*69888);
    screen();assert(strstr(display,"TR-DOS Ver") && strstr(display,"A>"));
    /* Feed CAT through the ROM's decoded-key interface (the physical matrix
     * and BASIC tokenizer are covered independently by spectrum_self_test). */
    cache[0x1C08]=0xCF;cache[0x1C3B]|=32;spectrum_run(&machine,10*69888);
    cache[0x1C08]=13;cache[0x1C3B]|=32;spectrum_run(&machine,100*69888);
    assert(cache[0x1CC8]&1); // CAT recognized the formatted, writable disk.
    disk[15*256]=0x57;disk[15*256+1]=0xA9;
    const uint8_t call_dos[]={0xAF,0x01,1,0,0xCD,0x13,0x3D,0x01,5,1,0x11,15,0,0x21,0,0x80,0xCD,0x13,0x3D,0xF3,0x76};memcpy(cache+0x5000,call_dos,sizeof(call_dos));
    machine.cpu.pc=0x9000;machine.cpu.halted=false;machine.cpu.sp=0xFFFC;
    machine.cpu.b=1;machine.cpu.c=5;machine.cpu.d=machine.cpu.e=0;machine.cpu.h=0x80;machine.cpu.l=0;
    spectrum_run(&machine,100*69888);
    if(!machine.cpu.halted || cache[0x4000]!=0x57) { screen();fprintf(stderr,"TRDOS read PC=%04X status=%02X mode=%02X\n%s",machine.cpu.pc,machine.disk.fdc.status,cache[0x1CC8],display); }
    assert(machine.cpu.halted && cache[0x4000]==0x57 && cache[0x4001]==0xA9 && !machine.disk.fdc.status);
    cache[0x4000]=0xDA;cache[0x4001]=0x75;cache[0x5000+8]=6;cache[0x5000+11]=14;
    machine.cpu.pc=0x9000;machine.cpu.halted=false;spectrum_run(&machine,100*69888);
    if(!machine.cpu.halted || disk[14*256]!=0xDA || disk[14*256+1]!=0x75 || machine.disk.fdc.status)
        fprintf(stderr,"TRDOS write PC=%04X status=%02X data=%02X%02X system=%02X cmd=%02X DRQ=%u sector=%u head=%u mode=%02X B=%u\n",machine.cpu.pc,machine.disk.fdc.status,disk[14*256],disk[14*256+1],machine.disk.fdc.system,machine.disk.fdc.command,machine.disk.fdc.drq,machine.disk.fdc.sector,machine.disk.fdc.head,cache[0x1CC8],machine.cpu.b);
    assert(machine.cpu.halted && disk[14*256]==0xDA && disk[14*256+1]==0x75 && !machine.disk.fdc.status);
    assert(spectrum_disk_cache_end(&machine));
    char path[1024];snprintf(path,sizeof(path),"%s/ESXDOS.img",extras);FILE* f=fopen(path,"rb");assert(f);
    fseek(f,0,SEEK_END);unsigned size=(unsigned)ftell(f);rewind(f);uint8_t* sd=malloc(size);assert(sd);assert(fread(sd,1,size,f)==size);fclose(f);
    setup();machine.disk.spi.io=(spectrum_disk_io){sd,size,rd,wr,false,0,0};
    assert(spectrum_disk_mode(&machine,SPECTRUM_DISK_DIVMMC));assert(spectrum_disk_cache_begin(&machine,disk_cache));spectrum_reset(&machine);
    spectrum_run(&machine,600*69888);
    assert(machine.disk.spi.reads>10 && !memory.fault);
    tap('.');tap('l');tap('s');tap(13);spectrum_run(&machine,100*69888);screen();
    assert(strstr(display,"HELLO.TXT") && strstr(display,"SYS"));
    const char* mkdir=".mkdir test\r";while(*mkdir) tap((unsigned char)*mkdir++);
    spectrum_run(&machine,100*69888);assert(machine.disk.spi.writes>0);
    tap('.');tap('l');tap('s');tap(13);spectrum_run(&machine,100*69888);screen();
    assert(strstr(display,"TEST") && strstr(display,"HELLO.TXT"));
    z80_gen_nmi(&machine.cpu);spectrum_run(&machine,100*69888);
    screen();assert(!memory.fault && !machine.cpu.nmi_pending && machine.disk.mapped);
    assert(strstr(display,"[1/4]") && strstr(display,"HELLO") && strstr(display,"SYS"));
    assert(spectrum_disk_cache_end(&machine));free(sd);puts("Real TR-DOS boot/sector read/write, esxDOS FAT boot, .ls, .mkdir/writeback, NMI: PASS");
}
int main(int argc,char** argv) {
    fdc_test();spi_test();if(argc==3)for(mapped_backend=0;mapped_backend<3;++mapped_backend)real_boot(argv[1],argv[2]);return 0;
}
