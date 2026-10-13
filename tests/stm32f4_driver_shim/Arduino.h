#ifndef MK61_DRIVER_TEST_ARDUINO_H
#define MK61_DRIVER_TEST_ARDUINO_H
#include <cassert>
#include <cstddef>
#include <cstdint>
uint32_t model_read(const void *, uint32_t);
void model_write(void *, uint32_t);
struct Register {
  uint32_t value = 0;
  operator uint32_t() const { return model_read(this, value); }
  void operator=(uint32_t next) { model_write(this, next); }
  void operator|=(uint32_t mask) { model_write(this, model_read(this, value) | mask); }
  void operator&=(uint32_t mask) { model_write(this, model_read(this, value) & mask); }
};
struct RCC_TypeDef {
  Register AHB1ENR, APB1ENR, APB2ENR, APB2RSTR, CFGR, DCKCFGR, BDCR, CSR;
};
struct PWR_TypeDef {
  Register CR;
};
struct GPIO_TypeDef {
  Register MODER, OTYPER, OSPEEDR, PUPDR, AFR[2];
};
struct ADC_TypeDef {
  Register SR, CR1, CR2, SQR1, SQR2, SQR3, SMPR1, DR;
};
struct ADC_Common_TypeDef {
  Register CCR;
};
struct SPI_TypeDef {
  Register CR1, CR2, SR, DR;
};
struct RTC_TypeDef {
  Register WPR, ISR, SSR, TR, DR, PRER, CR, CALR, ALRMAR, ALRMBR, ALRMASSR, ALRMBSSR,
      WUTR;
  uint32_t BKP0R, other_backup[19];
};
struct EXTI_TypeDef {
  Register PR, IMR, RTSR;
};
struct DMA_Stream_TypeDef {
  Register CR, FCR, PAR, M0AR, NDTR;
};
struct DMA_TypeDef {
  Register LISR, LIFCR;
};
struct SCB_TypeDef {
  Register SCR;
};
extern RCC_TypeDef model_rcc;
extern GPIO_TypeDef model_gpio;
extern PWR_TypeDef model_pwr;
extern ADC_TypeDef model_adc;
extern ADC_Common_TypeDef model_common;
extern SPI_TypeDef model_spi;
extern RTC_TypeDef model_rtc;
extern EXTI_TypeDef model_exti;
extern DMA_Stream_TypeDef model_rx, model_tx;
extern DMA_TypeDef model_dma;
extern SCB_TypeDef model_scb;
#define RCC (&model_rcc)
constexpr uint32_t PWR_CR_DBP = 1U << 8;
#define PWR (&model_pwr)
#define GPIOA (&model_gpio)
#define ADC1 (&model_adc)
#define ADC (&model_common)
#define SPI1 (&model_spi)
#define RTC (&model_rtc)
#define EXTI (&model_exti)
#define DMA2 (&model_dma)
#define DMA2_Stream2 (&model_rx)
#define DMA2_Stream3 (&model_tx)
#define SCB (&model_scb)
#define RTC_BASE (reinterpret_cast<uintptr_t>(&model_rtc))
enum {
  RTC_Alarm_IRQn = 41,
  RTC_WKUP_IRQn = 3,
  DMA2_Stream2_IRQn = 58,
  DMA2_Stream3_IRQn = 59
};
constexpr uint32_t PA5 = 5, PA6 = 6, PA7 = 7;
#define PIN_SPI_SCK PA5
#define PIN_SPI_MISO PA6
#define PIN_SPI_MOSI PA7
constexpr uint32_t LSI_VALUE = 32000;
// Register bit values follow STM32F411 CMSIS from pinned core 2.12.0.
#define ADC_CCR_ADCPRE 0x00030000U
#define ADC_CCR_ADCPRE_0 0x00010000U
#define ADC_CCR_MULTI 0x0000001FU
#define ADC_CCR_TSVREFE 0x00800000U
#define ADC_CCR_VBATE 0x00400000U
#define ADC_CR2_ADON 0x00000001U
#define ADC_CR2_SWSTART 0x40000000U
#define ADC_SR_EOC 0x00000002U
#define DMA_LIFCR_CDMEIF2 0x00040000U
#define DMA_LIFCR_CDMEIF3 0x01000000U
#define DMA_LIFCR_CFEIF2 0x00010000U
#define DMA_LIFCR_CFEIF3 0x00400000U
#define DMA_LIFCR_CHTIF2 0x00100000U
#define DMA_LIFCR_CHTIF3 0x04000000U
#define DMA_LIFCR_CTCIF2 0x00200000U
#define DMA_LIFCR_CTCIF3 0x08000000U
#define DMA_LIFCR_CTEIF2 0x00080000U
#define DMA_LIFCR_CTEIF3 0x02000000U
#define DMA_LISR_DMEIF2 0x00040000U
#define DMA_LISR_DMEIF3 0x01000000U
#define DMA_LISR_FEIF3 0x00400000U
#define DMA_LISR_TCIF2 0x00200000U
#define DMA_LISR_TCIF3 0x08000000U
#define DMA_LISR_TEIF2 0x00080000U
#define DMA_LISR_TEIF3 0x02000000U
#define DMA_SxCR_CHSEL_Pos 0x00000019U
#define DMA_SxCR_DIR_0 0x00000040U
#define DMA_SxCR_DMEIE 0x00000002U
#define DMA_SxCR_EN 0x00000001U
#define DMA_SxCR_MINC 0x00000400U
#define DMA_SxCR_PL_1 0x00020000U
#define DMA_SxCR_TCIE 0x00000010U
#define DMA_SxCR_TEIE 0x00000004U
#define RCC_AHB1ENR_DMA2EN 0x00400000U
#define RCC_AHB1ENR_GPIOAEN 0x00000001U
#define RCC_APB1ENR_PWREN 0x10000000U
#define RCC_APB2ENR_ADC1EN 0x00000100U
#define RCC_APB2ENR_SPI1EN 0x00001000U
#define RCC_APB2RSTR_SPI1RST 0x00001000U
#define RCC_BDCR_BDRST 0x00010000U
#define RCC_BDCR_LSEBYP 0x00000004U
#define RCC_BDCR_LSEON 0x00000001U
#define RCC_BDCR_LSERDY 0x00000002U
#define RCC_BDCR_RTCEN 0x00008000U
#define RCC_BDCR_RTCSEL 0x00000300U
#define RCC_BDCR_RTCSEL_0 0x00000100U
#define RCC_BDCR_RTCSEL_1 0x00000200U
#define RCC_CFGR_PPRE1 0x00001C00U
#define RCC_CFGR_PPRE1_DIV1 0x00000000U
#define RCC_CFGR_PPRE1_DIV2 0x00001000U
#define RCC_CFGR_PPRE1_DIV4 0x00001400U
#define RCC_CFGR_PPRE2 0x0000E000U
#define RCC_CFGR_PPRE2_DIV1 0x00000000U
#define RCC_CFGR_PPRE2_DIV2 0x00008000U
#define RCC_CFGR_PPRE2_DIV4 0x0000A000U
#define RCC_CSR_LSION 0x00000001U
#define RCC_CSR_LSIRDY 0x00000002U
#define RCC_DCKCFGR_TIMPRE 0x01000000U
#define RTC_ALARM_A 0x00000100U
#define RTC_ALARM_B 0x00000200U
#define RTC_CR_ALRAE 0x00000100U
#define RTC_CR_ALRAIE 0x00001000U
#define RTC_CR_ALRBE 0x00000200U
#define RTC_CR_ALRBIE 0x00002000U
#define RTC_CR_BYPSHAD 0x00000020U
#define RTC_CR_WUCKSEL 0x00000007U
#define RTC_CR_WUTE 0x00000400U
#define RTC_CR_WUTIE 0x00004000U
#define RTC_ISR_ALRAF 0x00000100U
#define RTC_ISR_ALRAWF 0x00000001U
#define RTC_ISR_ALRBF 0x00000200U
#define RTC_ISR_ALRBWF 0x00000002U
#define RTC_ISR_INIT 0x00000080U
#define RTC_ISR_INITF 0x00000040U
#define RTC_ISR_INITS 0x00000010U
#define RTC_ISR_RECALPF 0x00010000U
#define RTC_ISR_RSF 0x00000020U
#define RTC_ISR_WUTF 0x00000400U
#define RTC_ISR_WUTWF 0x00000004U
#define RTC_PRER_PREDIV_A_Pos 0x00000010U
#define RTC_PRER_PREDIV_S 0x00007FFFU
#define SPI_CR1_BR 0x00000038U
#define SPI_CR1_BR_Pos 0x00000003U
#define SPI_CR1_MSTR 0x00000004U
#define SPI_CR1_SPE 0x00000040U
#define SPI_CR1_SSI 0x00000100U
#define SPI_CR1_SSM 0x00000200U
#define SPI_CR2_RXDMAEN 0x00000001U
#define SPI_CR2_TXDMAEN 0x00000002U
#define SPI_SR_BSY 0x00000080U
#define SPI_SR_MODF 0x00000020U
#define SPI_SR_OVR 0x00000040U
#define SPI_SR_RXNE 0x00000001U
#define SPI_SR_TXE 0x00000002U
#define TIM11_BASE 0x40014800U
#define TIM2_BASE 0x40000000U
#define TIM4_BASE 0x40000800U
#define TIM5_BASE 0x40000C00U
#define TIM9_BASE 0x40014000U
#define SCB_SCR_SLEEPDEEP_Msk (1UL << 2)

struct RTC_TimeTypeDef {
  uint8_t Hours{}, Minutes{}, Seconds{};
  uint32_t SubSeconds{}, SecondFraction{};
};
struct RTC_DateTypeDef {
  uint8_t Year{}, Month{}, Date{}, WeekDay{};
};
struct RTC_AlarmTypeDef {
  RTC_TimeTypeDef AlarmTime{};
  uint32_t Alarm{}, AlarmMask{}, AlarmDateWeekDay{}, AlarmSubSecondMask{};
};
uint32_t millis();
uint32_t micros();
void yield();
void delayMicroseconds(uint32_t);
void __DSB();
void __DMB();
void __ISB();
void __WFI();
uint32_t __get_PRIMASK();
uint32_t __get_IPSR();
void NVIC_ClearPendingIRQ(int);
void NVIC_SetPendingIRQ(int);
void NVIC_SetPriority(int, unsigned);
void NVIC_EnableIRQ(int);
inline uint32_t HAL_RCC_GetPCLK2Freq() {
  return 96000000;
}
inline uint32_t HAL_RCC_GetPCLK1Freq() {
  return 48000000;
}
inline uint32_t HAL_RCC_GetHCLKFreq() {
  return 96000000;
}
#endif
