/* Frozen SDK byte loop from sdk/portable/memory.c, 2026-10-22.
 * A separate translation unit and -fno-builtin prevent substituting memchr. */
#include <stddef.h>
__attribute__((noipa)) void* baseline(const void* data,int value,size_t size) {
    const unsigned char* bytes=(const unsigned char*)data;
    const unsigned char wanted=(unsigned char)value;
    for(size_t i=0;i<size;++i)
        if(bytes[i]==wanted) return (void*)(bytes+i);
    return NULL;
}
