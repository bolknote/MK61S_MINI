#include "pmu_async.h"
#include "regs.h"

extern I2C_HandleTypeDef hi2c2;
extern volatile uint8_t pmu_irq;

/* Byte transactions avoid the F1 two-byte ACK/BTF corner. Re-read both
 * status bytes at the end; publish only one coherent foreground snapshot. */
static const uint8_t sample_regs[]={0x00,0x01,0xA4,0x48,0x49,0x4A,0x69,0x10,0x40,0x41,0x42,0x00,0x01};
static uint8_t cache[256],valid[32],wanted[256],dirty[32],needed[32];
static uint8_t sample[sizeof(sample_regs)],sample_at,scanning,force_scan;
static uint32_t sample_generation,io_generation,next_sample,deadline,next_recovery;
static uint32_t ready_deadline;
static uint8_t ready_waiting;
static uint8_t running,suspended,stopping,snapshot_valid,irq_ready,last_online;
static volatile uint8_t io_active,io_done,io_failed;
static uint8_t io_byte,io_reg,io_write,io_kind; /* kind: 0=demand, 1=snapshot */
static uint8_t recovering,recovery_step,recovery_clocks;
static uint32_t gpio_saved,recovery_due;
static volatile bios_pmu_statistics statistics;

static int due(uint32_t now,uint32_t at) { return (int32_t)(now-at)>=0; }
static int bit(const uint8_t* map,unsigned reg) { return (map[reg>>3]>>(reg&7))&1; }
static void set(uint8_t* map,unsigned reg) { map[reg>>3]|=(uint8_t)(1U<<(reg&7)); }
static void unset(uint8_t* map,unsigned reg) { map[reg>>3]&=(uint8_t)~(1U<<(reg&7)); }
static int first(const uint8_t* map) {
    for(unsigned byte=0;byte<32;++byte) if(map[byte])
        for(unsigned b=0;b<8;++b) if(map[byte]&(1U<<b)) return (int)(byte*8+b);
    return -1;
}
static int irq_reg(unsigned reg) { return reg>=0x48 && reg<=0x4A; }
static int pending_ack(void) {
    for(unsigned reg=0x48;reg<=0x4A;++reg)
        if(bit(dirty,reg) || (io_active && io_write && io_reg==reg)) return 1;
    return 0;
}
static void unknown(void) {
    snapshot_valid=irq_ready=0;
    reg_raw_access()[BIOS_POWER_REG]=BIOS_POWER_TAG;
    reg_raw_access()[REG_ID_BAT]=0x7F; /* Unknown, never an uninitialized 0%. */
}
static void restart_sample(void) {
    ++sample_generation;sample_at=scanning=0;force_scan=1;
}
static void irq_enable(void) {
    HAL_NVIC_SetPriority(I2C2_EV_IRQn,2,0);HAL_NVIC_SetPriority(I2C2_ER_IRQn,2,0);
    HAL_NVIC_ClearPendingIRQ(I2C2_EV_IRQn);HAL_NVIC_ClearPendingIRQ(I2C2_ER_IRQn);
    HAL_NVIC_EnableIRQ(I2C2_EV_IRQn);HAL_NVIC_EnableIRQ(I2C2_ER_IRQn);
}
static void irq_disable(void) {
    HAL_NVIC_DisableIRQ(I2C2_EV_IRQn);HAL_NVIC_DisableIRQ(I2C2_ER_IRQn);
    I2C2->CR2&=~(I2C_CR2_ITEVTEN|I2C_CR2_ITBUFEN|I2C_CR2_ITERREN);
}
static void restore_bus(void) {
    /* Touch only the two PMU pins. Keyboard GPIO/I2C1 and UART3 are separate. */
    HAL_GPIO_WritePin(GPIOB,GPIO_PIN_10|GPIO_PIN_11,GPIO_PIN_SET);
    GPIOB->CRH=(GPIOB->CRH&~0x0000FF00U)|gpio_saved;
    I2C2->CR1=I2C_CR1_SWRST;I2C2->CR1=0;
    hi2c2.State=HAL_I2C_STATE_RESET;hi2c2.Mode=HAL_I2C_MODE_NONE;hi2c2.Lock=HAL_UNLOCKED;
    (void)HAL_I2C_Init(&hi2c2); /* Register setup only; no BUSY/byte wait. */
    irq_enable();
}
static void abort_io(void) {
    irq_disable();
    I2C2->CR1|=I2C_CR1_STOP;I2C2->CR1&=~I2C_CR1_PE;
    if(io_active && io_write && !bit(dirty,io_reg)) {
        wanted[io_reg]=io_byte;set(dirty,io_reg);
    }
    io_active=io_done=io_failed=0;__DMB();
}
static void begin_recovery(uint32_t now,uint32_t error) {
    statistics.last_error=error;++statistics.errors;
    unknown();restart_sample();abort_io();ready_waiting=0;
    gpio_saved=GPIOB->CRH&0x0000FF00U;
    HAL_GPIO_WritePin(GPIOB,GPIO_PIN_10|GPIO_PIN_11,GPIO_PIN_SET);
    /* Open-drain GPIO, 2MHz: writing SET releases the wire, never drives high. */
    GPIOB->CRH=(GPIOB->CRH&~0x0000FF00U)|0x00006600U;
    recovering=1;recovery_step=recovery_clocks=0;recovery_due=now+1;
    ++statistics.recoveries;
}
static void recover_poll(uint32_t now) {
    if(!due(now,recovery_due)) return;
    recovery_due=now+1; /* One edge per foreground turn, no delay or spin. */
    if(recovery_step==0 || recovery_step==2) {
        if(HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_10)!=GPIO_PIN_SET) {
            ++statistics.recovery_failures;restore_bus();recovering=0;next_recovery=now+1000;return;
        }
        if(recovery_step==2) ++recovery_clocks;
        if(HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_11)==GPIO_PIN_RESET && recovery_clocks<9) {
            HAL_GPIO_WritePin(GPIOB,GPIO_PIN_10,GPIO_PIN_RESET);recovery_step=1;return;
        }
        /* STOP: SDA low while SCL low, then release SCL and finally SDA. */
        HAL_GPIO_WritePin(GPIOB,GPIO_PIN_10|GPIO_PIN_11,GPIO_PIN_RESET);
        recovery_step=3;return;
    }
    if(recovery_step==1 || recovery_step==3) {
        HAL_GPIO_WritePin(GPIOB,GPIO_PIN_10,GPIO_PIN_SET);
        recovery_step=(uint8_t)(recovery_step==1?2:4);return;
    }
    if(recovery_step==4) {
        if(HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_10)!=GPIO_PIN_SET) {
            ++statistics.recovery_failures;restore_bus();recovering=0;next_recovery=now+1000;return;
        }
        HAL_GPIO_WritePin(GPIOB,GPIO_PIN_11,GPIO_PIN_SET);recovery_step=5;return;
    }
    const int released=HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_11)==GPIO_PIN_SET;
    restore_bus();recovering=0;next_recovery=now+(released?10U:1000U);
    if(!released) ++statistics.recovery_failures;
}
static void publish(uint32_t now) {
    const unsigned end=sizeof(sample_regs)-2;
    const uint8_t power=bios_power_from_axp2101(sample[end],sample[end+1]);
    if(((sample[0]^sample[end])&0x28) || ((sample[1]^sample[end+1])&0x6F) || !(power&BIOS_POWER_VALID)) {
        ++statistics.incoherent;unknown();next_sample=now+50;force_scan=0;return;
    }
    for(unsigned i=0;i<end;++i) {
        const unsigned reg=sample_regs[i];
        if(!bit(dirty,reg)) {cache[reg]=sample[i];set(valid,reg);}
    }
    cache[0]=sample[end];cache[1]=sample[end+1];
    bios_pmu_sync_irq_masks();
    uint8_t level=(power&BIOS_POWER_BATTERY) && sample[2]<=100?sample[2]:0x7F;
    if(power&BIOS_POWER_CHARGING) level|=0x80;
    reg_raw_access()[REG_ID_BAT]=level;
    reg_raw_access()[BIOS_POWER_REG]=power;
    snapshot_valid=irq_ready=1;++statistics.snapshots;
    if((cache[0x48]|cache[0x49]|cache[0x4A])!=0) pmu_irq=1;
    next_sample=now+BIOS_POWER_POLL_MS;force_scan=0;
}
static void irq_complete(void) {
    if(io_active && (hi2c2.State==HAL_I2C_STATE_READY || hi2c2.ErrorCode!=HAL_I2C_ERROR_NONE)) {
        io_failed=(uint8_t)(hi2c2.ErrorCode!=HAL_I2C_ERROR_NONE);
        __DMB();io_done=1;
    }
}
void I2C2_EV_IRQHandler(void) {HAL_I2C_EV_IRQHandler(&hi2c2);irq_complete();}
void I2C2_ER_IRQHandler(void) {HAL_I2C_ER_IRQHandler(&hi2c2);irq_complete();}

