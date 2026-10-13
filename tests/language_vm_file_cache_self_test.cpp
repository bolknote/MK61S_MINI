#include "language_vm_file_cache.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
using namespace language_vm;
static bool read(void* raw,uint32_t at,uint8_t* out,usize n) {
  const auto& file=*(std::vector<uint8_t>*)raw;
  if(at>file.size()-64 || n>file.size()-64-at)return false;
  memcpy(out,file.data()+64+at,n);return true;
}
int main() {
  const char* source="10 FOR I=0 TO 100;A=128+I;@(I)=A;NEXT I\n20 PRINT A\n";
  std::vector<uint8_t> image(MAX_MODULE),file(MAX_MODULE+128),decoded(MAX_MODULE+128);
  ResourceSource resources={42,1};resources.mode=ResourceMode::EMBEDDED;
  const auto result=compile(Language::BASIC,source,(uint16_t)strlen(source),
      image.data(),(uint16_t)image.size(),true,&resources);
  assert(result.error==Error::NONE);
  const file_cache::Key key={1234,checksum((const uint8_t*)source,(uint16_t)strlen(source)),42,
      (uint16_t)strlen(source),Language::BASIC};
  uint16_t written=0;
  assert(file_cache::pack(key,image.data(),result.size,file.data(),(uint16_t)file.size(),written));
  file.resize(written);
  const uint8_t* cached=nullptr;uint16_t bytes=0;
  assert(file_cache::view(key,file.data(),written,cached,bytes));
  // Probe owns only this prefix, never the tail that will be read after reserve.
  std::vector<uint8_t> prefix(file.begin(),file.begin()+file_cache::PROBE_BYTES);
  uint16_t reserved=0;
  assert(file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),written,reserved) && reserved==bytes);
  assert(!file_cache::probe(key,nullptr,(uint16_t)prefix.size(),written,reserved));
  for(unsigned n=0;n<prefix.size();++n)
    assert(!file_cache::probe(key,prefix.data(),(uint16_t)n,written,reserved) && !reserved);
  for(unsigned n=0;n<written;++n)
    assert(!file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),(uint16_t)n,reserved));
  assert(!file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),(uint16_t)(written+1),reserved));
  const unsigned key_offset=(unsigned)(cached-file.data())-file_cache::KEY_BYTES;
  for(unsigned at=0;at<64;++at) {
    prefix[at]^=1;
    assert(!file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),written,reserved));
    prefix[at]^=1;
  }
  for(unsigned at=key_offset;at<key_offset+file_cache::KEY_BYTES;++at) {
    prefix[at]^=1;
    assert(!file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),written,reserved) && !reserved);
    prefix[at]^=1;
  }
  // A prefix is deliberately not an executable certificate: corrupt payload
  // can grant only a bounded reservation and must fail the full CRC check.
  file.back()^=1;
  assert(file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),written,reserved));
  assert(!file_cache::view(key,file.data(),written,cached,bytes));file.back()^=1;
  assert(file_cache::view(key,file.data(),written,cached,bytes));
  assert(file_cache::owned(key.source_id,key.language,file.data(),written));
  assert(!file_cache::owned((uint16_t)(key.source_id+1),key.language,file.data(),written));
  assert(!file_cache::owned(key.source_id,Language::FOCAL,file.data(),written));
  assert(bytes==result.size && !memcmp(cached,image.data(),bytes));
  loadable_module::Header h;
  assert(loadable_module::decode_header(file.data(),written,h)==loadable_module::HeaderStatus::OK);
  const loadable_module::Reader reader={&file,read};
  assert(loadable_module::decode_image(h,reader,decoded.data(),0x20004000));
  assert(!memcmp(decoded.data()+file_cache::KEY_BYTES,image.data(),bytes));
  for(unsigned at=0;at<file.size();++at) {
    file[at]^=1;assert(!file_cache::view(key,file.data(),written,cached,bytes));file[at]^=1;
  }
  for(unsigned n=0;n<written;++n)assert(!file_cache::view(key,file.data(),(uint16_t)n,cached,bytes));
  auto stale=key;stale.compiler_crc++;assert(!file_cache::view(stale,file.data(),written,cached,bytes));
  stale=key;stale.source_crc++;assert(!file_cache::view(stale,file.data(),written,cached,bytes));
  stale=key;stale.source_id++;assert(!file_cache::view(stale,file.data(),written,cached,bytes));
  stale=key;stale.source_size++;assert(!file_cache::view(stale,file.data(),written,cached,bytes));
  stale=key;stale.language=Language::FOCAL;assert(!file_cache::view(stale,file.data(),written,cached,bytes));
  // Both ends of the bounded range fit the same 92-byte probe, including the
  // largest four-byte initial gamma and alignment padding.
  for(const uint16_t size:{HEADER_SIZE,MAX_MODULE}) {
    std::vector<uint8_t> bounded(size,0),container(MAX_MODULE+128);
    uint16_t length=0;
    assert(file_cache::pack(key,bounded.data(),size,container.data(),(uint16_t)container.size(),length));
    prefix.assign(container.begin(),container.begin()+file_cache::PROBE_BYTES);
    assert(file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),length,reserved) && reserved==size);
  }
  assert(!file_cache::pack(key,image.data(),result.size,file.data(),64,written));
  std::puts("VM file cache: bounded prefix probe, C6 compatibility, byte-exact image, key changes, every-byte corruption/truncation PASS");
}
