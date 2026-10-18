#include "language_vm_file_cache.hpp"
#include <string.h>
namespace language_vm::file_cache {
namespace {
constexpr uint32_t CACHE_FLAGS=MK61_PORTABLE_APP_FLAG|MK61_APP_RELOCATABLE_FLAG
#if defined(MK61_CORE_STANDALONE)
    |MK61_APP_ARMV6M_FLAG
#endif
    ;
uint16_t word(const uint8_t* p){return(uint16_t)(p[0]|((uint16_t)p[1]<<8));}
void word(uint8_t* p,uint16_t n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
void dword(uint8_t* p,uint32_t n){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(n>>(8*i));}
void key_bytes(const Key& key,uint16_t size,uint8_t* p) {
  memset(p,0,KEY_BYTES);memcpy(p,"VMC1",4);
  dword(p+4,key.compiler_crc);dword(p+8,key.source_crc);
  word(p+12,key.source_id);word(p+14,key.source_size);
  word(p+16,size);word(p+18,VERSION);p[20]=(uint8_t)key.language;p[21]=1;
}
const uint8_t entry[]={5,0x20,0x70,0x47}; // movs r0,#MK61_APP_RUNTIME_ERROR; bx lr
struct Writer {
  uint8_t* output;unsigned capacity,position=0,control=0;uint8_t mask=0;
  bool byte(uint8_t n){if(position==capacity)return false;output[position++]=n;return true;}
  bool bit(bool n) {
    if(!mask){control=position;if(!byte(0))return false;mask=128;}
    if(n)output[control]|=mask;
    mask>>=1;return true;
  }
  bool gamma(unsigned n,bool invert) {
    unsigned top=1;while((top<<1)<=n)top<<=1;
    while((top>>=1)!=0)if(!bit(false)||!bit(((n&top)!=0)!=invert))return false;
    return bit(true);
  }
};
struct Reader {
  const uint8_t* input;unsigned size,position=0;uint8_t bits=0,mask=0;
  bool bit(bool& n) {
    if(!mask){if(position==size)return false;bits=input[position++];mask=128;}
    n=(bits&mask)!=0;mask>>=1;return true;
  }
  bool gamma(unsigned& n,bool invert) {
    n=1;bool b;
    for(unsigned i=0;i<16;++i){
      if(!bit(b))return false;
      if(b)return true;
      if(!bit(b))return false;
      n=(n<<1)|(unsigned)(b!=invert);
    }
    return false;
  }
};
}
bool pack(const Key& key,const uint8_t* image,uint16_t size,
          uint8_t* output,uint16_t capacity,uint16_t& written) {
  written=0;
  if(!image || !output || size<HEADER_SIZE || size>MAX_MODULE ||
     capacity<=loadable_module::HEADER_SIZE || key.source_id==0xFFFF ||
     (key.language!=Language::BASIC && key.language!=Language::FOCAL))return false;
  uint8_t prefix[KEY_BYTES];key_bytes(key,size,prefix);
  const unsigned entry_offset=(KEY_BYTES+size+3)&~3U,logical=entry_offset+sizeof(entry);
  Writer w={output+loadable_module::HEADER_SIZE,(unsigned)(capacity-loadable_module::HEADER_SIZE)};
  if(!w.gamma(logical,false))return false;
  uint32_t crc=loadable_module::crc32_begin();
  for(unsigned i=0;i<logical;++i){
    const uint8_t n=i<KEY_BYTES?prefix[i]:i<KEY_BYTES+size?image[i-KEY_BYTES]:
        i<entry_offset?0:entry[i-entry_offset];
    if(!w.byte(n))return false;
    crc=loadable_module::crc32_extend(crc,&n,1);
  }
  if(!w.bit(true)||!w.gamma(256,true))return false;
  loadable_module::Header h={};
  h.kind=loadable_module::Kind::APPLICATION;h.compression=loadable_module::Compression::ZX0;
  h.flags=CACHE_FLAGS;h.load_address=MK61_PORTABLE_APP_ADDRESS;
  h.stored_size=h.code_stored_size=w.position;h.image_size=h.memory_size=logical;
  h.entry_offset=entry_offset;h.stored_crc32=loadable_module::crc32(output+64,w.position);
  h.image_crc32=loadable_module::crc32_finish(crc);
  written=(uint16_t)(64+w.position);
  if(!loadable_module::encode_header(h,written,output)){written=0;return false;}
  return true;
}
namespace {
bool header(const uint8_t* file,uint16_t size,loadable_module::Header& h) {
  return file && size>=PROBE_BYTES &&
      loadable_module::decode_header(file,size,loadable_module::Kind::APPLICATION,h)==
        loadable_module::HeaderStatus::OK && !h.relocation_count &&
      h.compression==loadable_module::Compression::ZX0 && h.memory_size==h.image_size &&
      h.flags==CACHE_FLAGS &&
      h.stored_size==size-64U && h.code_stored_size==h.stored_size;
}
bool literal(Reader& r,const loadable_module::Header& h,
             const uint8_t*& data,uint16_t& image_size) {
  unsigned logical;
  if(!r.gamma(logical,false) || logical!=h.image_size || logical<KEY_BYTES+HEADER_SIZE+4 ||
     logical>h.stored_size-r.position || h.entry_offset+sizeof(entry)!=logical ||
     r.size-r.position<KEY_BYTES)return false;
  data=r.input+r.position;image_size=word(data+16);
  return image_size>=HEADER_SIZE && image_size<=MAX_MODULE &&
      h.entry_offset==((KEY_BYTES+image_size+3)&~3U);
}
bool matches(const Key& key,const uint8_t* plain,uint16_t image_size) {
  uint8_t expected[KEY_BYTES];key_bytes(key,image_size,expected);
  return !memcmp(plain,expected,sizeof(expected));
}
bool container(const uint8_t* file,uint16_t size,
               const uint8_t*& plain,uint16_t& image_size) {
  plain=nullptr;image_size=0;
  loadable_module::Header h;
  if(!header(file,size,h) ||
     loadable_module::crc32(file+64,h.stored_size)!=h.stored_crc32)return false;
  Reader r={file+64,h.stored_size};const uint8_t* data;
  if(!literal(r,h,data,image_size) ||
     memcmp(data+h.entry_offset,entry,sizeof(entry)) ||
     loadable_module::crc32(data,h.image_size)!=h.image_crc32)return false;
  r.position+=h.image_size;bool end;unsigned marker;
  if(!r.bit(end) || !end || !r.gamma(marker,true) || marker!=256 || r.position!=r.size)return false;
  plain=data;return true;
}
}
bool probe_candidate(const Key& key,const uint8_t* prefix,uint16_t prefix_size,
                     uint16_t size,uint32_t& source_crc,uint16_t& image_size) {
  source_crc=0;image_size=0;loadable_module::Header h;
  if(prefix_size<PROBE_BYTES || !header(prefix,size,h))return false;
  Reader r={prefix+64,PROBE_BYTES-64};const uint8_t* plain;
  if(!literal(r,h,plain,image_size)) {image_size=0;return false;}
  Key candidate=key;
  memcpy(&candidate.source_crc,plain+8,4);
  if(!matches(candidate,plain,image_size)) {
    image_size=0;return false;
  }
  source_crc=candidate.source_crc;
  return true;
}
bool probe(const Key& key,const uint8_t* prefix,uint16_t prefix_size,
           uint16_t size,uint16_t& image_size) {
  uint32_t source_crc=0;
  if(!probe_candidate(key,prefix,prefix_size,size,source_crc,image_size) ||
     source_crc!=key.source_crc) {image_size=0;return false;}
  return true;
}
bool view(const Key& key,const uint8_t* file,uint16_t size,
          const uint8_t*& image,uint16_t& image_size) {
  image=nullptr;
  const uint8_t* plain=nullptr;
  if(!container(file,size,plain,image_size))return false;
  if(!matches(key,plain,image_size)){image_size=0;return false;}
  image=plain+KEY_BYTES;return true;
}
bool owned(uint16_t source_id,Language language,const uint8_t* file,uint16_t size) {
  const uint8_t* plain=nullptr;uint16_t image_size=0;
  if(!container(file,size,plain,image_size))return false;
  Key key={};
  memcpy(&key.compiler_crc,plain+4,4);memcpy(&key.source_crc,plain+8,4);
  key.source_id=source_id;key.source_size=word(plain+14);key.language=language;
  // A verified cache from an earlier wire version is ours to rebuild, never
  // ours to execute. Keep probe/view strict; reject unknown future formats.
  const uint16_t version=word(plain+18);
  if(!version || version>VERSION)return false;
  uint8_t expected[KEY_BYTES];key_bytes(key,image_size,expected);
  word(expected+18,version);
  return !memcmp(plain,expected,sizeof(expected));
}
}
