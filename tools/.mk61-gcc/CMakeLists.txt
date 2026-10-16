cmake_minimum_required(VERSION 3.21)

if(NOT DEFINED MK61_PROJECT_ROOT OR NOT IS_DIRECTORY "${MK61_PROJECT_ROOT}")
  message(FATAL_ERROR "MK61_PROJECT_ROOT must point to the project directory")
endif()

project(mk61s_stm32_gcc LANGUAGES C CXX ASM)

if(CMAKE_HOST_WIN32)
  if(NOT DEFINED MK61_POWERSHELL OR
     NOT EXISTS "${MK61_POWERSHELL}")
    message(FATAL_ERROR
      "MK61_POWERSHELL must name Windows PowerShell 5.1 or newer")
  endif()
  if(NOT DEFINED MK61_PROFILE_DEFINITIONS)
    message(FATAL_ERROR
      "MK61_PROFILE_DEFINITIONS is required on Windows")
  endif()
else()
  find_package(Python3 3 REQUIRED COMPONENTS Interpreter)
endif()

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
include("${CMAKE_CURRENT_SOURCE_DIR}/native-sdk.cmake")

if(NOT DEFINED MK61_USE_COMPACT_LIBM)
  set(MK61_USE_COMPACT_LIBM 1)
endif()
if(NOT DEFINED MK61_USE_NATIVE_EABI)
  set(MK61_USE_NATIVE_EABI 1)
endif()
if(NOT DEFINED MK61_USE_NATIVE_LIBC)
  set(MK61_USE_NATIVE_LIBC 1)
endif()

foreach(_mk61_bool
    MK61_ENABLE_FOCAL
    MK61_ENABLE_TINYBASIC
    MK61_ENABLE_WBMP_VIEWER
    MK61_ENABLE_MARKDOWN_VIEWER
    MK61_ENABLE_CHIP8
    MK61_ENABLE_SETUP
    MK61_FOCAL_AS_APP
    MK61_TINYBASIC_AS_APP
    MK61_WBMP_VIEWER_AS_APP
    MK61_MARKDOWN_VIEWER_AS_APP
    MK61_CHIP8_AS_APP
    MK61_SETUP_AS_APP
    MK61_EXPLORER_AS_APP
    MK61_ENABLE_USB_SCREEN
    MK61_EXTERNALIZE_USBDISK
    MK61_WS0010_GRAPHICS_100X16
    MK61_ENABLE_EXTENDED_FONT_SETTINGS
    MK61_USER_EXPLORER_SHORTCUT
    MK61_APP_LOCAL_FLOAT_MATH
    MK61_USE_COMPACT_LIBM
    MK61_USE_NATIVE_EABI
    MK61_USE_NATIVE_LIBC
    MK61_F401_PRODUCT_BUILD
    MK61_REQUIRE_RESIDENT_CRC
    MK61_ENABLE_LTO)
  if(NOT DEFINED ${_mk61_bool})
    message(FATAL_ERROR "${_mk61_bool} is required")
  endif()
  if(NOT "${${_mk61_bool}}" MATCHES "^[01]$")
    message(FATAL_ERROR "${_mk61_bool} must be 0 or 1")
  endif()
endforeach()

if(NOT DEFINED MK61_MATH_BACKEND OR
   NOT "${MK61_MATH_BACKEND}" MATCHES "^[01]$")
  message(FATAL_ERROR "MK61_MATH_BACKEND must be 0 or 1")
endif()

if(CMAKE_HOST_WIN32)
  set(_mk61_profile_definitions "${MK61_PROFILE_DEFINITIONS}")
else()
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
endif()

# The pinned project SDK supplies headers only. Every compiled implementation
# belongs to this project; no external Core, HAL or Arduino library is built.
set(MK61_TARGET_MCU "f401" CACHE STRING "Qualified STM32 target: f401 or f411")
if(MK61_TARGET_MCU STREQUAL "f411")
  set(_mk61_device STM32F411xE)
  set(_mk61_board BLACKPILL_F411CE)
  set(BOARD_MAXSIZE 524288)
  set(BOARD_MAXDATASIZE 131072)
  set(_mk61_frequency 96000000UL)
  set(_mk61_size_option -Os)
elseif(MK61_TARGET_MCU STREQUAL "f401")
  set(_mk61_device STM32F401xC)
  set(_mk61_board BLACKPILL_F401CC)
  set(BOARD_MAXSIZE 262144)
  set(BOARD_MAXDATASIZE 65536)
  set(_mk61_frequency 84000000UL)
  set(_mk61_size_option -Oz)
