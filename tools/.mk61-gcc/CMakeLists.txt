cmake_minimum_required(VERSION 3.21)

foreach(_mk61_path_variable
    MK61_PROJECT_ROOT
    MK61_STM32_CORE
    MK61_CMSIS_ROOT
    MK61_CMSIS_DSP_ROOT
    MK61_LIQUIDCRYSTAL_ROOT
    MK61_RTC_ROOT)
  if(NOT DEFINED ${_mk61_path_variable} OR
     NOT IS_DIRECTORY "${${_mk61_path_variable}}")
    message(FATAL_ERROR
      "${_mk61_path_variable} must point to an existing directory")
  endif()
endforeach()

if(NOT DEFINED MK61_CORE_VERSION OR MK61_CORE_VERSION STREQUAL "")
  message(FATAL_ERROR "MK61_CORE_VERSION is required")
endif()

project(mk61s_f401_gcc LANGUAGES C CXX ASM)

find_package(Python3 3 REQUIRED COMPONENTS Interpreter)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# A raw developer build stays bootable for debugger/IDE workflows. Public
# builders explicitly set this to 1 and seal resident.bin after the link.
set(MK61_REQUIRE_RESIDENT_CRC "0" CACHE STRING
  "Require a post-link CRC-sealed resident image")
set(MK61_FLASH_MIN_HEADROOM "512" CACHE STRING
  "Required free bytes in the sealed resident Flash image")
set(MK61_GLOBAL_RAM_LIMIT "52428" CACHE STRING
  "Maximum resident .data + .bss bytes")
set(MK61_STACK_FRAME_LIMIT "5120" CACHE STRING
  "Maximum project-owned static or bounded-dynamic stack frame")

file(REAL_PATH "${MK61_PROJECT_ROOT}" MK61_PROJECT_ROOT)
file(REAL_PATH "${MK61_STM32_CORE}" CORE_PATH)
file(REAL_PATH "${CORE_PATH}/cores/arduino" BUILD_CORE_PATH)
file(REAL_PATH "${CORE_PATH}/system" BUILD_SYSTEM_PATH)
file(REAL_PATH "${CORE_PATH}/libraries" BUILD_LIB_PATH)
file(REAL_PATH "${MK61_CMSIS_ROOT}" CMSIS6_PATH)
file(REAL_PATH "${MK61_CMSIS_DSP_ROOT}" CMSIS_DSP_PATH)

if(NOT EXISTS "${CORE_PATH}/platform.txt" OR
   NOT EXISTS "${CORE_PATH}/cmake/boards_db.cmake")
  message(FATAL_ERROR
    "MK61_STM32_CORE is not an STM32 Arduino Core installation")
endif()

file(READ "${CORE_PATH}/platform.txt" _mk61_platform_text)
string(REPLACE "." "\\." _mk61_core_version_regex "${MK61_CORE_VERSION}")
if(NOT _mk61_platform_text MATCHES
   "(^|\n)version=${_mk61_core_version_regex}(\r?\n|$)")
  message(FATAL_ERROR "STM32 Arduino Core ${MK61_CORE_VERSION} is required")
endif()

foreach(_mk61_bool
    MK61_ENABLE_FOCAL
    MK61_ENABLE_TINYBASIC
    MK61_ENABLE_WBMP_VIEWER
    MK61_ENABLE_MARKDOWN_VIEWER
    MK61_ENABLE_CHIP8
    MK61_ENABLE_USB_SCREEN
    MK61_WS0010_GRAPHICS_100X16
    MK61_ENABLE_EXTENDED_FONT_SETTINGS
    MK61_USER_EXPLORER_SHORTCUT
    MK61_MATH_BACKEND
    MK61_REQUIRE_RESIDENT_CRC
    MK61_ENABLE_LTO)
  if(NOT DEFINED ${_mk61_bool})
    message(FATAL_ERROR "${_mk61_bool} is required")
  endif()
  if(NOT "${${_mk61_bool}}" MATCHES "^[01]$")
    message(FATAL_ERROR "${_mk61_bool} must be 0 or 1")
  endif()
