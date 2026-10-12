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
  assert(!file_cache::pack(key,image.data(),result.size,file.data(),64,written));
  std::puts("VM file cache: C6 compatibility, byte-exact image, key changes, every-byte corruption/truncation PASS");
}