else()
  message(FATAL_ERROR "MK61_TARGET_MCU must be f401 or f411")
endif()
set(MK61_COLD_OPTIMIZATION "${_mk61_size_option}" CACHE STRING "Size optimization: -Os or -Oz")
if(NOT MK61_COLD_OPTIMIZATION MATCHES "^-O[sz]$")
  message(FATAL_ERROR "MK61_COLD_OPTIMIZATION must be -Os or -Oz")
endif()
set(_mk61_size_option "${MK61_COLD_OPTIMIZATION}")
set(_mk61_portable_ld "${CMAKE_BINARY_DIR}/portable-resident.ld")
configure_file("${CMAKE_CURRENT_SOURCE_DIR}/standalone/resident.ld"
  "${_mk61_portable_ld}" COPYONLY)

add_library(user_settings INTERFACE)
target_compile_options(user_settings INTERFACE
  -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
  -Wa,--noexecstack
  ${_mk61_size_option} -ffunction-sections -fdata-sections
  "$<$<COMPILE_LANGUAGE:CXX>:-fno-rtti;-fno-exceptions;-fno-use-cxa-atexit;-fno-threadsafe-statics>"
  "$<$<COMPILE_LANGUAGE:CXX>:--param=max-inline-insns-single=500>")
target_link_options(user_settings INTERFACE
  -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
  ${_mk61_size_option} -nostartfiles --specs=nano.specs --specs=nosys.specs
  # GCC LTO assembler outputs must declare a non-executable GNU stack too.
  -Wa,--noexecstack
  "LINKER:--gc-sections"
  "LINKER:--default-script=${_mk61_portable_ld}"
  "LINKER:--defsym=LD_FLASH_OFFSET=0"
  "LINKER:--defsym=LD_MAX_SIZE=${BOARD_MAXSIZE}"
  "LINKER:--defsym=LD_MAX_DATA_SIZE=${BOARD_MAXDATASIZE}")
if(MK61_ENABLE_LTO)
  target_compile_options(user_settings INTERFACE -flto)
  target_link_options(user_settings INTERFACE -flto -flto-partition=one)
endif()
if(MK61_TARGET_MCU STREQUAL "f401")
  target_compile_options(user_settings INTERFACE
    -flto-partition=one -fipa-pta -fno-inline-functions-called-once)
  target_link_options(user_settings INTERFACE
    -flto-partition=one -fipa-pta -fno-inline-functions-called-once)
endif()
target_compile_definitions(user_settings INTERFACE
  ${_mk61_device} STM32F4xx USE_FULL_LL_DRIVER NDEBUG
  MK61_NATIVE_RUNTIME=1 F_CPU=${_mk61_frequency}
  # Source compatibility markers; no Arduino implementation is linked.
  ARDUINO=10607 ARDUINO_ARCH_STM32 ARDUINO_${_mk61_board}
  BOARD_NAME="${_mk61_board}" VECT_TAB_OFFSET=0x0
  USBCON USBD_USE_CDC HWSERIAL_NONE HAL_PCD_MODULE_ENABLED
  USBD_VID=0x0483 USBD_PID=0x5740 USBD_CLASS_USER_STRING_DESC=0
  USBD_MAX_STR_DESC_SIZ=64)
target_include_directories(user_settings INTERFACE
  "${CMAKE_CURRENT_SOURCE_DIR}/standalone"
  "${MK61_PROJECT_ROOT}/code"
  "${MK61_SDK_ROOT}/hal/include"
  "${MK61_SDK_ROOT}/device/include"
  "${MK61_SDK_ROOT}/cmsis/include"
  "${MK61_SDK_ROOT}/usb-interface/include"
  "${MK61_SDK_ROOT}/usb/include")

target_compile_options(user_settings INTERFACE
  "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include \"${MK61_PROJECT_ROOT}/code/stm32f4_usbd_def.h\">"
  "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include \"${MK61_PROJECT_ROOT}/code/stm32f4_usbd_cdc.h\">")

# Preserve the real middleware call boundaries needed by GNU ld --wrap.
set_source_files_properties("${MK61_PROJECT_ROOT}/code/stm32f4_usbd_core.c"
  PROPERTIES COMPILE_OPTIONS "-fno-lto")
