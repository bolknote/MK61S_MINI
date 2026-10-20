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
option(MK61_PICOCALC_M0_EABI "Use project-owned ARMv6-M arithmetic" ON)
option(MK61_PICOCALC_SAMPLE_PROFILE "Diagnostic-only 1 kHz PC sampling on core 0" OFF)
add_executable(mk61s-picocalc-pico-h
    main.cpp hardware.cpp io_worker.cpp calculator.cpp screen.cpp math_probe.cpp ui.cpp markdown.cpp terminal.cpp fonts.cpp diagnostics.cpp firmware.cpp native_display.cpp canvas.cpp
    settings.cpp device_settings.cpp sd_card.cpp block_transfer.cpp storage.cpp storage_journal.cpp usb_device.cpp services.cpp service_runtime.cpp
    script_files.cpp script_runtime.cpp language_cache.cpp input.cpp clock.cpp power.cpp chip8_runtime.cpp native_app.cpp native_runtime.cpp usb_screen.cpp
    "${MK61_ROOT}/third_party/fatfs/ff.c"
    "${MK61_ROOT}/third_party/fatfs/ffunicode.c"
    "${MK61_ROOT}/code/mk61emu_core.cpp"
    "${MK61_ROOT}/code/compact_math.cpp"
    "${MK61_ROOT}/code/native_eabi_m0.cpp"
    "${MK61_ROOT}/code/native_eabi_m0.S"
    "${MK61_ROOT}/code/native_eabi_m0_rp2040.S"
    "${MK61_ROOT}/code/ERM19264_graphics_font.cpp"
    "${MK61_ROOT}/code/calculator_face.cpp"
    "${MK61_ROOT}/code/text_screen.cpp"
    "${MK61_ROOT}/code/builtin_font.cpp"
    "${MK61_ROOT}/code/ui_font.cpp"
    "${MK61_ROOT}/code/fmk_font.cpp" "${MK61_ROOT}/code/prepared_font.cpp" "${MK61_ROOT}/code/fmk_prepare.cpp")
target_sources(mk61s-picocalc-pico-h PRIVATE
    "${MK61_ROOT}/code/language_bytecode.cpp"
    "${MK61_ROOT}/code/language_vm.cpp"
    "${MK61_ROOT}/code/language_vm_file_cache.cpp"
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
    MK61_PICOCALC_SAMPLE_PROFILE=$<BOOL:${MK61_PICOCALC_SAMPLE_PROFILE}>
    # Allocation failures are handled by the resident/APP ABI. The SDK's
    # default panic would turn a recoverable exhausted lease into HardFault.
    PICO_MALLOC_PANIC=0
    MK61_ENABLE_RTC_ALARM_TERMINAL=1
    MK61_ENABLE_USB_SCREEN=1
    MK61_M61_READ_CACHE_BYTES=2048
    MK61_USE_COMPACT_LIBM=1 MK61_MATH_BACKEND=0 MK61_USE_NATIVE_EABI=0
    MK61_USE_M0_EABI=$<BOOL:${MK61_PICOCALC_M0_EABI}>
    MK61_M0_RP2040_EABI=$<BOOL:${MK61_PICOCALC_M0_EABI}>
    PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=0
    PICO_STDIO_USB_ENABLE_RESET_VIA_BAUD_RATE=1
    PICO_STDIO_USB_ENABLE_IRQ_BACKGROUND_TASK=0
    PICO_STDIO_USB_USE_DEFAULT_DESCRIPTORS=0
    PICO_STDIO_USB_ENABLE_RESET_VIA_VENDOR_INTERFACE=0
    PICO_STDIO_USB_RESET_INTERFACE_SUPPORT_MS_OS_20_DESCRIPTOR=0
    PICO_STACK_SIZE=32768
    PICO_CORE1_STACK_SIZE=2048
    PICO_STDIO_DEFAULT_CRLF=1)
target_compile_options(mk61s-picocalc-pico-h PRIVATE
    -fstack-usage
    $<$<COMPILE_LANGUAGE:CXX>:-Wall;-Wextra;-Wno-unused-parameter;-Wno-unused-variable>)
# Both resident interpreters are hot code on RP2040. Keep IEEE semantics;
# this changes optimization level only, without fast-math or M4 instructions.
set_source_files_properties("${MK61_ROOT}/code/mk61emu_core.cpp"
    "${MK61_ROOT}/code/language_vm.cpp"
    PROPERTIES COMPILE_OPTIONS "-O3")
# Keep the typed arithmetic ABI separate from the APP table's erased function
# declarations, including in builds where the user enables global LTO.
set_source_files_properties("${MK61_ROOT}/code/native_eabi_m0.cpp"
    PROPERTIES COMPILE_OPTIONS "-fno-lto")
target_link_libraries(mk61s-picocalc-pico-h PRIVATE
    pico_stdlib pico_multicore hardware_rtc hardware_spi hardware_i2c hardware_watchdog hardware_pwm hardware_pll
    hardware_flash hardware_dma pico_flash pico_rand tinyusb_device tinyusb_board pico_unique_id)
if(MK61_PICOCALC_SAMPLE_PROFILE)
    target_link_libraries(mk61s-picocalc-pico-h PRIVATE hardware_exception)
endif()
pico_enable_stdio_uart(mk61s-picocalc-pico-h 1)
pico_enable_stdio_usb(mk61s-picocalc-pico-h 1)
# Disable SDK/bootrom float wrappers. Our runtime (or the explicit GCC control)
# implements IEEE gradual underflow; keep SDK's interrupt-safe SIO divider.
pico_set_float_implementation(mk61s-picocalc-pico-h compiler)
pico_set_double_implementation(mk61s-picocalc-pico-h compiler)
pico_set_program_name(mk61s-picocalc-pico-h "MK61S PicoCalc Pico H")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_LIST_DIR}/version.hpp")
file(READ "${CMAKE_CURRENT_LIST_DIR}/version.hpp" MK61_VERSION_HEADER)
string(REGEX MATCH "VERSION\\[\\] *= *\"([0-9]+\\.[0-9]+\\.[0-9]+)\"" MK61_VERSION_MATCH "${MK61_VERSION_HEADER}")
if(NOT MK61_VERSION_MATCH)
    message(FATAL_ERROR "version.hpp must define a semantic VERSION")
endif()
pico_set_program_version(mk61s-picocalc-pico-h "${CMAKE_MATCH_1}")
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
string(REPLACE "    .scratch_y : {"
    "    .lcd_dma (NOLOAD) : { *(.lcd_dma.*) . = ALIGN(4); __lcd_dma_end__ = .; } > SCRATCH_X :NONE\n\n    .scratch_y : {"
    MK61_MEMMAP "${MK61_MEMMAP}")
string(APPEND MK61_MEMMAP "\nASSERT(__lcd_dma_end__ <= __StackOneBottom, \"LCD DMA buffers overlap core 1 stack\")\n")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/picocalc-memmap.ld" "${MK61_MEMMAP}")
pico_set_linker_script(mk61s-picocalc-pico-h "${CMAKE_CURRENT_BINARY_DIR}/picocalc-memmap.ld")
pico_add_extra_outputs(mk61s-picocalc-pico-h)
if(MK61_PICOCALC_M0_EABI)
    add_custom_command(TARGET mk61s-picocalc-pico-h POST_BUILD
        COMMAND "${Python3_EXECUTABLE}" "${MK61_ROOT}/tests/check_picocalc_runtime.py"
            "$<TARGET_FILE:mk61s-picocalc-pico-h>.map"
        VERBATIM)
endif()
