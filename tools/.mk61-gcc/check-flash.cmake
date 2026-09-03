if(NOT DEFINED MK61_BIN OR NOT EXISTS "${MK61_BIN}" OR
   IS_DIRECTORY "${MK61_BIN}")
  message(FATAL_ERROR "MK61_BIN is missing or not a file: ${MK61_BIN}")
endif()
if(NOT DEFINED MK61_FLASH_CAPACITY OR
   NOT MK61_FLASH_CAPACITY MATCHES "^[1-9][0-9]*$")
  message(FATAL_ERROR "MK61_FLASH_CAPACITY must be a positive integer")
endif()
if(NOT DEFINED MK61_FLASH_MIN_HEADROOM OR
   NOT MK61_FLASH_MIN_HEADROOM MATCHES "^[0-9]+$" OR
   MK61_FLASH_MIN_HEADROOM GREATER MK61_FLASH_CAPACITY)
  message(FATAL_ERROR "MK61_FLASH_MIN_HEADROOM must be within Flash capacity")
endif()

# The objcopy image includes all loadable bytes, including .data initializers,
# alignment gaps and the CRC footer. Counting .text alone underestimates Flash.
file(SIZE "${MK61_BIN}" _mk61_flash_used)
if(_mk61_flash_used EQUAL 0)
  message(FATAL_ERROR "MK61_BIN is empty: ${MK61_BIN}")
endif()
math(EXPR _mk61_flash_free "${MK61_FLASH_CAPACITY} - ${_mk61_flash_used}")
message(STATUS
  "MK61 Flash: image ${_mk61_flash_used}/${MK61_FLASH_CAPACITY}, "
  "free ${_mk61_flash_free}, minimum headroom ${MK61_FLASH_MIN_HEADROOM}")
if(_mk61_flash_free LESS MK61_FLASH_MIN_HEADROOM)
  message(FATAL_ERROR
    "F401 Flash headroom below budget: ${_mk61_flash_free} bytes available, "
    "${MK61_FLASH_MIN_HEADROOM} required. Reduce resident code size; "
    "do not increase the physical Flash limit.")
endif()