static int begin_io(uint32_t now,unsigned reg,int write,int sample_read) {
    /* HAL *_IT itself has a 25ms BUSY wait. Do not enter it on a busy bus.
     * All runtime legacy accesses are cached, so no other foreground owner
     * can start I2C2 between this guard and the single IT submission. */
    if(hi2c2.State!=HAL_I2C_STATE_READY || hi2c2.Mode!=HAL_I2C_MODE_NONE || hi2c2.Lock!=HAL_UNLOCKED ||
       (I2C2->SR2&I2C_SR2_BUSY) ||
       HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_10)!=GPIO_PIN_SET || HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_11)!=GPIO_PIN_SET) {
        /* STOP may still own BUSY for a few wire clocks after HAL reports
         * READY. Yield during that normal tail; recover only if it persists. */
        if(!ready_waiting) {
            ready_waiting=1;ready_deadline=now+4;++statistics.busy_guards;
        } else if(due(now,ready_deadline)) begin_recovery(now,HAL_I2C_ERROR_TIMEOUT);
        return 0;
    }
    ready_waiting=0;
    io_reg=(uint8_t)reg;io_write=(uint8_t)write;io_kind=(uint8_t)sample_read;
    io_generation=sample_generation;io_byte=write?wanted[reg]:0;
    if(write) unset(dirty,reg);
    io_done=io_failed=0;deadline=now+4;__DMB();io_active=1;
    HAL_StatusTypeDef result=write?
        HAL_I2C_Mem_Write_IT(&hi2c2,0x68,(uint16_t)reg,I2C_MEMADD_SIZE_8BIT,&io_byte,1):
        HAL_I2C_Mem_Read_IT(&hi2c2,0x68,(uint16_t)reg,I2C_MEMADD_SIZE_8BIT,&io_byte,1);
    if(result!=HAL_OK) {begin_recovery(now,hi2c2.ErrorCode);return 0;}
    ++statistics.starts;return 1;
}
void bios_power_refresh(uint8_t online) {
    if(!running) {
        running=1;unknown();irq_enable();next_recovery=uptime_ms();
    }
    last_online=online;force_scan=1;
}
void bios_power_poll(uint8_t online) {
    if(!running) bios_power_refresh(online);
    last_online=online;if(suspended) return;
    const uint32_t now=uptime_ms();
    if(recovering) {recover_poll(now);return;}
    if(io_active) {
        if(!io_done) {
            if(due(now,deadline)) {++statistics.timeouts;begin_recovery(now,HAL_I2C_ERROR_TIMEOUT);}
            return;
        }
        __DMB();
        if(io_failed) {begin_recovery(now,hi2c2.ErrorCode);return;}
        io_active=io_done=0;++statistics.completions;
        if(io_write) {
            if(irq_reg(io_reg)) cache[io_reg]&=(uint8_t)~io_byte;
            else {cache[io_reg]=io_byte;set(valid,io_reg);}
        } else if(io_kind) {
            if(io_generation==sample_generation && scanning) {
                sample[sample_at++]=io_byte;
                if(sample_at==sizeof(sample_regs)) {scanning=0;publish(now);}
            }
        } else {cache[io_reg]=io_byte;set(valid,io_reg);unset(needed,io_reg);}
    }
    if(!due(now,next_recovery)) return;
    if(!online) {unknown();return;}
    /* A low IRQ level remains observable if a new event arrived while the
     * previous snapshot was being acknowledged. Never clear the GPIO flag. */
    if(!pending_ack() && HAL_GPIO_ReadPin(GPIOC,GPIO_PIN_9)==GPIO_PIN_RESET) pmu_irq=1;
    if(pmu_irq && !irq_ready) force_scan=1;
    int reg=bit(dirty,0x10)?0x10:first(dirty);
    if(reg>=0) {begin_io(now,(unsigned)reg,1,0);return;}
    reg=first(needed);
    if(reg>=0) {begin_io(now,(unsigned)reg,0,0);return;}
    if(stopping) return;
    if(!scanning && (force_scan || due(now,next_sample))) {scanning=1;sample_at=0;}
    if(scanning) begin_io(now,sample_regs[sample_at],0,1);
}

