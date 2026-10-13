import unittest
from check_narrow_stm32_drivers_elf import check_symbols

GOOD = "08000000 00000040 T RTC_Alarm_IRQHandler\n08000100 00000030 T RTC_WKUP_IRQHandler\n"
class GateTest(unittest.TestCase):
    def test_owned_irqs_and_unrelated_hal_are_allowed(self):
        check_symbols(GOOD + "08000200 00000020 T HAL_RCC_OscConfig\n")
    def test_each_removed_adapter_and_lto_clone_is_rejected(self):
        for name in ["analogRead.constprop.0", "analogReadResolution", "SPIClass::begin()", "SPISettings::SPISettings()", "LiquidCrystal::begin()", "STM32RTC::getInstance()", "HAL_ADC_Init", "HAL_SPI_Transmit", "HAL_DMA_Init", "HAL_RTC_SetTime", "PinMap_SPI_MOSI"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                check_symbols(GOOD + "08000200 00000020 T " + name + "\n")
    def test_weak_startup_irq_is_not_an_owned_irq(self):
        with self.assertRaises(ValueError):
            check_symbols(GOOD.replace("T RTC_WKUP_IRQHandler", "W RTC_WKUP_IRQHandler"))

if __name__ == "__main__": unittest.main()
