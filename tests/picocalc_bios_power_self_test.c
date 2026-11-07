#include "power_status.h"
#include "hal_interface.h"
#include "regs.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

I2C_HandleTypeDef hi2c2;
static uint8_t regs[24],pmu[2];
static uint32_t now,reads;
static int failed;
uint32_t uptime_ms(void) { return now; }
uint8_t* reg_raw_access(void) { return regs; }
int HAL_I2C_Mem_Read(I2C_HandleTypeDef* bus,uint16_t address,uint16_t reg,
    uint16_t address_size,uint8_t* bytes,uint16_t size,uint32_t timeout) {
    assert(bus==&hi2c2 && address==0x68 && reg==0 && address_size==1);
    assert(size==2 && timeout==4);++reads;
    if(failed) return HAL_ERROR;
    memcpy(bytes,pmu,2);return HAL_OK;
}

int main(void) {
    for(unsigned s1=0;s1<256;++s1) for(unsigned s2=0;s2<256;++s2) {
        const unsigned mode=(s2/32)%4,phase=s2%8;
        uint8_t expected=BIOS_POWER_TAG;
        if(mode!=3 && phase<=5) {
            expected|=BIOS_POWER_VALID;
            if(s1&8) expected|=BIOS_POWER_BATTERY;
            const int external=(s1&32) && !(s2&8);
            if(external) expected|=BIOS_POWER_EXTERNAL;
            if(external && (s1&8)) {
                if(phase==4) expected|=BIOS_POWER_COMPLETE;
                else if(mode==1) expected|=BIOS_POWER_CHARGING;
            }
        }
        assert(bios_power_from_axp2101((int)s1,(int)s2)==expected);
        assert(bios_power_valid_encoding(expected));
    }
    assert(bios_power_from_axp2101(-1,0)==BIOS_POWER_TAG);
    assert(bios_power_from_axp2101(0,256)==BIOS_POWER_TAG);
    for(unsigned raw=0;raw<256;++raw) {
        const int tagged=(raw&0xE0)==0xA0,valid=(raw&16)!=0;
        const int charge=(raw&12)!=0,contradiction=(raw&12)==12;
        const int sane=tagged && (valid?(!contradiction && (!charge || (raw&3)==3)):raw==0xA0);
        assert(bios_power_valid_encoding((uint8_t)raw)==sane);
    }
    // Same percent throughout: VBUS, charging, DONE and unplug are independent.
    regs[REG_ID_BAT]=75;pmu[0]=8;pmu[1]=0x40;bios_power_refresh(1);
    assert(regs[BIOS_POWER_REG]==0xB1 && regs[REG_ID_BAT]==75);
    pmu[0]=0x28;pmu[1]=0x22;bios_power_refresh(1);
    assert(regs[BIOS_POWER_REG]==0xB7 && regs[REG_ID_BAT]==(75|128));
    pmu[1]=4;bios_power_refresh(1);
    assert(regs[BIOS_POWER_REG]==0xBB && regs[REG_ID_BAT]==75);
    pmu[1]=5;bios_power_refresh(1);
    assert(regs[BIOS_POWER_REG]==0xB3); // External, stopped, not DONE.
    regs[REG_ID_BAT]|=128;pmu[0]=8;pmu[1]=0x44;bios_power_refresh(1);
    assert(regs[BIOS_POWER_REG]==0xB1 && regs[REG_ID_BAT]==75); // Stale DONE after unplug.
    pmu[0]=0x20;pmu[1]=4;bios_power_refresh(1);
    assert(regs[BIOS_POWER_REG]==0xB2); // External without batteries, not full.
    pmu[0]=0x28;pmu[1]=0x22;failed=1;bios_power_refresh(1);
    assert(regs[BIOS_POWER_REG]==BIOS_POWER_TAG && !(regs[REG_ID_BAT]&128));
    const unsigned count=reads;bios_power_refresh(0);assert(reads==count);
    failed=0;now=UINT32_MAX-100;bios_power_refresh(1);
    const unsigned before=reads;now+=499;bios_power_poll(1);assert(reads==before);
    ++now;bios_power_poll(1);assert(reads==before+1); // Timer wrap.
    assert(regs[BIOS_POWER_REG]==0xB7);
    puts("PicoCalc Southbridge power: 65536 PMU states, transitions, I2C failure/offline and timer wrap PASS");
}