static int range_ok(I2C_HandleTypeDef* bus,uint16_t dev,uint16_t reg,uint16_t address_size,const uint8_t* data,uint16_t count) {
    return bus==&hi2c2 && dev==0x68 && address_size==I2C_MEMADD_SIZE_8BIT && data && count && reg<256 && count<=256-reg;
}
HAL_StatusTypeDef bios_pmu_mem_read(I2C_HandleTypeDef* bus,uint16_t dev,uint16_t reg,uint16_t address_size,uint8_t* data,uint16_t count,uint32_t timeout) {
    if(!running) {
        const HAL_StatusTypeDef status=HAL_I2C_Mem_Read(bus,dev,reg,address_size,data,count,timeout);
        if(status==HAL_OK && range_ok(bus,dev,reg,address_size,data,count))
            for(unsigned i=0;i<count;++i) {cache[reg+i]=data[i];set(valid,reg+i);}
        return status;
    }
    if(!range_ok(bus,dev,reg,address_size,data,count)) return HAL_ERROR;
    for(unsigned i=0;i<count;++i)
        if(!bit(valid,reg+i) && !bit(dirty,reg+i) && !(io_active && io_write && io_reg==reg+i)) {
            set(needed,reg+i);return HAL_BUSY;
        }
    for(unsigned i=0;i<count;++i) {
        const unsigned at=reg+i;
        data[i]=!irq_reg(at) && bit(dirty,at)?wanted[at]:
            !irq_reg(at) && io_active && io_write && io_reg==at?io_byte:cache[at];
    }
    ++statistics.cached_reads;return HAL_OK;
}
HAL_StatusTypeDef bios_pmu_mem_write(I2C_HandleTypeDef* bus,uint16_t dev,uint16_t reg,uint16_t address_size,uint8_t* data,uint16_t count,uint32_t timeout) {
    if(!running) {
        const HAL_StatusTypeDef status=HAL_I2C_Mem_Write(bus,dev,reg,address_size,data,count,timeout);
        if(status==HAL_OK && range_ok(bus,dev,reg,address_size,data,count))
            for(unsigned i=0;i<count;++i) if(!irq_reg(reg+i)) {cache[reg+i]=data[i];set(valid,reg+i);}
        return status;
    }
    if(!range_ok(bus,dev,reg,address_size,data,count)) return HAL_ERROR;
    for(unsigned i=0;i<count;++i) {
        const unsigned at=reg+i;uint8_t value=data[i];
        if(irq_reg(at)) {
            value&=bit(valid,at)?cache[at]:0;
            if(!value) continue;
            cache[at]&=(uint8_t)~value;
            if(bit(dirty,at)) value|=wanted[at];
        } else if(!bit(dirty,at) && ((io_active && io_write && io_reg==at && io_byte==value) ||
                  (!(io_active && io_write && io_reg==at) && bit(valid,at) && cache[at]==value))) continue;
        if(bit(dirty,at) && wanted[at]==value) continue;
        wanted[at]=value;set(dirty,at);++statistics.queued_writes;
        restart_sample();
    }
    return HAL_OK;
}
uint8_t bios_pmu_legacy_ready(void) {return snapshot_valid && (!pmu_irq || irq_ready);}
void bios_pmu_legacy_complete(void) {if(!pmu_irq) irq_ready=0;}
void bios_power_legacy_battery(uint8_t value) {if(!running) reg_set_value(REG_ID_BAT,value);}

void bios_pmu_quiesce(void) {
    /* Called only after Pico/native execution has stopped, at the explicit
     * sleep boundary. Flush wake-IRQ controls while clocks/interrupts run.
     * Normal foreground operation never waits, including BUSY/fault cases. */
    stopping=1;const uint32_t started=uptime_ms();
    while((io_active || recovering || first(dirty)>=0) && (uint32_t)(uptime_ms()-started)<100) {
        bios_power_poll(last_online);__WFI();
    }
    if(recovering) {restore_bus();recovering=0;}
    abort_io();suspended=1;unknown();
}
void bios_pmu_resume(void) {
    suspended=stopping=0;force_scan=1;next_recovery=uptime_ms();irq_enable();unknown();
}
const volatile bios_pmu_statistics* bios_pmu_counters(void) {return &statistics;}
