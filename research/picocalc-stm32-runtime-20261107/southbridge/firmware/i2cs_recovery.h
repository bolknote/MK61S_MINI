#ifndef STM3_I2CS_RECOVERY_H
#define STM3_I2CS_RECOVERY_H
#include "i2cs.h"

extern volatile uint8_t i2cs_recover_required;
/* An API refusal must not leave ADDR asserted and SCL stretched. Quiesce
 * this slave only; main reinitializes its HAL context outside the IRQ. */
static inline void i2cs_address_failure(I2C_HandleTypeDef *h) {
  __HAL_I2C_DISABLE_IT(h, I2C_IT_EVT | I2C_IT_BUF | I2C_IT_ERR);
  __HAL_I2C_DISABLE(h);
  i2cs_state = I2CS_STATE_IDLE;
  i2cs_recover_required = 1;
}
static inline void i2cs_receive(I2C_HandleTypeDef *h, uint8_t *p,
                               uint16_t n, uint32_t flags) {
  if (HAL_I2C_Slave_Seq_Receive_IT(h, p, n, flags) != HAL_OK)
    i2cs_address_failure(h);
}
static inline void i2cs_transmit(I2C_HandleTypeDef *h, uint8_t *p,
                                uint16_t n, uint32_t flags) {
  if (HAL_I2C_Slave_Seq_Transmit_IT(h, p, n, flags) != HAL_OK)
    i2cs_address_failure(h);
}
#endif
