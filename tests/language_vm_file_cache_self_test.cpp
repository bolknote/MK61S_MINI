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
  uint32_t claimed_crc=0;
  auto unknown_crc=key;unknown_crc.source_crc^=1;
  assert(file_cache::probe_candidate(unknown_crc,prefix.data(),(uint16_t)prefix.size(),written,claimed_crc,reserved));
  assert(claimed_crc==key.source_crc && reserved==bytes);
  assert(!file_cache::probe(unknown_crc,prefix.data(),(uint16_t)prefix.size(),written,reserved));
  assert(file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),written,reserved) && reserved==bytes);
  assert(!file_cache::probe(key,nullptr,(uint16_t)prefix.size(),written,reserved));
  assert(!file_cache::probe_candidate(key,nullptr,(uint16_t)prefix.size(),written,claimed_crc,reserved) && !claimed_crc && !reserved);
  for(unsigned n=0;n<prefix.size();++n) {
    assert(!file_cache::probe(key,prefix.data(),(uint16_t)n,written,reserved) && !reserved);
    assert(!file_cache::probe_candidate(key,prefix.data(),(uint16_t)n,written,claimed_crc,reserved) && !claimed_crc && !reserved);
  }
  for(unsigned n=0;n<written;++n)
    assert(!file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),(uint16_t)n,reserved));
  assert(!file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),(uint16_t)(written+1),reserved));
  const unsigned key_offset=(unsigned)(cached-file.data())-file_cache::KEY_BYTES;
  for(unsigned at=0;at<64;++at) {
    prefix[at]^=1;
    assert(!file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),written,reserved));
    assert(!file_cache::probe_candidate(key,prefix.data(),(uint16_t)prefix.size(),written,claimed_crc,reserved) && !claimed_crc && !reserved);
    prefix[at]^=1;
  }
  for(unsigned at=key_offset;at<key_offset+file_cache::KEY_BYTES;++at) {
    prefix[at]^=1;
    assert(!file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),written,reserved) && !reserved);
    const bool only_source_crc=at>=key_offset+8 && at<key_offset+12;
    assert(file_cache::probe_candidate(key,prefix.data(),(uint16_t)prefix.size(),written,claimed_crc,reserved)==only_source_crc);
    if(only_source_crc)assert(claimed_crc!=key.source_crc && reserved==bytes);
    else assert(!claimed_crc && !reserved);
    prefix[at]^=1;
  }
  // A prefix is deliberately not an executable certificate: corrupt payload
  // can grant only a bounded reservation and must fail the full CRC check.
  file.back()^=1;
  assert(file_cache::probe(key,prefix.data(),(uint16_t)prefix.size(),written,reserved));
  assert(file_cache::probe_candidate(key,prefix.data(),(uint16_t)prefix.size(),written,claimed_crc,reserved));
  assert(!file_cache::view(key,file.data(),written,cached,bytes));file.back()^=1;
  assert(file_cache::view(key,file.data(),written,cached,bytes));
  assert(file_cache::owned(key.source_id,key.language,file.data(),written));
  assert(!file_cache::owned((uint16_t)(key.source_id+1),key.language,file.data(),written));
  assert(!file_cache::owned(key.source_id,Language::FOCAL,file.data(),written));
  assert(bytes==result.size && !memcmp(cached,image.data(),bytes));
  loadable_module::Header h;
  assert(loadable_module::decode_header(file.data(),written,h)==loadable_module::HeaderStatus::OK);
  // Wire upgrades must replace a recognized old cache instead of treating its
  // filename as a foreign collision and recompiling forever. It is never a hit.
  for(uint16_t version:{uint16_t(0),uint16_t(VERSION-1),uint16_t(VERSION+1)}) {
    auto old=file;auto old_header=h;
    old[key_offset+18]=(uint8_t)version;old[key_offset+19]=(uint8_t)(version>>8);
    old[key_offset+file_cache::KEY_BYTES+4]=(uint8_t)version;
    old_header.stored_crc32=loadable_module::crc32(old.data()+64,old.size()-64);
    old_header.image_crc32=loadable_module::crc32(old.data()+key_offset,old_header.image_size);
    assert(loadable_module::encode_header(old_header,(uint16_t)old.size(),old.data()));
    const uint8_t* span=nullptr;uint16_t length=0;
    assert(!file_cache::view(key,old.data(),(uint16_t)old.size(),span,length));
    assert(!file_cache::probe(key,old.data(),file_cache::PROBE_BYTES,(uint16_t)old.size(),length));
    assert(!file_cache::probe_candidate(key,old.data(),file_cache::PROBE_BYTES,(uint16_t)old.size(),claimed_crc,length) && !claimed_crc && !length);
    assert(file_cache::owned(key.source_id,key.language,old.data(),(uint16_t)old.size())==(version==VERSION-1));
  }
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
