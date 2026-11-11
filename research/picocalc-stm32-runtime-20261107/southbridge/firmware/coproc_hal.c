#include "coproc_hal.h"
#include "hal_interface.h"
#include "stm3_runtime.h"
#include "stm3_uart_dma.h"

extern TIM_HandleTypeDef htim2;
extern uint32_t _sstack;
static stm3_runtime coproc;
static uint32_t last_uart_errors,last_rx_ms;
static uint8_t configured,ready;

uint32_t coproc_time_us(void*context){
 (void)context;
 const uint32_t mask=__get_PRIMASK();__disable_irq();
 uint32_t ms=systicks_counter,cnt=TIM2->CNT;
 // TIM2 ticks at exactly 1MHz, ARR=999; include a pending update once.
 if(TIM2->SR&TIM_SR_UIF){++ms;cnt=TIM2->CNT;}
 __set_PRIMASK(mask);
 return ms*1000u+cnt;
}
static uint32_t address(void*context,const void*p){(void)context;return (uint32_t)(uintptr_t)p;}
static uint32_t invoke(void*context,uint32_t entry,uint32_t op,const stm3_api*api,stm3_job*job){
 (void)context;__DSB();__ISB();
 return ((stm3_entry)(uintptr_t)entry)(op,api,job);
}
static void clear_runtime(void){
 const stm3_backend backend={0,coproc_time_us,address,invoke,STM3_UART_BAUD,3};
 stm3_init(&coproc,&backend);last_uart_errors=0;last_rx_ms=uptime_ms();
}
void coproc_setup(void){
 clear_runtime();configured=1;
 // Paint only unused stack, with IRQs masked so an exception cannot land here.
 const uint32_t mask=__get_PRIMASK();__disable_irq();
 const uintptr_t limit=(uintptr_t)__get_MSP()-64u;
 for(volatile uint32_t*p=&_sstack;(uintptr_t)p<limit;++p)*p=0xa55a39c6u;
 __set_PRIMASK(mask);
}
uint32_t coproc_stack_unused(void){
 const volatile uint32_t*p=&_sstack;const uintptr_t top=(uintptr_t)&_sstack+4096u;
 while((uintptr_t)p<top&&*p==0xa55a39c6u)++p;
 return (uint32_t)((uintptr_t)p-(uintptr_t)&_sstack);
}
void coproc_suspend(void){
 if(!configured)return;
 // Power/reset overrides jobs. Never execute module FINI on this path.
 stm3_uart_end();ready=0;clear_runtime();
}
void coproc_resume(void){
 if(configured&&!ready)ready=(uint8_t)(stm3_uart_begin(HAL_RCC_GetPCLK1Freq())!=0);
}
int coproc_storage_idle(void){
 // F103 internal-Flash erase/program stalls instruction fetch. Defer while a
 // module or exchange exists, even between jobs with resident constants.
 return !ready||(coproc.state==STM3_EMPTY&&coproc.tx_at==coproc.tx_bytes&&
                 stm3_uart_tx_idle()&&uptime_ms()-last_rx_ms>=20u);
}
void coproc_poll(void){
 if(!ready)return;
 unsigned completed_request=0;
 if(stm3_uart_tx_idle()){
  if(coproc.tx_at<coproc.tx_bytes){
   if(stm3_uart_tx_start(coproc.tx+coproc.tx_at,coproc.tx_bytes-coproc.tx_at))coproc.tx_at=coproc.tx_bytes;
  }else{
   // Do not consume another request while DMA still owns the cached reply.
   for(unsigned i=0;i<64u;++i){
    uint8_t byte;const unsigned n=stm3_uart_read(&byte,1);
    const uint32_t errors=stm3_uart_errors();
    if(errors!=last_uart_errors){last_uart_errors=errors;++coproc.bad_frames;coproc.frame_overflow=1;}
    if(!n)break;
    last_rx_ms=uptime_ms();const uint32_t job_before=coproc.job_id;stm3_feed(&coproc,byte);
    // START_RESULT runs INIT now but defers its UART reply. Keep keyboard
    // processing between that INIT and the first cooperative STEP too.
    if(coproc.tx_at<coproc.tx_bytes||coproc.job_id!=job_before){completed_request=1;break;}
   }
  }
 }
 // INIT/CANCEL/FINI may already have run while handling a request. Keep one
 // module invocation per main-loop turn, with keyboard processing in between.
 if(!completed_request)stm3_tick(&coproc);
}
void coproc_enter_sleep(void){
 HAL_TIM_Base_Stop_IT(&htim2);HAL_SuspendTick();
 // No automatic option-byte programming. If STOP would reset this chip,
 // retain wake behavior with ordinary SLEEP at higher idle power instead.
 if(FLASH->OBR&FLASH_OBR_nRST_STOP)
  HAL_PWR_EnterSTOPMode(PWR_LOWPOWERREGULATOR_ON,PWR_STOPENTRY_WFI);
 else
  HAL_PWR_EnterSLEEPMode(PWR_MAINREGULATOR_ON,PWR_SLEEPENTRY_WFI);
 SystemClock_Config();HAL_ResumeTick();
 __HAL_TIM_SET_COUNTER(&htim2,0);__HAL_TIM_CLEAR_FLAG(&htim2,TIM_FLAG_UPDATE);
 if(HAL_TIM_Base_Start_IT(&htim2)!=HAL_OK)Error_Handler();
}
