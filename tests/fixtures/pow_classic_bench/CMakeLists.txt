cmake_minimum_required(VERSION 3.13)
set(PICO_NO_PICOTOOL 1)
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(powbench C CXX ASM)
set(CMAKE_CXX_STANDARD 17)
pico_sdk_init()
get_filename_component(root "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
add_library(reference OBJECT ${root}/code/compact_math.cpp)
target_compile_definitions(reference PRIVATE compact_math=classic_reference
    MK61_USE_COMPACT_LIBM=1 MK61_MATH_BACKEND=0 MK61_USE_M0_EABI=0)
target_compile_options(reference PRIVATE -O3 -ffp-contract=off -ffunction-sections -fdata-sections)
add_executable(powbench bench.cpp $<TARGET_OBJECTS:reference>
    ${root}/code/compact_math.cpp ${root}/code/native_eabi_m0.cpp
    ${root}/code/native_eabi_m0_cr.cpp ${root}/code/native_eabi_m0.S ${root}/code/native_eabi_m0_rp2040.S)
target_include_directories(powbench PRIVATE ${root}/code)
target_compile_definitions(powbench PRIVATE POW_BENCH_PICO=1 MK61_USE_COMPACT_LIBM=1
    MK61_MATH_BACKEND=0 MK61_USE_M0_EABI=1 MK61_M0_RP2040_EABI=1)
set_source_files_properties(${root}/code/native_eabi_m0.cpp ${root}/code/native_eabi_m0_cr.cpp
    PROPERTIES COMPILE_OPTIONS "-Os;-fno-lto;-ffp-contract=off")
target_link_libraries(powbench pico_stdlib hardware_watchdog hardware_clocks)
target_link_options(powbench PRIVATE "-Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/powbench.map,--cref")
pico_set_float_implementation(powbench compiler)
pico_set_double_implementation(powbench compiler)
pico_set_binary_type(powbench no_flash)
pico_enable_stdio_usb(powbench 1)
pico_enable_stdio_uart(powbench 0)
