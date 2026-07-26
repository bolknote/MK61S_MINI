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

project(mk61s_f401_gcc LANGUAGES C CXX ASM)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

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
if(NOT _mk61_platform_text MATCHES "(^|\n)version=2\\.12\\.0(\r?\n|$)")
  message(FATAL_ERROR "STM32 Arduino Core 2.12.0 is required")
endif()

foreach(_mk61_bool
    MK61_ENABLE_FOCAL
    MK61_ENABLE_TINYBASIC
    MK61_ENABLE_WBMP_VIEWER
    MK61_ENABLE_CHIP8
    MK61_ENABLE_USB_SCREEN
    MK61_ENABLE_EXTENDED_FONT_SETTINGS
    MK61_USER_EXPLORER_SHORTCUT
    MK61_MATH_BACKEND)
  if(NOT DEFINED ${_mk61_bool})
    message(FATAL_ERROR "${_mk61_bool} is required")
  endif()
  if(NOT "${${_mk61_bool}}" MATCHES "^[01]$")
    message(FATAL_ERROR "${_mk61_bool} must be 0 or 1")
  endif()
endforeach()

set(_mk61_profile_definitions)
if(MK61_PROFILE STREQUAL "mini-v3-a00")
  list(APPEND _mk61_profile_definitions MK61_LCD1602_A00)
elseif(MK61_PROFILE STREQUAL "mini-v3-a02")
  list(APPEND _mk61_profile_definitions MK61_LCD1602_A02)
elseif(MK61_PROFILE STREQUAL "mini-v2-a00")
  list(APPEND _mk61_profile_definitions REVISION_V2 MK61_LCD1602_A00)
elseif(MK61_PROFILE STREQUAL "mini-v2-a02")
  list(APPEND _mk61_profile_definitions REVISION_V2 MK61_LCD1602_A02)
elseif(MK61_PROFILE STREQUAL "classic-v2")
  list(APPEND _mk61_profile_definitions MK61_BOARD_CLASSIC_V2)
elseif(MK61_PROFILE STREQUAL "classic-v3")
  list(APPEND _mk61_profile_definitions MK61_BOARD_CLASSIC_V3)
elseif(MK61_PROFILE STREQUAL "40th")
  list(APPEND _mk61_profile_definitions MK61_BOARD_40TH)
else()
  message(FATAL_ERROR "Unsupported MK61_PROFILE: ${MK61_PROFILE}")
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
  BLACKPILL_F401CC_serial_generic
  BLACKPILL_F401CC_usb_CDCgen
  BLACKPILL_F401CC_xusb_FS)

include("${CORE_PATH}/cmake/overall_settings.cmake")
overall_settings(OPTIMIZATION s)
target_compile_definitions(user_settings INTERFACE
  ARDUINO=10607
  VECT_TAB_OFFSET=0x0)

include("${CORE_PATH}/cmake/set_base_arduino_config.cmake")
add_subdirectory("${BUILD_VARIANT_PATH}" "${CMAKE_BINARY_DIR}/stm32/variant")
add_subdirectory("${BUILD_CORE_PATH}" "${CMAKE_BINARY_DIR}/stm32/core")
add_subdirectory("${BUILD_LIB_PATH}" "${CMAKE_BINARY_DIR}/stm32/libraries")

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
  MK61_ENABLE_CHIP8=${MK61_ENABLE_CHIP8}
  MK61_ENABLE_USB_SCREEN=${MK61_ENABLE_USB_SCREEN}
  MK61_ENABLE_EXTENDED_FONT_SETTINGS=${MK61_ENABLE_EXTENDED_FONT_SETTINGS}
  MK61_USER_EXPLORER_SHORTCUT=${MK61_USER_EXPLORER_SHORTCUT}
  MK61_MATH_BACKEND=${MK61_MATH_BACKEND})
target_link_libraries(resident PRIVATE
  stm32_runtime
  SPI
  USBDevice
  mk61_liquidcrystal
  mk61_rtc)
target_link_options(resident PRIVATE
  "LINKER:-Map,${CMAKE_BINARY_DIR}/resident.map")

add_custom_command(TARGET resident POST_BUILD
  COMMAND "${CMAKE_OBJCOPY}" -O binary
    "$<TARGET_FILE:resident>" "${CMAKE_BINARY_DIR}/resident.bin"
  COMMAND "${CMAKE_OBJCOPY}" -O ihex
    "$<TARGET_FILE:resident>" "${CMAKE_BINARY_DIR}/resident.hex"
  COMMAND "${CMAKE_SIZE}" "$<TARGET_FILE:resident>"
  BYPRODUCTS
    "${CMAKE_BINARY_DIR}/resident.bin"
    "${CMAKE_BINARY_DIR}/resident.hex"
  VERBATIM)
