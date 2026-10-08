/* Model the runtime's string/memory exports. Linking this with memory.c
 * compiled in shared mode must not define any of these functions twice. */
#include <stddef.h>
#include <string.h>
size_t mk61_test_strlen(const char* text) { return strlen(text); }
char* mk61_test_strchr(const char* text, int c) { return strchr(text,c); }
void* mk61_test_memcpy(void* out,const void* in,size_t n) { return memcpy(out,in,n); }
void* mk61_test_memset(void* out,int value,size_t n) { return memset(out,value,n); }
void* mk61_test_memmove(void* out,const void* in,size_t n) { return memmove(out,in,n); }
int mk61_test_memcmp(const void* a,const void* b,size_t n) { return memcmp(a,b,n); }