set_source_files_properties("${MK61_PROJECT_ROOT}/code/stm32f4_usbd_cdc.c"
  PROPERTIES COMPILE_DEFINITIONS "MK61_USB_BUILD_CDC=1" COMPILE_OPTIONS "-fno-lto")
set_source_files_properties("${MK61_PROJECT_ROOT}/code/stm32f4_cdc_if.c"
  PROPERTIES COMPILE_DEFINITIONS "MK61_USB_BUILD_CDC_IF=1")
set_source_files_properties("${MK61_PROJECT_ROOT}/code/stm32f4_usb_device.cpp"
  PROPERTIES COMPILE_DEFINITIONS "MK61_USB_BUILD_BRIDGE=1")
set_source_files_properties("${MK61_PROJECT_ROOT}/code/stm32f4_usbd_ctlreq.c"
  PROPERTIES COMPILE_DEFINITIONS "MK61_USB_BUILD_CTLREQ=1")
set_source_files_properties("${MK61_PROJECT_ROOT}/code/system_strings.c"
  PROPERTIES COMPILE_OPTIONS "-fno-builtin;-fno-lto")
set_source_files_properties("${MK61_PROJECT_ROOT}/code/native_eabi.cpp"
  PROPERTIES COMPILE_OPTIONS "-fno-lto")
set_source_files_properties("${MK61_PROJECT_ROOT}/code/compact_math.cpp"
  PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
if(MK61_TARGET_MCU STREQUAL "f411")
  # The measured emulator policy matches the Arduino control image exactly.
  set_source_files_properties("${MK61_PROJECT_ROOT}/code/mk61emu_core.cpp"
    PROPERTIES COMPILE_OPTIONS "-fno-lto")
endif()

file(GLOB _mk61_project_sources CONFIGURE_DEPENDS
  "${MK61_PROJECT_ROOT}/code/*.c"
  "${MK61_PROJECT_ROOT}/code/*.cpp")
# Native UC1609 renders through our framebuffer, never the generic graphics base.
list(FILTER _mk61_project_sources EXCLUDE REGEX "/ERM19264_graphics\\.cpp$")
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/firmware_main.cpp.in"
  "${CMAKE_BINARY_DIR}/generated/firmware_main.cpp"
  COPYONLY)
list(APPEND _mk61_project_sources
  "${CMAKE_BINARY_DIR}/generated/firmware_main.cpp")

add_executable(resident ${_mk61_project_sources}
  "${MK61_PROJECT_ROOT}/code/stm32f4_startup.S"
  "${MK61_PROJECT_ROOT}/code/native_eabi_arm.S"
  "${MK61_PROJECT_ROOT}/code/native_eabi_fixed.S")
target_include_directories(resident PRIVATE "${MK61_PROJECT_ROOT}/code")
target_compile_definitions(resident PRIVATE
  ${_mk61_profile_definitions}
  ${MK61_CASE_DEFINITIONS}
  MK61_ENABLE_FOCAL=${MK61_ENABLE_FOCAL}
  MK61_ENABLE_TINYBASIC=${MK61_ENABLE_TINYBASIC}
  MK61_ENABLE_WBMP_VIEWER=${MK61_ENABLE_WBMP_VIEWER}
  MK61_ENABLE_MARKDOWN_VIEWER=${MK61_ENABLE_MARKDOWN_VIEWER}
  MK61_ENABLE_CHIP8=${MK61_ENABLE_CHIP8}
  MK61_ENABLE_SETUP=${MK61_ENABLE_SETUP}
  MK61_FOCAL_AS_APP=${MK61_FOCAL_AS_APP}
  MK61_TINYBASIC_AS_APP=${MK61_TINYBASIC_AS_APP}
  MK61_WBMP_VIEWER_AS_APP=${MK61_WBMP_VIEWER_AS_APP}
  MK61_MARKDOWN_VIEWER_AS_APP=${MK61_MARKDOWN_VIEWER_AS_APP}
  MK61_CHIP8_AS_APP=${MK61_CHIP8_AS_APP}
  MK61_SETUP_AS_APP=${MK61_SETUP_AS_APP}
  MK61_EXPLORER_AS_APP=${MK61_EXPLORER_AS_APP}
  MK61_ENABLE_USB_SCREEN=${MK61_ENABLE_USB_SCREEN}
  MK61_EXTERNALIZE_USBDISK=${MK61_EXTERNALIZE_USBDISK}
  MK61_WS0010_GRAPHICS_100X16=${MK61_WS0010_GRAPHICS_100X16}
  MK61_ENABLE_EXTENDED_FONT_SETTINGS=${MK61_ENABLE_EXTENDED_FONT_SETTINGS}
  MK61_USER_EXPLORER_SHORTCUT=${MK61_USER_EXPLORER_SHORTCUT}
  MK61_MATH_BACKEND=${MK61_MATH_BACKEND}
  MK61_APP_LOCAL_FLOAT_MATH=${MK61_APP_LOCAL_FLOAT_MATH}
  MK61_USE_COMPACT_LIBM=${MK61_USE_COMPACT_LIBM}
  MK61_USE_NATIVE_EABI=${MK61_USE_NATIVE_EABI}
  MK61_USE_NATIVE_LIBC=${MK61_USE_NATIVE_LIBC}
  MK61_F401_PRODUCT_BUILD=${MK61_F401_PRODUCT_BUILD}
  MK61_ENABLE_LOADABLE_MODULES=1
  MK61_REQUIRE_RESIDENT_CRC=${MK61_REQUIRE_RESIDENT_CRC}
  # F401 release builds deliberately combine global -Os(+LTO) with O3 only
  # on the measured emulator loops.  Fail configuration drift instead of
  # silently shipping a uniformly size-optimised core.
)
if(MK61_TARGET_MCU STREQUAL "f401")
  target_compile_definitions(resident PRIVATE MK61_REQUIRE_F401_SELECTIVE_O3=1)
