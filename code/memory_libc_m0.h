/* All eight M0+ candidates are opt-in until the grouped hardware verdict.
 * 0 keeps the existing implementation; 1/2/4 are ordered byte unrolls;
 * 8/16 select checked, naturally aligned word candidates for all eight.
 * This is one shared body source for native, SDK and isolated controls. */
#ifndef MK61_MEMORY_LIBC_M0_H
#define MK61_MEMORY_LIBC_M0_H
#include <stddef.h>
#include <stdint.h>
#ifndef MK61_M0_LIBC_UNROLL
#define MK61_M0_LIBC_UNROLL 0
#endif
#if MK61_M0_LIBC_UNROLL != 0 && MK61_M0_LIBC_UNROLL != 1 && MK61_M0_LIBC_UNROLL != 2 && MK61_M0_LIBC_UNROLL != 4 && MK61_M0_LIBC_UNROLL != 8 && MK61_M0_LIBC_UNROLL != 16
#error "Unsupported M0 libc candidate"
#endif
#if defined(__ARM_ARCH_6M__) && defined(__GNUC__) && !defined(__clang__)
/* Inline helpers must inherit the same options as their public entries. */
#pragma GCC push_options
#pragma GCC optimize ("Os", "no-tree-loop-distribute-patterns")
#define MK61_M0_LIBC_STR_INNER(v) #v
#define MK61_M0_LIBC_STR(v) MK61_M0_LIBC_STR_INNER(v)
#ifndef MK61_M0_STRLEN_IMPL
#if defined(MK61_APP_SHARED_RUNTIME) && 1
#define MK61_M0_STRLEN_IMPL 0
#else
#define MK61_M0_STRLEN_IMPL MK61_M0_LIBC_UNROLL
#endif
#endif
#if MK61_M0_STRLEN_IMPL != 0 && MK61_M0_STRLEN_IMPL != 1 && MK61_M0_STRLEN_IMPL != 2 && MK61_M0_STRLEN_IMPL != 4 && MK61_M0_STRLEN_IMPL != 8 && MK61_M0_STRLEN_IMPL != 16
#error "Unsupported strlen candidate"
#endif
#if MK61_M0_STRLEN_IMPL
#define MK61_ARM_STRLEN 1
#define MK61_M0_LIBC_OPERATION 0
#define MK61_M0_LIBC_CURRENT MK61_M0_STRLEN_IMPL
__attribute__((naked,noipa,aligned(16)))
size_t strlen(const char* text __attribute__((unused))) {
  __asm__(
#if MK61_M0_STRLEN_IMPL >= 8
#include "libc_m0_strlen_word.inc"
#else
#include "libc_m0_byte.inc"
#endif
  );
}
#undef MK61_M0_LIBC_CURRENT
#undef MK61_M0_LIBC_OPERATION
#endif
#ifndef MK61_M0_STRCMP_IMPL
#if defined(MK61_APP_SHARED_RUNTIME) && 0
#define MK61_M0_STRCMP_IMPL 0
#else
#define MK61_M0_STRCMP_IMPL MK61_M0_LIBC_UNROLL
#endif
#endif
#if MK61_M0_STRCMP_IMPL != 0 && MK61_M0_STRCMP_IMPL != 1 && MK61_M0_STRCMP_IMPL != 2 && MK61_M0_STRCMP_IMPL != 4 && MK61_M0_STRCMP_IMPL != 8 && MK61_M0_STRCMP_IMPL != 16
#error "Unsupported strcmp candidate"
#endif
#if MK61_M0_STRCMP_IMPL
#define MK61_ARM_STRCMP 1
#define MK61_M0_LIBC_OPERATION 1
#define MK61_M0_LIBC_CURRENT MK61_M0_STRCMP_IMPL
#if MK61_M0_STRCMP_IMPL >= 8
#include "libc_m0_compare.h"
__attribute__((noipa,aligned(16),optimize("Os")))
int strcmp(const char* left,const char* right) {
  return mk61_m0_compare_words(left,right,0,0, MK61_M0_STRCMP_IMPL == 16 ? 2 : 1);
}
#else
__attribute__((naked,noipa,aligned(16)))
int strcmp(const char* left __attribute__((unused)),const char* right __attribute__((unused))) {
  __asm__(
#include "libc_m0_byte.inc"
  );
}
#endif
#undef MK61_M0_LIBC_CURRENT
#undef MK61_M0_LIBC_OPERATION
#endif
#ifndef MK61_M0_STRNCMP_IMPL
#if defined(MK61_APP_SHARED_RUNTIME) && 1
#define MK61_M0_STRNCMP_IMPL 0
#else
#define MK61_M0_STRNCMP_IMPL MK61_M0_LIBC_UNROLL
#endif
#endif
#if MK61_M0_STRNCMP_IMPL != 0 && MK61_M0_STRNCMP_IMPL != 1 && MK61_M0_STRNCMP_IMPL != 2 && MK61_M0_STRNCMP_IMPL != 4 && MK61_M0_STRNCMP_IMPL != 8 && MK61_M0_STRNCMP_IMPL != 16
#error "Unsupported strncmp candidate"
#endif
#if MK61_M0_STRNCMP_IMPL
#define MK61_ARM_STRNCMP 1
#define MK61_M0_LIBC_OPERATION 2
#define MK61_M0_LIBC_CURRENT MK61_M0_STRNCMP_IMPL
#if MK61_M0_STRNCMP_IMPL >= 8
#include "libc_m0_compare.h"
__attribute__((noipa,aligned(16),optimize("Os")))
int strncmp(const char* left,const char* right,size_t count) {
  return mk61_m0_compare_words(left,right,count,1, MK61_M0_STRNCMP_IMPL == 16 ? 2 : 1);
}
#else
__attribute__((naked,noipa,aligned(16)))
int strncmp(const char* left __attribute__((unused)),const char* right __attribute__((unused)),size_t count __attribute__((unused))) {
  __asm__(
#include "libc_m0_byte.inc"
  );
}
#endif
#undef MK61_M0_LIBC_CURRENT
#undef MK61_M0_LIBC_OPERATION
#endif
#ifndef MK61_M0_MEMCMP_IMPL
#if defined(MK61_APP_SHARED_RUNTIME) && 1
#define MK61_M0_MEMCMP_IMPL 0
#else
#define MK61_M0_MEMCMP_IMPL MK61_M0_LIBC_UNROLL
#endif
#endif
#if MK61_M0_MEMCMP_IMPL != 0 && MK61_M0_MEMCMP_IMPL != 1 && MK61_M0_MEMCMP_IMPL != 2 && MK61_M0_MEMCMP_IMPL != 4 && MK61_M0_MEMCMP_IMPL != 8 && MK61_M0_MEMCMP_IMPL != 16
#error "Unsupported memcmp candidate"
#endif
#if MK61_M0_MEMCMP_IMPL
#define MK61_ARM_MEMCMP 1
#define MK61_M0_LIBC_OPERATION 3
#define MK61_M0_LIBC_CURRENT MK61_M0_MEMCMP_IMPL
__attribute__((naked,noipa,aligned(16)))
int memcmp(const void* left __attribute__((unused)),const void* right __attribute__((unused)),size_t count __attribute__((unused))) {
  __asm__(
#if MK61_M0_MEMCMP_IMPL >= 8
#include "libc_m0_memcmp_word.inc"
#else
#include "libc_m0_byte.inc"
#endif
  );
}
#undef MK61_M0_LIBC_CURRENT
#undef MK61_M0_LIBC_OPERATION
#endif
#ifndef MK61_M0_STRNLEN_IMPL
#if defined(MK61_APP_SHARED_RUNTIME) && 0
#define MK61_M0_STRNLEN_IMPL 0
#else
#define MK61_M0_STRNLEN_IMPL MK61_M0_LIBC_UNROLL
#endif
#endif
#if MK61_M0_STRNLEN_IMPL != 0 && MK61_M0_STRNLEN_IMPL != 1 && MK61_M0_STRNLEN_IMPL != 2 && MK61_M0_STRNLEN_IMPL != 4 && MK61_M0_STRNLEN_IMPL != 8 && MK61_M0_STRNLEN_IMPL != 16
#error "Unsupported strnlen candidate"
#endif
#if MK61_M0_STRNLEN_IMPL
#define MK61_ARM_STRNLEN 1
#define MK61_M0_LIBC_OPERATION 4
#define MK61_M0_LIBC_CURRENT MK61_M0_STRNLEN_IMPL
#if MK61_M0_STRNLEN_IMPL >= 8
#include "libc_m0_copy_words.h"
__attribute__((noipa,aligned(16),optimize("Os","no-tree-loop-distribute-patterns")))
size_t strnlen(const char* text,size_t maximum) {
  return mk61_m0_length_words(text,maximum,1,MK61_M0_STRNLEN_IMPL == 16 ? 2 : 1);
}
#else
__attribute__((naked,noipa,aligned(16)))
size_t strnlen(const char* text __attribute__((unused)),size_t maximum __attribute__((unused))) {
  __asm__(
#include "libc_m0_byte.inc"
  );
}
#endif
#undef MK61_M0_LIBC_CURRENT
#undef MK61_M0_LIBC_OPERATION
#endif
#ifndef MK61_M0_STRCPY_IMPL
#if defined(MK61_APP_SHARED_RUNTIME) && 0
#define MK61_M0_STRCPY_IMPL 0
#else
#define MK61_M0_STRCPY_IMPL MK61_M0_LIBC_UNROLL
#endif
#endif
#if MK61_M0_STRCPY_IMPL != 0 && MK61_M0_STRCPY_IMPL != 1 && MK61_M0_STRCPY_IMPL != 2 && MK61_M0_STRCPY_IMPL != 4 && MK61_M0_STRCPY_IMPL != 8 && MK61_M0_STRCPY_IMPL != 16
#error "Unsupported strcpy candidate"
#endif
#if MK61_M0_STRCPY_IMPL
#define MK61_ARM_STRCPY 1
#define MK61_M0_LIBC_OPERATION 5
#define MK61_M0_LIBC_CURRENT MK61_M0_STRCPY_IMPL
#if MK61_M0_STRCPY_IMPL >= 8
#include "libc_m0_copy_words.h"
__attribute__((noipa,aligned(16),optimize("Os","no-tree-loop-distribute-patterns")))
char* strcpy(char* destination,const char* source) {
  return mk61_m0_copy_words(destination,source,0,0,MK61_M0_STRCPY_IMPL == 16 ? 2 : 1);
}
#else
__attribute__((naked,noipa,aligned(16)))
char* strcpy(char* destination __attribute__((unused)),const char* source __attribute__((unused))) {
  __asm__(
#include "libc_m0_byte.inc"
  );
}
#endif
#undef MK61_M0_LIBC_CURRENT
#undef MK61_M0_LIBC_OPERATION
#endif
#ifndef MK61_M0_STRNCPY_IMPL
#if defined(MK61_APP_SHARED_RUNTIME) && 0
#define MK61_M0_STRNCPY_IMPL 0
#else
#define MK61_M0_STRNCPY_IMPL MK61_M0_LIBC_UNROLL
#endif
#endif
#if MK61_M0_STRNCPY_IMPL != 0 && MK61_M0_STRNCPY_IMPL != 1 && MK61_M0_STRNCPY_IMPL != 2 && MK61_M0_STRNCPY_IMPL != 4 && MK61_M0_STRNCPY_IMPL != 8 && MK61_M0_STRNCPY_IMPL != 16
#error "Unsupported strncpy candidate"
#endif
#if MK61_M0_STRNCPY_IMPL
#define MK61_ARM_STRNCPY 1
#define MK61_M0_LIBC_OPERATION 6
#define MK61_M0_LIBC_CURRENT MK61_M0_STRNCPY_IMPL
#if MK61_M0_STRNCPY_IMPL >= 8
#include "libc_m0_copy_words.h"
__attribute__((noipa,aligned(16),optimize("Os","no-tree-loop-distribute-patterns")))
char* strncpy(char* destination,const char* source,size_t count) {
  return mk61_m0_copy_words(destination,source,count,1,MK61_M0_STRNCPY_IMPL == 16 ? 2 : 1);
}
#else
__attribute__((naked,noipa,aligned(16)))
char* strncpy(char* destination __attribute__((unused)),const char* source __attribute__((unused)),size_t count __attribute__((unused))) {
  __asm__(
#include "libc_m0_byte.inc"
  );
}
#endif
#undef MK61_M0_LIBC_CURRENT
#undef MK61_M0_LIBC_OPERATION
#endif
#ifndef MK61_M0_STRNCAT_IMPL
#if defined(MK61_APP_SHARED_RUNTIME) && 1
#define MK61_M0_STRNCAT_IMPL 0
#else
#define MK61_M0_STRNCAT_IMPL MK61_M0_LIBC_UNROLL
#endif
#endif
#if MK61_M0_STRNCAT_IMPL != 0 && MK61_M0_STRNCAT_IMPL != 1 && MK61_M0_STRNCAT_IMPL != 2 && MK61_M0_STRNCAT_IMPL != 4 && MK61_M0_STRNCAT_IMPL != 8 && MK61_M0_STRNCAT_IMPL != 16
#error "Unsupported strncat candidate"
#endif
#if MK61_M0_STRNCAT_IMPL
#define MK61_ARM_STRNCAT 1
#define MK61_M0_LIBC_OPERATION 7
#define MK61_M0_LIBC_CURRENT MK61_M0_STRNCAT_IMPL
#if MK61_M0_STRNCAT_IMPL >= 8
#include "libc_m0_copy_words.h"
__attribute__((noipa,aligned(16),optimize("Os","no-tree-loop-distribute-patterns")))
char* strncat(char* destination,const char* source,size_t count) {
  return mk61_m0_copy_words(destination,source,count,2,MK61_M0_STRNCAT_IMPL == 16 ? 2 : 1);
}
#else
__attribute__((naked,noipa,aligned(16)))
char* strncat(char* destination __attribute__((unused)),const char* source __attribute__((unused)),size_t count __attribute__((unused))) {
  __asm__(
#include "libc_m0_byte.inc"
  );
}
#endif
#undef MK61_M0_LIBC_CURRENT
#undef MK61_M0_LIBC_OPERATION
#endif
#undef MK61_M0_LIBC_STR
#undef MK61_M0_LIBC_STR_INNER
#pragma GCC pop_options
#endif
#endif
