/* Opt-in naturally aligned word candidates for all remaining string kernels.
 * A word containing NUL may be read, but only nonzero complete words are
 * stored. Bounded functions never load a word outside their remaining n.
 * Misaligned destinations use byte stores; every word store is aligned. */
#ifndef MK61_LIBC_M0_COPY_WORDS_H
#define MK61_LIBC_M0_COPY_WORDS_H
typedef uint32_t mk61_m0_copy_word __attribute__((__may_alias__));
#define M0_COPY_INLINE static inline __attribute__((always_inline))
M0_COPY_INLINE int mk61_m0_word_has_zero(uint32_t w){return ((w-0x01010101u)&~w&0x80808080u)!=0;}
M0_COPY_INLINE void mk61_m0_store_word(unsigned char* d,uint32_t w){
  if(!((uintptr_t)d&3))*(mk61_m0_copy_word*)d=w;
  else {d[0]=(unsigned char)w;d[1]=(unsigned char)(w>>8);d[2]=(unsigned char)(w>>16);d[3]=(unsigned char)(w>>24);}
}
M0_COPY_INLINE void mk61_m0_zero_tail(unsigned char* d,size_t n,int words){
  while(n&&((uintptr_t)d&3)){*d++=0;--n;}
  if(words==2)while(n>=16){*(mk61_m0_copy_word*)d=0;*(mk61_m0_copy_word*)(d+4)=0;*(mk61_m0_copy_word*)(d+8)=0;*(mk61_m0_copy_word*)(d+12)=0;d+=16;n-=16;}
  while(n>=4){*(mk61_m0_copy_word*)d=0;d+=4;n-=4;}
  while(n--)*d++=0;
}
M0_COPY_INLINE size_t mk61_m0_length_words(const char* text,size_t n,int bounded,int words){
  const unsigned char* s=(const unsigned char*)text;size_t length=0;
  while(((uintptr_t)s&3)&&(!bounded||n)) {if(!*s)return length;++s;++length;if(bounded)--n;}
  while(!bounded||n>=4){
    for(int i=0;i<words;++i){
      if(bounded&&n<4)goto bytes;
      uint32_t w=*(const mk61_m0_copy_word*)s;if(mk61_m0_word_has_zero(w))goto bytes;
      s+=4;length+=4;if(bounded)n-=4;
    }
  }
bytes:
  while(!bounded||n){if(!*s)return length;++s;++length;if(bounded)--n;}
  return length;
}
/* kind0=strcpy, kind1=strncpy (zero-pad), kind2=strncat (terminate only). */
M0_COPY_INLINE char* mk61_m0_copy_words(char* destination,const char* source,size_t n,int kind,int words){
  unsigned char* d=(unsigned char*)destination;const unsigned char* s=(const unsigned char*)source;
  if(kind&&n==0)return destination;
  if(kind==2)d+=mk61_m0_length_words(destination,0,0,words);
  while(((uintptr_t)s&3)&&(!kind||n)){
    unsigned c=*s++;*d++=(unsigned char)c;if(kind)--n;
    if(!c){if(kind==1)mk61_m0_zero_tail(d,n,words);return destination;}
  }
  while(!kind||n>=4){
    for(int i=0;i<words;++i){
      if(kind&&n<4)goto bytes;
      uint32_t w=*(const mk61_m0_copy_word*)s;if(mk61_m0_word_has_zero(w))goto bytes;
      mk61_m0_store_word(d,w);s+=4;d+=4;if(kind)n-=4;
    }
  }
bytes:
  while(!kind||n){
    unsigned c=*s++;*d++=(unsigned char)c;if(kind)--n;
    if(!c){if(kind==1)mk61_m0_zero_tail(d,n,words);return destination;}
  }
  if(kind==2)*d=0;
  return destination;
}
#undef M0_COPY_INLINE
#endif