endforeach()

execute_process(
  COMMAND "${Python3_EXECUTABLE}"
    "${MK61_PROJECT_ROOT}/tools/release_contract.py"
    profile --id "${MK61_PROFILE}" --format cmake
  RESULT_VARIABLE _mk61_profile_result
  OUTPUT_VARIABLE _mk61_profile_definitions
  ERROR_VARIABLE _mk61_profile_error
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT _mk61_profile_result EQUAL 0)
  message(FATAL_ERROR
    "Unsupported MK61_PROFILE ${MK61_PROFILE}: ${_mk61_profile_error}")
endif()

# Reuse the board, core, HAL and Arduino-library targets shipped with the
# pinned STM32 Core.  Include its generated board database directly so this
# build never invokes Arduino CLI or the database updater.
include("${CORE_PATH}/cmake/boards_db.cmake")
add_library(board ALIAS BLACKPILL_F401CC)
set(BUILD_VARIANT_PATH "${BLACKPILL_F401CC_VARIANT_PATH}")
set(BOARD_MAXSIZE "${BLACKPILL_F401CC_MAXSIZE}")
set(BOARD_MAXDATASIZE "${BLACKPILL_F401CC_MAXDATASIZE}")
set(MCU "${BLACKPILL_F401CC_MCU}")
set(FPCONF "${BLACKPILL_F401CC_FPCONF}")
target_link_libraries(BLACKPILL_F401CC INTERFACE
  # The firmware terminal is USB CDC.  Instantiating the board's unused UART
  # Serial1 object costs SRAM and also pulls the HAL UART debug state in.
  BLACKPILL_F401CC_serial_none
  BLACKPILL_F401CC_usb_CDCgen
  BLACKPILL_F401CC_xusb_FS)

include("${CORE_PATH}/cmake/overall_settings.cmake")
if(MK61_ENABLE_LTO)
  overall_settings(OPTIMIZATION s LTO)
else()
  overall_settings(OPTIMIZATION s)
endif()
target_compile_definitions(user_settings INTERFACE
  ARDUINO=10607
  VECT_TAB_OFFSET=0x0
  # Terminal I/O is USB CDC. Disable the unused Arduino UART wrapper/debug
  # state while leaving the STM32 HAL UART module available.
  HAL_UART_MODULE_ONLY
  # CDC and our MSC class publish no class-specific user strings. The Core
  # default callback merely reserves an otherwise unused 255-byte RAM buffer.
  USBD_CLASS_USER_STRING_DESC=0)

include("${CORE_PATH}/cmake/set_base_arduino_config.cmake")
add_subdirectory("${BUILD_VARIANT_PATH}" "${CMAKE_BINARY_DIR}/stm32/variant")
add_subdirectory("${BUILD_CORE_PATH}" "${CMAKE_BINARY_DIR}/stm32/core")
add_subdirectory("${BUILD_LIB_PATH}" "${CMAKE_BINARY_DIR}/stm32/libraries")

# Keep the CDC queue-full call visible to GNU ld.  With whole-program LTO the
# call to USBD_CDC_ClearBuffer is resolved inside usbd_cdc.c before --wrap can
# redirect it, leaving F401 builds unprotected.  Only this small translation
# unit needs to opt out; the rest of the resident firmware retains LTO.
set_source_files_properties(
  "${BUILD_LIB_PATH}/USBDevice/src/cdc/usbd_cdc.c"
  "${BUILD_LIB_PATH}/USBDevice/src/usbd_conf.c"
  DIRECTORY "${BUILD_LIB_PATH}/USBDevice"
  PROPERTIES COMPILE_OPTIONS "-fno-lto")

add_library(mk61_liquidcrystal STATIC
  "${MK61_LIQUIDCRYSTAL_ROOT}/src/LiquidCrystal.cpp")
