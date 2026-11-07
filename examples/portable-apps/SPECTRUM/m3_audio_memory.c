#include <stddef.h>
/* Only state import/export uses these; synthesis needs no allocation. */
void* memcpy(void* dst,const void* src,size_t n) {
    unsigned char* d=dst;const unsigned char* s=src;
    while(n--)*d++=*s++;return dst;
}
void* memset(void* dst,int value,size_t n) {
    unsigned char* d=dst;while(n--)*d++=(unsigned char)value;return dst;
}
