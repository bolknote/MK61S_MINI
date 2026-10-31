// Link this with the exact accepted A748 loader and decoder, on the host.
#include "loadable_module_format.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include <cstring>
struct Input { const std::vector<u8>* bytes; };
static bool read(void* raw,u32 offset,u8* out,usize n) {
  const auto& data=*static_cast<Input*>(raw)->bytes;
  if(offset>data.size()-64 || n>data.size()-64-offset)return false;
  std::memcpy(out,data.data()+64+offset,n);return true;
}
int main(int argc,char** argv) {
  if(argc!=5)return 1;
  std::cout<<"[";
  for(int i=1;i<argc;++i) {
    std::ifstream file(argv[i],std::ios::binary);
    std::vector<u8> bytes((std::istreambuf_iterator<char>(file)),{});
    loadable_module::Header header{};
    if(bytes.size()<64 || loadable_module::decode_header(bytes.data(),loadable_module::MAX_CONTAINER_SIZE,header)!=loadable_module::HeaderStatus::OK || bytes.size()!=64+header.stored_size)return 2;
    Input input{&bytes};loadable_module::Reader reader{&input,read};
    for(u32 address:{0x20030800U,0x20031000U}) {
      std::vector<u8> decoded(header.memory_size,0);
      if(!loadable_module::decode_image(header,reader,decoded.data(),address))return 3;
      bytes.back()^=128;
      if(loadable_module::decode_image(header,reader,decoded.data(),address))return 4;
      bytes.back()^=128;
    }
    if(i>1)std::cout<<",";
    std::cout<<"{\"memory_bytes\":"<<header.memory_size<<",\"image_bytes\":"<<header.image_size
      <<",\"relocations\":"<<header.relocation_count<<",\"addresses_checked\":2,\"damaged_payload_rejected\":true}";
  }
  std::cout<<"]\n";
}
