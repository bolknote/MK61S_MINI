/* Function-only math image initialization; not a reset handler or firmware. */
#include <stddef.h>
#include <stdint.h>
extern unsigned char __scratch_y_start__[],__scratch_y_end__[],__scratch_y_source__[];
extern unsigned char __data_start__[],__data_end__[],__data_source__[];
extern unsigned char __bss_start__[],__bss_end__[];
extern void* __wrap_memcpy(void*,const void*,size_t);
extern void* __wrap_memset(void*,int,size_t);
extern int __aeabi_mem_init(void);
__attribute__((noinline,used)) unsigned unified_math_init(void) {
  const size_t hot=(uintptr_t)__scratch_y_end__-(uintptr_t)__scratch_y_start__;
  const size_t data=(uintptr_t)__data_end__-(uintptr_t)__data_start__;
  const size_t bss=(uintptr_t)__bss_end__-(uintptr_t)__bss_start__;
  __wrap_memcpy(__scratch_y_start__,__scratch_y_source__,hot);
  __wrap_memcpy(__data_start__,__data_source__,data);
  if(!__aeabi_mem_init()) return 0;
  __wrap_memset(__bss_start__,0,bss);
  return 1;
}
