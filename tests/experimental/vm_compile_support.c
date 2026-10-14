// The standalone SDK deliberately omits memchr; this compiler needs it.
#include <stddef.h>
void* memchr(const void* data,int value,size_t length) {
  const unsigned char* p=data;
  for(size_t i=0;i<length;++i) if(p[i]==(unsigned char)value) return (void*)(p+i);
  return NULL;
}