else()
  target_compile_definitions(resident PRIVATE MK61_REQUIRE_F411_SELECTIVE_O3=1)
endif()
# Keep the direct F401 path at least as strict as the Arduino release matrix.
# This applies only to project sources; warnings in pinned third-party targets
# stay visible without making their upstream diagnostics our build failures.
target_compile_options(resident PRIVATE
  -Wall
  -Wextra
  -Werror
  -Wno-error=cpp)
target_link_libraries(resident PRIVATE user_settings)
if(MK61_USE_NATIVE_EABI AND MK61_USE_NATIVE_LIBC AND MK61_USE_COMPACT_LIBM)
  target_link_options(resident PRIVATE -nostdlib)
else()
  target_link_libraries(resident PRIVATE -Wl,--start-group m c stdc++ gcc -Wl,--end-group)
endif()
target_link_options(resident PRIVATE
  "LINKER:-Map,${CMAKE_BINARY_DIR}/resident.map"
  "LINKER:--wrap=USBD_CDC_ClearBuffer"
  "LINKER:--wrap=USBD_LL_SetupStage"
  "LINKER:--wrap=USBD_LL_Reset"
  "LINKER:--wrap=USBD_LL_Suspend"
  "LINKER:--wrap=USBD_LL_Resume"
  "LINKER:--wrap=USBD_LL_DevConnected"
  "LINKER:--wrap=USBD_LL_DevDisconnected")

if(MK61_ENABLE_LTO)
  # APPs reach resident code only through public C tables. Keep per-function
  # and data sections through the LTO link; no resident symbols are exported.
  target_link_options(resident PRIVATE -ffunction-sections -fdata-sections)
endif()

set_property(TARGET resident APPEND PROPERTY LINK_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/check-flash.cmake")
set_property(TARGET resident APPEND PROPERTY LINK_DEPENDS "${_mk61_portable_ld}")

if(CMAKE_HOST_WIN32)
  set(_mk61_stack_analysis_command
    "${MK61_POWERSHELL}" -NoLogo -NoProfile -File
    "${MK61_PROJECT_ROOT}/tests/analyze-stack-usage.ps1"
    -CompileCommands "${CMAKE_BINARY_DIR}/compile_commands.json"
    -SourceRoot "${MK61_PROJECT_ROOT}/code" -Top 3
    -MaxFrame "${MK61_STACK_FRAME_LIMIT}"
    -SummaryJson "${CMAKE_BINARY_DIR}/stack-usage.json")
else()
  set(_mk61_stack_analysis_command
    "${Python3_EXECUTABLE}"
    "${MK61_PROJECT_ROOT}/tests/analyze_stack_usage.py"
    --compile-commands "${CMAKE_BINARY_DIR}/compile_commands.json"
    --source-root "${MK61_PROJECT_ROOT}/code" --top 3
    --max-frame "${MK61_STACK_FRAME_LIMIT}"
    --summary-json "${CMAKE_BINARY_DIR}/stack-usage.json")
endif()

add_custom_command(TARGET resident POST_BUILD
  COMMAND ${_mk61_stack_analysis_command}
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
