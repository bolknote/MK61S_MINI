#ifndef STM3_UART_DMA_H
#define STM3_UART_DMA_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define STM3_UART_BAUD 2250000u
#define STM3_UART_RX_BYTES 512u
#define STM3_UART_TX_BYTES 272u
int stm3_uart_begin(uint32_t pclk1_hz);
void stm3_uart_end(void);
unsigned stm3_uart_read(uint8_t*,unsigned);
// Caller retains the packet unchanged until tx_idle() reports completion.
int stm3_uart_tx_idle(void);
int stm3_uart_tx_start(const uint8_t*,unsigned);
uint32_t stm3_uart_errors(void);
const uint8_t* stm3_uart_rx_buffer(void);
void DMA1_Channel3_IRQHandler(void);
#ifdef __cplusplus
}
#endif
#endif
