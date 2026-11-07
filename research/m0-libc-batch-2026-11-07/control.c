/* Same-place ISO C controls. Actual native/newlib and SDK remain separate. */
#include <stddef.h>
#pragma GCC optimize ("no-tree-loop-distribute-patterns")
#define FN __attribute__((noipa,aligned(16)))
FN size_t strlen(const char* s){const char* p=s;while(*p)++p;return (size_t)(p-s);}
FN int strcmp(const char* a,const char* b){for(;;){unsigned x=(unsigned char)*a++,y=(unsigned char)*b++;if(x!=y||!x)return (int)x-(int)y;}}
FN int strncmp(const char* a,const char* b,size_t n){while(n--){unsigned x=(unsigned char)*a++,y=(unsigned char)*b++;if(x!=y||!x)return (int)x-(int)y;}return 0;}
FN int memcmp(const void* left,const void* right,size_t n){const unsigned char* a=left;const unsigned char* b=right;while(n--){unsigned x=*a++,y=*b++;if(x!=y)return (int)x-(int)y;}return 0;}
FN size_t strnlen(const char* s,size_t n){size_t i=0;while(i<n&&s[i])++i;return i;}
FN char* strcpy(char* d,const char* s){char* out=d;do{*out=*s++;}while(*out++);return d;}
FN char* strncpy(char* d,const char* s,size_t n){char* out=d;while(n&&*s){*out++=*s++;--n;}while(n--)*out++=0;return d;}
FN char* strncat(char* d,const char* s,size_t n){char* out=d;while(*out)++out;while(n--&&*s)*out++=*s++;*out=0;return d;}
