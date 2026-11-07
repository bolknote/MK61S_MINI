#include "pmu_async.h"
#include "regs.h"
#include "axp2101.h"
#include "keyboard.h"
#include "batt.h"
#ifdef MK61_PMU_TEST_ARM
#include "arm_test_support.h"
#else
#include <assert.h>
#include <stdio.h>
#endif
#include <string.h>

I2C_TypeDef test_i2c2;
GPIO_TypeDef test_gpiob,test_gpioc;
I2C_HandleTypeDef hi2c2;
volatile uint8_t pmu_irq;
static uint8_t registers[256],pmu[256];
static uint32_t now,sync_reads,sync_writes,it_calls,coproc_turns;
static unsigned runtime_started,irq_enabled,held_scl,held_sda,clock_edges,drop_io,error_io;
static unsigned status_transition;
static unsigned key_events,shift_pressed,blink_calls;
static int wfi_allowed;
static struct {unsigned active,write,reg;uint8_t* byte;uint32_t at;} pending;
static uint8_t pmu_online=1,uninhibit_pwr_button=1,stop_mode_active;
static uint32_t pmu_check_counter;
static void legacy(void);
static void key_cb(char key,enum key_state state) {assert((uint8_t)key==KEY_POWER && state==KEY_STATE_PRESSED);++key_events;}
uint8_t keyboard_get_shift(void) {return (uint8_t)shift_pressed;}
uint8_t* reg_raw_access(void) {return registers;}
uint8_t reg_get_value(enum reg_id reg) {return registers[reg];}
void reg_set_value(enum reg_id reg,uint8_t value) {registers[reg]=value;}
uint8_t reg_is_bit_set(enum reg_id reg,uint8_t value) {return registers[reg]&value;}
void reg_set_bit(enum reg_id reg,uint8_t value) {registers[reg]|=value;}
uint32_t uptime_ms(void) {return now;}
static void update_lines(void) {
    test_gpiob.IDR=(test_gpiob.IDR&~(uint32_t)(GPIO_PIN_10|GPIO_PIN_11))|
        ((!held_scl && (test_gpiob.ODR&GPIO_PIN_10))?GPIO_PIN_10:0)|
        ((!held_sda && (test_gpiob.ODR&GPIO_PIN_11))?GPIO_PIN_11:0);
    test_gpioc.IDR=(test_gpioc.IDR&~(uint32_t)GPIO_PIN_9)|
        (((pmu[0x48]&pmu[0x40])|(pmu[0x49]&pmu[0x41])|(pmu[0x4A]&pmu[0x42]))?0:GPIO_PIN_9);
}
void HAL_GPIO_WritePin(GPIO_TypeDef* port,uint16_t pins,GPIO_PinState value) {
    const uint32_t before=port->ODR;
    if(value==GPIO_PIN_SET)port->ODR|=pins;else port->ODR&=~(uint32_t)pins;
    if(port==GPIOB && (port->CRH&0xFF00)==0x6600 && !(before&GPIO_PIN_10) && (port->ODR&GPIO_PIN_10)) {
        ++clock_edges;if(held_sda)--held_sda;
    }
    update_lines();
}
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef* port,uint16_t pins) {update_lines();return (port->IDR&pins)?GPIO_PIN_SET:GPIO_PIN_RESET;}
unsigned LL_GPIO_IsOutputPinSet(GPIO_TypeDef* port,uint32_t pins) {return (port->ODR&pins)!=0;}
void LL_GPIO_SetOutputPin(GPIO_TypeDef* port,uint32_t pins) {port->ODR|=pins;}
void LL_GPIO_ResetOutputPin(GPIO_TypeDef* port,uint32_t pins) {port->ODR&=~pins;}
void led_blink_configure(uint8_t n,uint8_t state) {(void)n;(void)state;++blink_calls;}
static void check_args(I2C_HandleTypeDef* bus,uint16_t dev,uint16_t reg,uint16_t addr_size,uint16_t n) {
    assert(bus==&hi2c2 && dev==0x68 && reg<256 && addr_size==1 && n && reg+n<=256);
}
HAL_StatusTypeDef HAL_I2C_Mem_Read(I2C_HandleTypeDef* bus,uint16_t dev,uint16_t reg,uint16_t a,uint8_t* out,uint16_t n,uint32_t timeout) {
    assert(!runtime_started);assert(timeout<=60);check_args(bus,dev,reg,a,n);
    memcpy(out,pmu+reg,n);++sync_reads;return HAL_OK;
}
HAL_StatusTypeDef HAL_I2C_Mem_Write(I2C_HandleTypeDef* bus,uint16_t dev,uint16_t reg,uint16_t a,uint8_t* in,uint16_t n,uint32_t timeout) {
    assert(!runtime_started);assert(timeout<=60);check_args(bus,dev,reg,a,n);
    for(unsigned i=0;i<n;++i) if(reg+i>=0x48 && reg+i<=0x4A)pmu[reg+i]&=(uint8_t)~in[i];else pmu[reg+i]=in[i];
    ++sync_writes;return HAL_OK;
}
static HAL_StatusTypeDef submit(I2C_HandleTypeDef* bus,uint16_t dev,uint16_t reg,uint16_t a,uint8_t* byte,uint16_t n,unsigned write) {
    check_args(bus,dev,reg,a,n);assert(n==1);assert(!pending.active);
    assert(!(I2C2->SR2&I2C_SR2_BUSY)); /* Otherwise real HAL *_IT waits25ms. */
    assert(hi2c2.State==HAL_I2C_STATE_READY && hi2c2.Lock==HAL_UNLOCKED);
    assert(irq_enabled==3);pending.active=1;pending.write=write;pending.reg=reg;pending.byte=byte;pending.at=now+1;
    hi2c2.State=write?HAL_I2C_STATE_BUSY_TX:HAL_I2C_STATE_BUSY_RX;
    hi2c2.Mode=HAL_I2C_MODE_MEM;hi2c2.Lock=HAL_LOCKED;hi2c2.ErrorCode=0;++it_calls;
    return HAL_OK;
}
HAL_StatusTypeDef HAL_I2C_Mem_Read_IT(I2C_HandleTypeDef* b,uint16_t d,uint16_t r,uint16_t a,uint8_t* p,uint16_t n) {return submit(b,d,r,a,p,n,0);}
HAL_StatusTypeDef HAL_I2C_Mem_Write_IT(I2C_HandleTypeDef* b,uint16_t d,uint16_t r,uint16_t a,uint8_t* p,uint16_t n) {return submit(b,d,r,a,p,n,1);}
HAL_StatusTypeDef HAL_I2C_Init(I2C_HandleTypeDef* bus) {
    assert(bus==&hi2c2);pending.active=0;hi2c2.Instance=I2C2;
    hi2c2.State=HAL_I2C_STATE_READY;hi2c2.Mode=HAL_I2C_MODE_NONE;hi2c2.Lock=HAL_UNLOCKED;hi2c2.ErrorCode=0;
    I2C2->CR1=I2C_CR1_PE;I2C2->CR2=36;I2C2->SR2=0;I2C2->CCR=180;I2C2->TRISE=37;return HAL_OK;
}
void HAL_I2C_EV_IRQHandler(I2C_HandleTypeDef* bus) {
    assert(bus==&hi2c2 && pending.active);
    if(pending.write) {
        const unsigned r=pending.reg;
        if(r>=0x48 && r<=0x4A)pmu[r]&=(uint8_t)~*pending.byte;else pmu[r]=*pending.byte;
    } else {
        *pending.byte=pmu[pending.reg];
        if(status_transition && pending.reg==0xA4) {pmu[1]=0x22;status_transition=0;}
    }
    pending.active=0;hi2c2.State=HAL_I2C_STATE_READY;hi2c2.Mode=HAL_I2C_MODE_NONE;hi2c2.Lock=HAL_UNLOCKED;
}
void HAL_I2C_ER_IRQHandler(I2C_HandleTypeDef* bus) {
    assert(bus==&hi2c2);pending.active=0;hi2c2.State=HAL_I2C_STATE_READY;hi2c2.Mode=HAL_I2C_MODE_NONE;
    hi2c2.Lock=HAL_UNLOCKED;hi2c2.ErrorCode=HAL_I2C_ERROR_AF;
}
void HAL_NVIC_SetPriority(int irq,unsigned priority,unsigned sub) {assert((irq==33||irq==34)&&priority==2&&!sub);}
void HAL_NVIC_ClearPendingIRQ(int irq) {assert(irq==33||irq==34);}
void HAL_NVIC_EnableIRQ(int irq) {assert(irq==33||irq==34);irq_enabled|=(irq==33?1U:2U);}
void HAL_NVIC_DisableIRQ(int irq) {assert(irq==33||irq==34);irq_enabled&=~(irq==33?1U:2U);}
static void clock_tick(void) {
    ++now;
    if(pending.active && irq_enabled==3 && !drop_io && (int32_t)(now-pending.at)>=0) {
        if(error_io) {error_io=0;I2C2_ER_IRQHandler();}else I2C2_EV_IRQHandler();
    }
}
static void tick(void) {
    clock_tick();
    bios_power_poll(pmu_online);
    legacy(); /* Same ordering as the actual Southbridge main loop. */
    ++coproc_turns; /* Service M3 once per turn, even during PMU faults. */
}
static void advance(unsigned n) {while(n--)tick();}
void test_wfi(void) {assert(wfi_allowed);clock_tick();}

