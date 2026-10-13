#!/usr/bin/env python3
"""Preprocess real project/Core timer sources under each HAL timer policy."""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def core_directory():
    explicit = os.environ.get("MK61_STM32_CORE_PATH")
    if explicit:
        path = Path(explicit)
        if not path.is_dir():
            raise ValueError(f"STM32 Core directory does not exist: {path}")
        return path
    for data in (os.environ.get("ARDUINO_DATA_DIR"),
                 Path.home() / "Library/Arduino15", Path.home() / ".arduino15"):
        if data:
            path = Path(data) / "packages/STMicroelectronics/hardware/stm32/2.12.0"
            if path.is_dir():
                return path
    return None


class HalTimerPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("clang++") or shutil.which("c++")
        if not cls.compiler:
            raise unittest.SkipTest("C++ preprocessor is unavailable")
        cls.core = core_directory()

    def preprocess(self, source, chip, options=(), macros=False):
        with tempfile.TemporaryDirectory(prefix="mk61-hal-policy-") as temporary:
            includes = Path(temporary)
            # Only preprocessing is performed: register identifiers and C++
            # types need no mock implementations. CONFIG avoids unrelated
            # product-profile dependencies while retaining the real drivers.
            common = ('#pragma once\n#define HAL_TIM_MODULE_ENABLED 1\n'
                      '#include "hal_conf_extra.h"\n')
            for name in ("Arduino.h", "timer.h", "HardwareTimer.h"):
                (includes / name).write_text(common)
            for name in ("PeripheralPins.h", "pinmap.h", "core_debug.h", "board.h"):
                (includes / name).write_text("#pragma once\n")
            command = [self.compiler, "-std=c++17", "-E", "-x", "c++",
                       "-DCONFIG", "-DTIMER_TONE=1", "-I" + str(includes),
                       "-I" + str(ROOT / "code"), *options]
            if chip:
                command.extend(["-DARDUINO_ARCH_STM32", "-D" + chip])
            command.append("-dM" if macros else "-P")
            command.append(str(source))
            return subprocess.check_output(command, text=True)

    def test_direct_sound_and_tim9_survive_size_and_lto_policies(self):
        for chip in ("STM32F401xC", "STM32F401xE", "STM32F411xE"):
            for options in (("-Os",), ("-Os", "-flto"),
                            ("-Oz", "-flto", "-DHAL_TIM_MODULE_ONLY")):
                with self.subTest(chip=chip, options=options):
                    sound = self.preprocess(ROOT / "code/sound_driver.cpp",
                                            chip, options, macros=True)
                    classic = self.preprocess(ROOT / "code/classic_timer.cpp",
                                              chip, options, macros=True)
                    self.assertIn("#define HAL_TIM_MODULE_ONLY", sound)
                    self.assertIn("#define MK61_SOUND_DRIVER_DIRECT 1", sound)
                    self.assertIn("#define MK61_SOUND_DRIVER_STM32 1", sound)
                    self.assertIn("#define MK61_CLASSIC_TIMER_USES_TIM9 1", classic)

    def test_other_stm32_retains_the_arduino_timer_backend(self):
        sound = self.preprocess(ROOT / "code/sound_driver.cpp", "STM32F103xB",
                                macros=True)
        classic = self.preprocess(ROOT / "code/classic_timer.cpp", "STM32F103xB",
                                  macros=True)
        self.assertNotIn("#define HAL_TIM_MODULE_ONLY", sound)
        self.assertIn("#define MK61_SOUND_DRIVER_STM32 1", sound)
        self.assertIn("#define MK61_SOUND_DRIVER_DIRECT 0", sound)
        self.assertIn("#define MK61_CLASSIC_TIMER_USES_TIM9 0", classic)

    def test_actual_core_wrappers_are_removed_only_on_supported_devices(self):
        if self.core is None:
            self.skipTest("install pinned STM32 Core or set MK61_STM32_CORE_PATH")
        sources = {
            self.core / "libraries/SrcWrapper/src/stm32/timer.c": "get_timer_obj(",
            self.core / "libraries/SrcWrapper/src/HardwareTimer.cpp":
                "HardwareTimer::captureCompareCallback(",
        }
        for source, marker in sources.items():
            self.assertTrue(source.is_file(), source)
            # The negative control prevents an empty/misconfigured fixture
            # from making the supported-device removal checks pass.
            fallback = self.preprocess(source, "STM32F103xB")
            self.assertIn(marker, re.sub(r"\s+", "", fallback))
            for chip in ("STM32F401xC", "STM32F401xE", "STM32F411xE"):
                for options in (("-Os",), ("-Os", "-flto"),
                                ("-Oz", "-flto", "-DHAL_TIM_MODULE_ONLY")):
                    with self.subTest(source=source.name, chip=chip, options=options):
                        output = self.preprocess(source, chip, options)
                        self.assertNotIn(marker, re.sub(r"\s+", "", output))


if __name__ == "__main__":
    unittest.main()
