#include "stm3_uart_dma.h"
#include "stm32f1xx.h"
static uint8_t rx[STM3_UART_RX_BYTES];
static volatile uint32_t rx_wraps,errors;
static uint32_t consumed;
static int ready;
void stm3_uart_end(void){
 if(!ready)return;
 USART3->CR3=0;USART3->CR1=0;
 DMA1_Channel2->CCR=0;DMA1_Channel3->CCR=0;
 NVIC_DisableIRQ(DMA1_Channel3_IRQn);NVIC_ClearPendingIRQ(DMA1_Channel3_IRQn);
 DMA1->IFCR=DMA_IFCR_CGIF2|DMA_IFCR_CGIF3;
 // Float both lines while Pico power is off; do not feed its protection diodes.
 GPIOC->CRH=(GPIOC->CRH&~0x0000ff00u)|0x00004400u;
 ready=0;
}
int stm3_uart_begin(uint32_t pclk1_hz){
 // USART3 is clocked from APB1: at36MHz its maximum divider16 gives2.25Mbaud.
 if(pclk1_hz!=36000000u)return 0;
 RCC->AHBENR|=RCC_AHBENR_DMA1EN;
 if((DMA1_Channel2->CCR&DMA_CCR_EN)||(DMA1_Channel3->CCR&DMA_CCR_EN))return 0;
 RCC->APB2ENR|=RCC_APB2ENR_AFIOEN|RCC_APB2ENR_IOPCEN;
 RCC->APB1ENR|=RCC_APB1ENR_USART3EN;
 // The stock keyboard uses PA13/PA14 for power GPIO, so SWJ is already off.
 // SWJ_CFG reads are undefined onF1: reassert that board setting explicitly.
 AFIO->MAPR=(AFIO->MAPR&~(AFIO_MAPR_USART3_REMAP|AFIO_MAPR_SWJ_CFG))|
             AFIO_MAPR_USART3_REMAP_PARTIALREMAP|AFIO_MAPR_SWJ_CFG_DISABLE;
 // Change PC10/11 only: TX AF push-pull50MHz, RX input with pull-up.
 GPIOC->BSRR=1u<<11;
 GPIOC->CRH=(GPIOC->CRH&~0x0000ff00u)|0x00008b00u;
 USART3->CR1=0;USART3->CR2=0;USART3->CR3=USART_CR3_DMAT|USART_CR3_DMAR;
 USART3->BRR=16;
 DMA1_Channel2->CCR=0;DMA1_Channel3->CCR=0;
 DMA1->IFCR=DMA_IFCR_CGIF2|DMA_IFCR_CGIF3;
 DMA1_Channel3->CPAR=(uint32_t)(uintptr_t)&USART3->DR;
 DMA1_Channel3->CMAR=(uint32_t)(uintptr_t)rx;DMA1_Channel3->CNDTR=sizeof(rx);
 rx_wraps=consumed=errors=0;
 NVIC_SetPriority(DMA1_Channel3_IRQn,3);NVIC_EnableIRQ(DMA1_Channel3_IRQn);
 DMA1_Channel3->CCR=DMA_CCR_MINC|DMA_CCR_CIRC|DMA_CCR_TCIE|DMA_CCR_TEIE|DMA_CCR_PL_1|DMA_CCR_EN;
 USART3->CR1=USART_CR1_UE|USART_CR1_RE|USART_CR1_TE;
 ready=1;return 1;
}
void DMA1_Channel3_IRQHandler(void){
 const uint32_t status=DMA1->ISR;
 if(status&DMA_ISR_TCIF3){++rx_wraps;DMA1->IFCR=DMA_IFCR_CTCIF3;}
 if(status&DMA_ISR_TEIF3){++errors;DMA1_Channel3->CCR&=~DMA_CCR_EN;DMA1->IFCR=DMA_IFCR_CTEIF3;}
}
static uint32_t produced(void){
 uint32_t w1,w2,left1,left2,flags;
 do{w1=rx_wraps;left1=DMA1_Channel3->CNDTR;flags=DMA1->ISR;left2=DMA1_Channel3->CNDTR;w2=rx_wraps;}
 while(w1!=w2||!left2||left2>left1);
 // Include a complete wrap whose IRQ is pending, exactly once.
 if(flags&DMA_ISR_TCIF3)++w1;
 return w1*STM3_UART_RX_BYTES+STM3_UART_RX_BYTES-left2;
}
unsigned stm3_uart_read(uint8_t*out,unsigned cap){
 if(!ready||!cap)return 0;
 const uint32_t status=USART3->SR;
 if(status&(USART_SR_ORE|USART_SR_FE|USART_SR_NE|USART_SR_PE)){
  volatile uint32_t discard=USART3->DR;(void)discard;++errors;
 }
 if(!(DMA1_Channel3->CCR&DMA_CCR_EN)){
  // A DMA transfer error invalidates the partial frame. Re-arm the known
  // resident buffer; the bridge discards through the next COBS delimiter.
  const uint32_t mask=__get_PRIMASK();__disable_irq();
  DMA1->IFCR=DMA_IFCR_CGIF3;rx_wraps=consumed=0;
  DMA1_Channel3->CPAR=(uint32_t)(uintptr_t)&USART3->DR;
  DMA1_Channel3->CMAR=(uint32_t)(uintptr_t)rx;
  DMA1_Channel3->CNDTR=sizeof(rx);
  DMA1_Channel3->CCR=DMA_CCR_MINC|DMA_CCR_CIRC|DMA_CCR_TCIE|DMA_CCR_TEIE|DMA_CCR_PL_1|DMA_CCR_EN;
  __set_PRIMASK(mask);return 0;
 }
 const uint32_t total=produced(),available=total-consumed;
 if(available>sizeof(rx)){consumed=total;++errors;return 0;}
 unsigned n=available<cap?available:cap;
 for(unsigned i=0;i<n;++i)out[i]=rx[(consumed+i)&(STM3_UART_RX_BYTES-1)];
 consumed+=n;return n;
}
int stm3_uart_tx_idle(void){
 if(!ready)return 0;
 if(DMA1_Channel2->CCR&DMA_CCR_EN){
  if(DMA1->ISR&DMA_ISR_TEIF2){++errors;DMA1_Channel2->CCR&=~DMA_CCR_EN;DMA1->IFCR=DMA_IFCR_CGIF2;return 0;}
  if(DMA1_Channel2->CNDTR)return 0;
  DMA1_Channel2->CCR&=~DMA_CCR_EN;
 }
 return 1;
}
int stm3_uart_tx_start(const uint8_t*packet,unsigned n){
 if(!packet||!n||n>STM3_UART_TX_BYTES||!stm3_uart_tx_idle())return 0;
 DMA1->IFCR=DMA_IFCR_CGIF2;
 DMA1_Channel2->CPAR=(uint32_t)(uintptr_t)&USART3->DR;
 DMA1_Channel2->CMAR=(uint32_t)(uintptr_t)packet;DMA1_Channel2->CNDTR=n;
 __DMB();
 DMA1_Channel2->CCR=DMA_CCR_DIR|DMA_CCR_MINC|DMA_CCR_PL_0|DMA_CCR_EN;
 return 1;
}
uint32_t stm3_uart_errors(void){return errors;}
const uint8_t*stm3_uart_rx_buffer(void){return rx;}
