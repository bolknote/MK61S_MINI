#include "arm_test_support.h"
#include <stdint.h>
#include <stddef.h>
__attribute__((noreturn,noinline)) void test_arm_fail(unsigned line,const char* expression) {
    (void)line;(void)expression;for(;;) __asm volatile("nop");
}
void* memcpy(void* destination,const void* source,size_t n) {
    volatile uint8_t* out=destination;const uint8_t* in=source;
    while(n--) *out++=*in++;
    return destination;
}
void* memset(void* destination,int value,size_t n) {
    volatile uint8_t* out=destination;while(n--) *out++=(uint8_t)value;
    return destination;
}
int strcmp(const char* a,const char* b) {
    while(*a && *a==*b) {++a;++b;}
    return (unsigned char)*a-(unsigned char)*b;
}
int printf(const char* format,...) {(void)format;return 0;}