target_include_directories(mk61_liquidcrystal PUBLIC
  "${MK61_LIQUIDCRYSTAL_ROOT}/src")
target_link_libraries(mk61_liquidcrystal PUBLIC base_config)

add_library(mk61_rtc STATIC
  "${MK61_RTC_ROOT}/src/STM32RTC.cpp"
  "${MK61_RTC_ROOT}/src/rtc.c")
target_include_directories(mk61_rtc PUBLIC "${MK61_RTC_ROOT}/src")
target_link_libraries(mk61_rtc PUBLIC base_config)

file(GLOB _mk61_project_sources CONFIGURE_DEPENDS
  "${MK61_PROJECT_ROOT}/code/*.c"
  "${MK61_PROJECT_ROOT}/code/*.cpp")
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/firmware_main.cpp.in"
  "${CMAKE_BINARY_DIR}/generated/firmware_main.cpp"
  COPYONLY)
list(APPEND _mk61_project_sources
  "${CMAKE_BINARY_DIR}/generated/firmware_main.cpp")

add_executable(resident ${_mk61_project_sources})
target_include_directories(resident PRIVATE "${MK61_PROJECT_ROOT}/code")
target_compile_definitions(resident PRIVATE
  ${_mk61_profile_definitions}
  MK61_ENABLE_FOCAL=${MK61_ENABLE_FOCAL}
  MK61_ENABLE_TINYBASIC=${MK61_ENABLE_TINYBASIC}
  MK61_ENABLE_WBMP_VIEWER=${MK61_ENABLE_WBMP_VIEWER}
  MK61_ENABLE_MARKDOWN_VIEWER=${MK61_ENABLE_MARKDOWN_VIEWER}
  MK61_ENABLE_CHIP8=${MK61_ENABLE_CHIP8}
  MK61_ENABLE_USB_SCREEN=${MK61_ENABLE_USB_SCREEN}
  MK61_WS0010_GRAPHICS_100X16=${MK61_WS0010_GRAPHICS_100X16}
  MK61_ENABLE_EXTENDED_FONT_SETTINGS=${MK61_ENABLE_EXTENDED_FONT_SETTINGS}
  MK61_USER_EXPLORER_SHORTCUT=${MK61_USER_EXPLORER_SHORTCUT}
  MK61_MATH_BACKEND=${MK61_MATH_BACKEND}
  MK61_REQUIRE_RESIDENT_CRC=${MK61_REQUIRE_RESIDENT_CRC})
# Keep the direct F401 path at least as strict as the Arduino release matrix.
# This applies only to project sources; warnings in pinned third-party targets
# stay visible without making their upstream diagnostics our build failures.
target_compile_options(resident PRIVATE
  -Wall
  -Wextra
  -Werror
  -Wno-error=cpp)
target_link_libraries(resident PRIVATE
  stm32_runtime
  SPI
  USBDevice
  mk61_liquidcrystal
  mk61_rtc)
target_link_options(resident PRIVATE
  "LINKER:-Map,${CMAKE_BINARY_DIR}/resident.map"
  "LINKER:--wrap=USBD_CDC_ClearBuffer"
  "LINKER:--wrap=USBD_LL_SetupStage"
  "LINKER:--wrap=USBD_LL_Reset"
  "LINKER:--wrap=USBD_LL_Suspend"
  "LINKER:--wrap=USBD_LL_Resume"
  "LINKER:--wrap=USBD_LL_DevConnected"
  "LINKER:--wrap=USBD_LL_DevDisconnected")

