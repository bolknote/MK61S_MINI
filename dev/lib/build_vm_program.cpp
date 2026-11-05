#include "vm_program_builder.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
int main(int argc,char** argv) {
  using namespace vm_program_builder;
  try {
    if(argc<7 || (argc-3)%4)throw std::runtime_error("usage: build_vm_program OUTPUT ENTRY SYMBOL SOURCE_ID basic|focal SOURCE ...");
    auto number=[](const char* s,uint64_t limit){size_t end=0;std::string text=s;if(text.empty() || text[0]=='-')throw std::runtime_error("invalid number");auto n=std::stoull(text,&end);if(end!=text.size() || n>limit)throw std::runtime_error("invalid number");return n;};
    const auto entry=uint32_t(number(argv[2],UINT32_MAX));std::vector<Member> members;
    for(int i=3;i<argc;i+=4) {
      if(std::filesystem::exists(argv[1]) && std::filesystem::equivalent(argv[1],argv[i+3]))
        throw std::runtime_error("output must not overwrite a source file");
      std::ifstream input(argv[i+3],std::ios::binary);if(!input)throw std::runtime_error(std::string("cannot read ")+argv[i+3]);
      std::string source(std::istreambuf_iterator<char>(input),{}),language=argv[i+2];
      if(language!="basic" && language!="focal")throw std::runtime_error("language must be basic or focal");
      members.push_back({uint32_t(number(argv[i],UINT32_MAX)),uint16_t(number(argv[i+1],65535)),
          compile(language=="basic"?language_vm::Language::BASIC:language_vm::Language::FOCAL,source)});
    }
    auto bytes=package(members,entry);Disk scratch;language_vm::linked::Program checked;
    std::vector<language_vm::linked::Member> directory(members.size());
    language_vm::linked::Input in{};in.bytes=bytes.data();in.size=uint32_t(bytes.size());
    const auto error=language_vm::linked::inspect(in,directory.data(),uint16_t(directory.size()),checked,scratch.io());
    if(error!=language_vm::Error::NONE)throw std::runtime_error(std::string("package verification: ")+language_vm::error_name(error));
    std::ofstream output(argv[1],std::ios::binary);output.write((const char*)bytes.data(),std::streamsize(bytes.size()));
    if(!output)throw std::runtime_error("cannot write output");
    std::cout<<"LVP1 members="<<members.size()<<" bytes="<<bytes.size()<<" metadata="
        <<language_vm::linked::HEADER_BYTES+language_vm::linked::ENTRY_BYTES*members.size()<<" verified\n";
  } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
