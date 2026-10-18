cmake_minimum_required(VERSION 3.20)

set(PICO_BOARD mk61_picocalc_pico_h CACHE STRING "PicoCalc/Pico H board")
set(PICO_BOARD_HEADER_DIRS "${CMAKE_CURRENT_LIST_DIR}/boards")
# UF2 packaging is performed by the Python builder, without a host picotool
# download during CMake configuration. The SDK still owns boot2 and linking.
set(PICO_NO_PICOTOOL 1)
if(NOT PICO_SDK_PATH AND DEFINED ENV{PICO_SDK_PATH})
    set(PICO_SDK_PATH "$ENV{PICO_SDK_PATH}")
endif()
if(NOT EXISTS "${PICO_SDK_PATH}/pico_sdk_init.cmake")
    message(FATAL_ERROR "Pass -DPICO_SDK_PATH=/path/to/pico-sdk (2.2.0)")
endif()
include("${PICO_SDK_PATH}/pico_sdk_init.cmake")
project(mk61s_picocalc C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
pico_sdk_init()
if(NOT PICO_RP2040 OR NOT PICO_BOARD STREQUAL "mk61_picocalc_pico_h")
    message(FATAL_ERROR "This prototype supports only PicoCalc with Pico H/RP2040")
endif()

set(MK61_ROOT "${CMAKE_CURRENT_LIST_DIR}/../..")
add_executable(mk61s-picocalc-pico-h
    main.cpp hardware.cpp calculator.cpp screen.cpp math_probe.cpp ui.cpp markdown.cpp terminal.cpp fonts.cpp diagnostics.cpp firmware.cpp native_display.cpp canvas.cpp
    settings.cpp device_settings.cpp sd_card.cpp block_transfer.cpp storage.cpp usb_device.cpp services.cpp service_runtime.cpp
    script_files.cpp script_runtime.cpp input.cpp clock.cpp power.cpp chip8_runtime.cpp native_app.cpp native_runtime.cpp usb_screen.cpp
    "${MK61_ROOT}/third_party/fatfs/ff.c"
    "${MK61_ROOT}/third_party/fatfs/ffunicode.c"
    "${MK61_ROOT}/code/mk61emu_core.cpp"
    "${MK61_ROOT}/code/compact_math.cpp"
    "${MK61_ROOT}/code/ERM19264_graphics_font.cpp"
    "${MK61_ROOT}/code/calculator_face.cpp"
    "${MK61_ROOT}/code/text_screen.cpp"
    "${MK61_ROOT}/code/builtin_font.cpp"
    "${MK61_ROOT}/code/ui_font.cpp"
    "${MK61_ROOT}/code/fmk_font.cpp" "${MK61_ROOT}/code/prepared_font.cpp" "${MK61_ROOT}/code/fmk_prepare.cpp")
target_sources(mk61s-picocalc-pico-h PRIVATE
    "${MK61_ROOT}/code/language_bytecode.cpp"
    "${MK61_ROOT}/code/language_vm.cpp"
    "${MK61_ROOT}/code/basic_graphics.cpp")
target_sources(mk61s-picocalc-pico-h PRIVATE "${MK61_ROOT}/code/basic_native_io.cpp" "${MK61_ROOT}/code/app_flow.cpp")
target_sources(mk61s-picocalc-pico-h PRIVATE
    "${MK61_ROOT}/code/m61_text.cpp" "${MK61_ROOT}/code/m61_print.cpp"
    "${MK61_ROOT}/code/m61_ansi.cpp" "${MK61_ROOT}/code/terminal_script_runtime.cpp"
    "${MK61_ROOT}/code/terminal_catalog.cpp" "${MK61_ROOT}/code/terminal_key_sequence.cpp"
    "${MK61_ROOT}/code/program_load.cpp" "${MK61_ROOT}/code/zx0_stream.cpp")
target_sources(mk61s-picocalc-pico-h PRIVATE "${MK61_ROOT}/code/calculator_control.cpp"
    "${MK61_ROOT}/code/chip8.cpp" "${MK61_ROOT}/code/usb_screen_protocol.cpp"
    "${MK61_ROOT}/code/loadable_module_format.cpp" "${MK61_ROOT}/code/zx0.cpp")
target_sources(mk61s-picocalc-pico-h PRIVATE "${MK61_ROOT}/code/markdown_document.cpp" "${MK61_ROOT}/code/wbmp.cpp"
    "${MK61_ROOT}/code/explorer_autoexec.cpp")
target_sources(mk61s-picocalc-pico-h PRIVATE "${MK61_ROOT}/code/usb_screen_surface.cpp" "${MK61_ROOT}/code/ui_text_renderer.cpp")
target_sources(mk61s-picocalc-pico-h PRIVATE "${MK61_ROOT}/code/crash_dump_format.cpp")
if(DEFINED MK61_PICOCALC_BUILD_ID)
    target_compile_definitions(mk61s-picocalc-pico-h PRIVATE MK61_PICOCALC_BUILD_ID=${MK61_PICOCALC_BUILD_ID})
endif()
target_include_directories(mk61s-picocalc-pico-h PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}" "${MK61_ROOT}/code" "${MK61_ROOT}/third_party/fatfs")
target_compile_definitions(mk61s-picocalc-pico-h PRIVATE
    MK61_CORE_STANDALONE=1
    # Allocation failures are handled by the resident/APP ABI. The SDK's
    # default panic would turn a recoverable exhausted lease into HardFault.
    PICO_MALLOC_PANIC=0
    MK61_ENABLE_RTC_ALARM_TERMINAL=1
    MK61_ENABLE_USB_SCREEN=1
    MK61_M61_READ_CACHE_BYTES=1024
    MK61_USE_COMPACT_LIBM=1 MK61_MATH_BACKEND=0 MK61_USE_NATIVE_EABI=0
    PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=0
    PICO_STDIO_USB_ENABLE_RESET_VIA_BAUD_RATE=1
    PICO_STDIO_USB_ENABLE_IRQ_BACKGROUND_TASK=0
    PICO_STDIO_USB_USE_DEFAULT_DESCRIPTORS=0
    PICO_STDIO_USB_ENABLE_RESET_VIA_VENDOR_INTERFACE=0
    PICO_STDIO_USB_RESET_INTERFACE_SUPPORT_MS_OS_20_DESCRIPTOR=0
    PICO_STACK_SIZE=32768
    PICO_STDIO_DEFAULT_CRLF=1)
target_compile_options(mk61s-picocalc-pico-h PRIVATE
    -fstack-usage
    $<$<COMPILE_LANGUAGE:CXX>:-Wall;-Wextra;-Wno-unused-parameter;-Wno-unused-variable>)
# Keep the portable decoder for the first hardware qualification.
set_source_files_properties("${MK61_ROOT}/code/mk61emu_core.cpp"
    PROPERTIES COMPILE_OPTIONS "-O3")
target_link_libraries(mk61s-picocalc-pico-h PRIVATE
    pico_stdlib hardware_rtc hardware_spi hardware_i2c hardware_watchdog hardware_pwm hardware_pll
    hardware_flash pico_flash pico_rand tinyusb_device tinyusb_board pico_unique_id)
pico_enable_stdio_uart(mk61s-picocalc-pico-h 1)
pico_enable_stdio_usb(mk61s-picocalc-pico-h 1)
# SDK/bootrom arithmetic does not promise full IEEE subnormal semantics.
# The shared math kernels and native APP ABI require gradual underflow.
pico_set_float_implementation(mk61s-picocalc-pico-h compiler)
pico_set_double_implementation(mk61s-picocalc-pico-h compiler)
pico_set_program_name(mk61s-picocalc-pico-h "MK61S PicoCalc Pico H")
pico_set_program_version(mk61s-picocalc-pico-h "0.8.0")
# The SDK normally puts core 0's stack in the 4 KiB scratch bank. Source
# compilers and FatFs need a larger, separately reserved stack. Keep the SDK
# section layout and split the same 264 KiB SRAM into 224+4+36 KiB regions.
file(READ "${PICO_SDK_PATH}/src/rp2_common/pico_crt0/rp2040/memmap_default.ld" MK61_MEMMAP)
string(REPLACE "RAM(rwx) : ORIGIN =  0x20000000, LENGTH = 256k"
    "RAM(rwx) : ORIGIN =  0x20000000, LENGTH = 224k" MK61_MEMMAP "${MK61_MEMMAP}")
string(REPLACE "SCRATCH_X(rwx) : ORIGIN = 0x20040000, LENGTH = 4k"
    "SCRATCH_X(rwx) : ORIGIN = 0x20041000, LENGTH = 4k" MK61_MEMMAP "${MK61_MEMMAP}")
string(REPLACE "SCRATCH_Y(rwx) : ORIGIN = 0x20041000, LENGTH = 4k"
    "SCRATCH_Y(rwx) : ORIGIN = 0x20038000, LENGTH = 36k" MK61_MEMMAP "${MK61_MEMMAP}")
string(REPLACE ".rodata : {"
    ".mk61_fw_footer : { KEEP(*(.mk61_fw_footer)) } > FLASH\n\n    .rodata : {"
    MK61_MEMMAP "${MK61_MEMMAP}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/picocalc-memmap.ld" "${MK61_MEMMAP}")
pico_set_linker_script(mk61s-picocalc-pico-h "${CMAKE_CURRENT_BINARY_DIR}/picocalc-memmap.ld")
pico_add_extra_outputs(mk61s-picocalc-pico-h)
