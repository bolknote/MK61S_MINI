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
    def test_exact_legacy_and_native_layouts(self):
        legacy = "20000000 000000fc B hUSBD_Device_CDC\n20000100 00000024 B _hcdc\n"
        compact = "00000001 A mk61_usb_compact_layout\n20000000 00000060 B hUSBD_Device_CDC\n20000100 0000001c B _hcdc\n"
        check_symbols(GOOD + legacy)
        check_symbols(GOOD + compact, native_panel=True)
        for invalid in [compact.replace("00000060", "000000fc"),
                        compact.replace("0000001c", "00000024"),
                        compact.replace("00000001 A", "00000002 A"),
                        compact.split("\n", 1)[1],
                        "00000001 A mk61_usb_compact_layout\n" + legacy]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                check_symbols(GOOD + invalid)

    def test_weak_startup_irq_is_not_an_owned_irq(self):
        with self.assertRaises(ValueError):
            check_symbols(GOOD.replace("T RTC_WKUP_IRQHandler", "W RTC_WKUP_IRQHandler"))

if __name__ == "__main__": unittest.main()
