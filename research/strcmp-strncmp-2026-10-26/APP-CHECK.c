/* Shared and standalone smoke workload. The volatile pointers retain actual
 * public strcmp/strncmp calls through LTO; no timing claim is made here. */
#include "mk61_app.h"
#include <string.h>
static int (*volatile compare)(const char*,const char*)=strcmp;
static int (*volatile bounded)(const char*,const char*,size_t)=strncmp;
static unsigned char left[528] __attribute__((aligned(16)));
static unsigned char right[528] __attribute__((aligned(16)));
volatile uint32_t checks;
static int sign(int x) {return (x>0)-(x<0);}
static int oracle(const unsigned char* a,const unsigned char* b,size_t n,int limit) {
  for(size_t i=0;!limit || i<n;++i) {
    const unsigned x=a[i],y=b[i];
    if(x!=y || !x)return (x>y)-(x<y);
  }
  return 0;
}
int main(void) {
  static const unsigned lengths[]={0,1,2,3,4,7,8,15,16,31,32,63,64,127,128,255,511};
  checks=0;
  for(unsigned l=0;l<sizeof(lengths)/sizeof(lengths[0]);++l)
    for(unsigned aa=0;aa<4;++aa)for(unsigned ba=0;ba<4;++ba)
      for(unsigned mode=0;mode<5;++mode) {
        const unsigned n=lengths[l];unsigned char *a=left+aa,*b=right+ba;
        for(unsigned i=0;i<sizeof(left);++i){left[i]=0xa5;right[i]=0xa5;}
        for(unsigned i=0;i<n;++i)a[i]=b[i]=(unsigned char)(1+i%255);
        a[n]=b[n]=0;
        if(n && mode){unsigned at=mode==1?0:mode==2?n/2:n-1;b[at]=mode==4?0:(unsigned char)(a[at]==255?1:255);}
        const int expected=oracle(a,b,0,0);
        if(sign(compare((const char*)a,(const char*)b))!=expected)return 10;
        ++checks;
        const size_t limits[]={0,1,n?n-1:0,n,n+1,(size_t)-1};
        for(unsigned k=0;k<6;++k) {
          const size_t limit=limits[k];
          if(sign(bounded((const char*)a,(const char*)b,limit))!=oracle(a,b,limit,1))return 11;
          ++checks;
        }
        for(unsigned i=0;i<n;++i) {
          if(a[i]!=(unsigned char)(1+i%255))return 12;
          unsigned char expected_byte=a[i];
          if(mode && i==(mode==1?0:mode==2?n/2:n-1))expected_byte=mode==4?0:(unsigned char)(a[i]==255?1:255);
          if(b[i]!=expected_byte)return 13;
        }
        if(a[n] || b[n])return 14;
        for(unsigned i=0;i<sizeof(left);++i) {
          if((i<aa || i>aa+n) && left[i]!=0xa5)return 15;
          if((i<ba || i>ba+n) && right[i]!=0xa5)return 16;
        }
      }
  return 0;
}
