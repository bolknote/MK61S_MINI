#ifndef PICOCALC_PMU_ASYNC_TEST_HAL_H
#define PICOCALC_PMU_ASYNC_TEST_HAL_H
#include <stdint.h>
#include <stddef.h>
#define __STATIC_INLINE static inline
typedef enum {HAL_OK=0,HAL_ERROR=1,HAL_BUSY=2,HAL_TIMEOUT=3} HAL_StatusTypeDef;
typedef enum {GPIO_PIN_RESET=0,GPIO_PIN_SET=1} GPIO_PinState;
typedef struct {volatile uint32_t CR1,CR2,OAR1,OAR2,DR,SR1,SR2,CCR,TRISE;} I2C_TypeDef;
typedef struct {volatile uint32_t CRL,CRH,IDR,ODR,BSRR,BRR,LCKR;} GPIO_TypeDef;
typedef struct {I2C_TypeDef* Instance;unsigned State,Mode,Lock,ErrorCode;} I2C_HandleTypeDef;
extern I2C_TypeDef test_i2c2;
extern GPIO_TypeDef test_gpiob,test_gpioc;
#define I2C2 (&test_i2c2)
#define GPIOB (&test_gpiob)
#define GPIOC (&test_gpioc)
enum {I2C2_EV_IRQn=33,I2C2_ER_IRQn=34,I2C_MEMADD_SIZE_8BIT=1,
      HAL_I2C_STATE_RESET=0,HAL_I2C_STATE_READY=32,HAL_I2C_STATE_BUSY_RX=34,
      HAL_I2C_STATE_BUSY_TX=33,HAL_I2C_MODE_NONE=0,HAL_I2C_MODE_MEM=64,
      HAL_UNLOCKED=0,HAL_LOCKED=1,HAL_I2C_ERROR_NONE=0,HAL_I2C_ERROR_AF=4,
      HAL_I2C_ERROR_TIMEOUT=32,I2C_CR1_PE=1,I2C_CR1_STOP=512,I2C_CR1_SWRST=32768,
      I2C_CR2_ITEVTEN=512,I2C_CR2_ITBUFEN=1024,I2C_CR2_ITERREN=256,I2C_SR2_BUSY=2,
      GPIO_PIN_9=512,GPIO_PIN_10=1024,GPIO_PIN_11=2048,GPIO_PIN_13=8192,LOW_BAT_VAL=20};
#define SYS_LED_GPIO_Port GPIOC
#define SYS_LED_Pin GPIO_PIN_13
uint32_t uptime_ms(void);
void test_wfi(void);
#define __DMB() ((void)0)
#define __WFI() test_wfi()
HAL_StatusTypeDef HAL_I2C_Mem_Read(I2C_HandleTypeDef*,uint16_t,uint16_t,uint16_t,uint8_t*,uint16_t,uint32_t);
HAL_StatusTypeDef HAL_I2C_Mem_Write(I2C_HandleTypeDef*,uint16_t,uint16_t,uint16_t,uint8_t*,uint16_t,uint32_t);
HAL_StatusTypeDef HAL_I2C_Mem_Read_IT(I2C_HandleTypeDef*,uint16_t,uint16_t,uint16_t,uint8_t*,uint16_t);
HAL_StatusTypeDef HAL_I2C_Mem_Write_IT(I2C_HandleTypeDef*,uint16_t,uint16_t,uint16_t,uint8_t*,uint16_t);
HAL_StatusTypeDef HAL_I2C_Init(I2C_HandleTypeDef*);
void HAL_I2C_EV_IRQHandler(I2C_HandleTypeDef*);
void HAL_I2C_ER_IRQHandler(I2C_HandleTypeDef*);
void HAL_NVIC_SetPriority(int,unsigned,unsigned);
void HAL_NVIC_ClearPendingIRQ(int);
void HAL_NVIC_EnableIRQ(int);
void HAL_NVIC_DisableIRQ(int);
void HAL_GPIO_WritePin(GPIO_TypeDef*,uint16_t,GPIO_PinState);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef*,uint16_t);
unsigned LL_GPIO_IsOutputPinSet(GPIO_TypeDef*,uint32_t);
void LL_GPIO_SetOutputPin(GPIO_TypeDef*,uint32_t);
void LL_GPIO_ResetOutputPin(GPIO_TypeDef*,uint32_t);
void led_blink_configure(uint8_t,uint8_t);
#endif