if(MK61_ENABLE_LTO AND
   (MK61_ENABLE_FOCAL OR MK61_ENABLE_TINYBASIC OR
    MK61_ENABLE_WBMP_VIEWER OR MK61_ENABLE_MARKDOWN_VIEWER OR
    MK61_ENABLE_CHIP8))
  set(_mk61_system_app_exports
    "${CMAKE_CURRENT_SOURCE_DIR}/system-app-exports.list")
  if(NOT EXISTS "${_mk61_system_app_exports}")
    message(FATAL_ERROR
      "System APP LTO export list is missing: ${_mk61_system_app_exports}")
  endif()
  # Built-in APP link to exact resident ELF symbols after the resident link.
  # Keep only that ABI surface public; --export-dynamic would retain the
  # complete STM32 HAL and overflow the F401 flash.
  target_link_options(resident PRIVATE
    "LINKER:--export-dynamic-symbol-list=${_mk61_system_app_exports}")
  set_property(TARGET resident APPEND PROPERTY LINK_DEPENDS
    "${_mk61_system_app_exports}")
elseif(MK61_ENABLE_LTO)
  # No built-in APP imports resident symbols through --just-symbols, so the
  # live reference graph (including the user-APP API table) is sufficient for
  # GC. Keep per-function/data sections through the LTO link instead of merged
  # LTRANS data/bss blocks with partition-dependent padding. Do not apply this
  # to System APP builds: exported visibility alone is not a GC root for the
  # direct-symbol ABI used by those separately linked modules.
  target_link_options(resident PRIVATE -ffunction-sections -fdata-sections)
endif()

set_property(TARGET resident APPEND PROPERTY LINK_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/check-flash.cmake")

add_custom_command(TARGET resident POST_BUILD
  COMMAND "${Python3_EXECUTABLE}"
    "${MK61_PROJECT_ROOT}/tests/analyze_stack_usage.py"
    --compile-commands "${CMAKE_BINARY_DIR}/compile_commands.json"
    --source-root "${MK61_PROJECT_ROOT}/code" --top 3
    --max-frame "${MK61_STACK_FRAME_LIMIT}"
    --summary-json "${CMAKE_BINARY_DIR}/stack-usage.json"
  COMMAND "${CMAKE_OBJCOPY}" -O binary
    "$<TARGET_FILE:resident>" "${CMAKE_BINARY_DIR}/resident.bin"
  COMMAND "${CMAKE_OBJCOPY}" -O ihex
    "$<TARGET_FILE:resident>" "${CMAKE_BINARY_DIR}/resident.hex"
  # The laboratory USB Screen + WS0010 graphics combination is close to the
  # F401 limit. Do not accept an image that fits by only a handful of bytes.
  # This gate also runs in local, Windows and macOS builds, not just CI.
  COMMAND "${CMAKE_COMMAND}"
    "-DMK61_BIN=${CMAKE_BINARY_DIR}/resident.bin"
    "-DMK61_FLASH_CAPACITY=${BOARD_MAXSIZE}"
    "-DMK61_FLASH_MIN_HEADROOM=${MK61_FLASH_MIN_HEADROOM}"
    -P "${CMAKE_CURRENT_SOURCE_DIR}/check-flash.cmake"
  # Keep the canonical F401/LTO firmware within our explicit 80% static-RAM
  # budget. Arduino uses a more conservative generic warning threshold; the
  # numeric project budget is the regression contract. USB Screen is an
  # explicit diagnostic build with a separate RAM trade-off.
  COMMAND "${CMAKE_COMMAND}"
    "-DMK61_SIZE_TOOL=${CMAKE_SIZE}"
    "-DMK61_ELF=$<TARGET_FILE:resident>"
    "-DMK61_RAM_CAPACITY=${BOARD_MAXDATASIZE}"
    "-DMK61_GLOBAL_RAM_LIMIT=${MK61_GLOBAL_RAM_LIMIT}"
    -P "${CMAKE_CURRENT_SOURCE_DIR}/check-ram.cmake"
  COMMAND "${CMAKE_SIZE}" "$<TARGET_FILE:resident>"
  BYPRODUCTS
    "${CMAKE_BINARY_DIR}/resident.bin"
    "${CMAKE_BINARY_DIR}/resident.hex"
  VERBATIM)
