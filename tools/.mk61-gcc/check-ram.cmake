if(NOT DEFINED MK61_SIZE_TOOL OR NOT EXISTS "${MK61_SIZE_TOOL}")
  message(FATAL_ERROR "MK61_SIZE_TOOL is missing: ${MK61_SIZE_TOOL}")
endif()
if(NOT DEFINED MK61_ELF OR NOT EXISTS "${MK61_ELF}")
  message(FATAL_ERROR "MK61_ELF is missing: ${MK61_ELF}")
endif()
if(NOT DEFINED MK61_RAM_CAPACITY OR
   NOT MK61_RAM_CAPACITY MATCHES "^[0-9]+$")
  message(FATAL_ERROR "MK61_RAM_CAPACITY must be an integer")
endif()
if(NOT DEFINED MK61_GLOBAL_RAM_LIMIT OR
   NOT MK61_GLOBAL_RAM_LIMIT MATCHES "^[0-9]+$")
  message(FATAL_ERROR "MK61_GLOBAL_RAM_LIMIT must be an integer")
endif()

execute_process(
  COMMAND "${MK61_SIZE_TOOL}" -A "${MK61_ELF}"
  RESULT_VARIABLE _mk61_size_result
  OUTPUT_VARIABLE _mk61_size_output
  ERROR_VARIABLE _mk61_size_error)
if(NOT _mk61_size_result EQUAL 0)
  message(FATAL_ERROR
    "arm-none-eabi-size failed (${_mk61_size_result}):\n${_mk61_size_error}")
endif()

set(_mk61_data "")
set(_mk61_bss "")
set(_mk61_noinit "")
set(_mk61_reserved "")
string(REPLACE "\r\n" "\n" _mk61_size_output "${_mk61_size_output}")
string(REPLACE "\n" ";" _mk61_size_lines "${_mk61_size_output}")
foreach(_mk61_line IN LISTS _mk61_size_lines)
  if(_mk61_line MATCHES "^\\.data[ \t]+([0-9]+)")
    set(_mk61_data "${CMAKE_MATCH_1}")
  elseif(_mk61_line MATCHES "^\\.bss[ \t]+([0-9]+)")
    set(_mk61_bss "${CMAKE_MATCH_1}")
  elseif(_mk61_line MATCHES "^\\.noinit[ \t]+([0-9]+)")
    set(_mk61_noinit "${CMAKE_MATCH_1}")
  elseif(_mk61_line MATCHES "^\\._user_heap_stack[ \t]+([0-9]+)")
    set(_mk61_reserved "${CMAKE_MATCH_1}")
  endif()
endforeach()

foreach(_mk61_required IN ITEMS data bss noinit reserved)
  if("${_mk61_${_mk61_required}}" STREQUAL "")
    message(FATAL_ERROR
      "section .${_mk61_required} is missing from size output:\n${_mk61_size_output}")
  endif()
endforeach()

math(EXPR _mk61_globals
  "${_mk61_data} + ${_mk61_bss} + ${_mk61_noinit}")
math(EXPR _mk61_linked
  "${_mk61_globals} + ${_mk61_reserved}")
math(EXPR _mk61_free_after_reserve
  "${MK61_RAM_CAPACITY} - ${_mk61_linked}")

message(STATUS
  "MK61 RAM: globals ${_mk61_globals}/${MK61_RAM_CAPACITY}, "
  "linked reserve ${_mk61_reserved}, free after reserve ${_mk61_free_after_reserve}")

if(_mk61_globals GREATER MK61_GLOBAL_RAM_LIMIT)
  math(EXPR _mk61_over "${_mk61_globals} - ${MK61_GLOBAL_RAM_LIMIT}")
  message(FATAL_ERROR
    "F401 static RAM budget exceeded by ${_mk61_over} bytes: "
    "${_mk61_globals} > ${MK61_GLOBAL_RAM_LIMIT}. "
    "Move immutable data to Flash or reuse an existing shared arena.")
endif()