/* Generated directly from the candidate's real legacy PMU interpreter. */
#include "legacy_check.inc"

static void legacy(void) {
    if(bios_pmu_legacy_ready()) {check_pmu_int();bios_pmu_legacy_complete();}
}
static void setup(void) {
    test_gpiob.CRH=0xA5A5FF5A;test_gpiob.ODR=0xCC00;test_gpioc.IDR=GPIO_PIN_9;
    HAL_I2C_Init(&hi2c2);pmu[0]=0x28;pmu[1]=0x22;pmu[0xA4]=75;pmu[0x69]=0x35;pmu[0x10]=4;
    assert(AXP2101_enableIRQ(XPOWERS_AXP2101_ALL_IRQ)==HAL_OK);
    registers[REG_ID_INT_CFG]=INT_PWR_BTN;
    uint8_t value;assert(bios_pmu_mem_read(&hi2c2,0x68,0x69,1,&value,1,60)==HAL_OK);
    bios_power_refresh(1);runtime_started=1;
    assert(registers[BIOS_POWER_REG]==BIOS_POWER_TAG && registers[REG_ID_BAT]==127);
}
int main(int argc,char** argv) {
    const char* mode=argc>1?argv[1]:"normal";
    if(!strcmp(mode,"wrap"))now=UINT32_MAX-100;
    setup();const uint32_t boot_reads=sync_reads,boot_writes=sync_writes;
    if(!strcmp(mode,"offline")) {pmu_online=0;advance(100);assert(!it_calls);assert(registers[BIOS_POWER_REG]==BIOS_POWER_TAG);return 0;}
    advance(100);assert(registers[BIOS_POWER_REG]==0xB7 && registers[REG_ID_BAT]==(75|128));
    assert(bios_pmu_legacy_ready());
    uint8_t pct=0;assert(AXP2101_getBatteryPercent(&pct)==HAL_OK && pct==75);
    pmu[1]=4;advance(600);assert(registers[BIOS_POWER_REG]==0xBB && registers[REG_ID_BAT]==75);
    /* Do not publish a mix of states when charge mode changes mid-snapshot. */
    const uint32_t incoherent=bios_pmu_counters()->incoherent;
    status_transition=1;bios_power_refresh(1);advance(20);
    assert(registers[BIOS_POWER_REG]==BIOS_POWER_TAG && bios_pmu_counters()->incoherent>incoherent);
    advance(100);assert(registers[BIOS_POWER_REG]==0xB7);
    pmu[1]=4;advance(600);assert(registers[BIOS_POWER_REG]==0xBB);
    /* A cache miss is scheduled without waiting or modifying the caller. */
    uint8_t missing=0xEA;pmu[0x30]=0x67;
    assert(bios_pmu_mem_read(&hi2c2,0x68,0x30,1,&missing,1,60)==HAL_BUSY && missing==0xEA);
    advance(5);assert(bios_pmu_mem_read(&hi2c2,0x68,0x30,1,&missing,1,60)==HAL_OK && missing==0x67);
    assert(bios_pmu_mem_read(&hi2c2,0x68,255,1,&missing,2,60)==HAL_ERROR);
    /* A present, really empty cell is different from an absent battery. */
    pmu[0]=0x08;pmu[1]=0x40;pmu[0xA4]=0;bios_power_refresh(1);advance(80);
    assert(registers[BIOS_POWER_REG]==0xB1 && registers[REG_ID_BAT]==0);
    pmu[0]=0x20;pmu[1]=0;pmu[0xA4]=255;bios_power_refresh(1);advance(80);
    assert(registers[BIOS_POWER_REG]==0xB2 && registers[REG_ID_BAT]==127);
    pmu[0]=0x28;pmu[1]=4;pmu[0xA4]=75;bios_power_refresh(1);advance(80);
    assert(registers[BIOS_POWER_REG]==0xBB && registers[REG_ID_BAT]==75);
    /* The real legacy completion handler used to set a false charging bit. */
    pmu[0x4A]|=(uint8_t)(XPOWERS_AXP2101_BAT_CHG_DONE_IRQ>>16);pmu_irq=1;
    advance(80);legacy();advance(80);
    assert(registers[BIOS_POWER_REG]==0xBB && !(registers[REG_ID_BAT]&128));
    /* Real short/long button and IRQ ACK code, using cached reads/queued writes. */
    pmu[0x49]|=(uint8_t)(XPOWERS_AXP2101_PKEY_SHORT_IRQ>>8);pmu_irq=1;
    advance(80);legacy();assert(key_events==1 && (registers[REG_ID_INT]&INT_PWR_BTN));
    advance(80);assert(!(pmu[0x49]&(uint8_t)(XPOWERS_AXP2101_PKEY_SHORT_IRQ>>8)));
    pmu[0x49]|=(uint8_t)(XPOWERS_AXP2101_PKEY_LONG_IRQ>>8);pmu_irq=1;
    advance(80);legacy();assert(stop_mode_active==1);advance(80);
    /* A later write to the same register must survive an outstanding IT job. */
    uint8_t a=0x11,b=0x2D;
    assert(bios_pmu_mem_write(&hi2c2,0x68,0x69,1,&a,1,60)==HAL_OK);tick();
    assert(bios_pmu_mem_write(&hi2c2,0x68,0x69,1,&b,1,60)==HAL_OK);advance(80);assert(pmu[0x69]==b);
    const uint32_t untouched=test_gpiob.CRH&~0xFF00U;
    /* A normal STOP tail must yield, without resetting a healthy bus. */
    while(pending.active)tick();I2C2->SR2=I2C_SR2_BUSY;
    const uint32_t recovered=bios_pmu_counters()->recoveries;
    bios_power_refresh(1);advance(2);I2C2->SR2=0;advance(80);
    assert(bios_pmu_counters()->recoveries==recovered && registers[BIOS_POWER_REG]==0xBB);
    /* A permanent BUSY must never enter HAL's 25ms preamble. */
    advance(50);while(pending.active)tick();I2C2->SR2=I2C_SR2_BUSY;
    bios_power_refresh(1);advance(100);
    assert(bios_pmu_counters()->busy_guards && registers[BIOS_POWER_REG]==0xBB);
    assert((test_gpiob.CRH&~0xFF00U)==untouched);
    /* Recover nine stuck SDA bits without spinning or blocking M3 service. */
    while(pending.active)tick();held_sda=9;bios_power_refresh(1);advance(150);
    assert(!held_sda && clock_edges>=9 && registers[BIOS_POWER_REG]==0xBB);
    /* Missing completion and an IRQ error clear telemetry, then recover. */
    drop_io=1;bios_power_refresh(1);advance(10);
    assert(bios_pmu_counters()->timeouts && registers[BIOS_POWER_REG]==BIOS_POWER_TAG);
    drop_io=0;advance(150);assert(registers[BIOS_POWER_REG]==0xBB);
    error_io=1;bios_power_refresh(1);advance(150);assert(registers[BIOS_POWER_REG]==0xBB);
    /* Sleep is the only bounded drain; no render/inference is live then. */
    const uint32_t wake_mask=XPOWERS_AXP2101_PKEY_SHORT_IRQ |
        XPOWERS_AXP2101_PKEY_LONG_IRQ | XPOWERS_AXP2101_WARNING_LEVEL1_IRQ;
    assert(AXP2101_disableIRQ(XPOWERS_AXP2101_ALL_IRQ)==HAL_OK);
    assert(AXP2101_clearIrqStatus()==HAL_OK);
    assert(AXP2101_enableIRQ(wake_mask)==HAL_OK);
    const uint32_t before=now;wfi_allowed=1;bios_pmu_quiesce();wfi_allowed=0;
    assert((uint32_t)(now-before)<=101 && registers[BIOS_POWER_REG]==BIOS_POWER_TAG);
    assert(pmu[0x40]==(uint8_t)wake_mask && pmu[0x41]==(uint8_t)(wake_mask>>8) && pmu[0x42]==(uint8_t)(wake_mask>>16));
    bios_pmu_resume();assert(AXP2101_enableIRQ(XPOWERS_AXP2101_ALL_IRQ)==HAL_OK);
    advance(150);assert(registers[BIOS_POWER_REG]==0xBB);
    /* Held SCL backs off rather than monopolizing the CPU or other GPIO. */
    while(pending.active)tick();held_scl=1;bios_power_refresh(1);advance(100);
    assert(registers[BIOS_POWER_REG]==BIOS_POWER_TAG && bios_pmu_counters()->recovery_failures);
    const uint32_t attempts=bios_pmu_counters()->recoveries;advance(500);
    assert(bios_pmu_counters()->recoveries==attempts);held_scl=0;advance(1200);
    assert(registers[BIOS_POWER_REG]==0xBB);
    assert(sync_reads==boot_reads && sync_writes==boot_writes);assert(coproc_turns>3000);
    printf("Async PMU %s: coherent status, real IRQ/buttons, cached legacy, queued controls, BUSY/timeout recovery, sleep and M3 progress PASS\n",mode);
}
