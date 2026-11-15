#include "heap_trace.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>

thread_local unsigned test_core=0;
static void write(void* raw,const char* value,unsigned n) {
    ((std::string*)raw)->append(value,n);
}
int main() {
    using namespace picocalc::heap_trace;
    std::string text;
    start();
    record(ALLOC,(void*)0x20001000,100,(void*)0x10002001);
    mark(IMAGE_RESERVED,300);
    realloc_result((void*)0x20001000,(void*)0x20002000,200,(void*)0x10003001);
    assert(!report(write,&text) && text.empty());
    stop();assert(report(write,&text));
    assert(text.find("count=4 dropped=0 capacity=128")!=std::string::npos);
    assert(text.find("kind=1 core=0 ptr=20001000 value=100 pc=10002001")!=std::string::npos);
    assert(text.find("kind=6 core=0 ptr=00000002 value=300")!=std::string::npos);
    assert(text.find("kind=4 core=0 ptr=20001000 value=200 pc=10003001")!=std::string::npos);
    assert(text.find("kind=5 core=0 ptr=20002000 value=200 pc=10003001")!=std::string::npos);
    text.clear();start();
    auto produce=[](unsigned core) {
        test_core=core;
        for(unsigned i=0;i<100;++i) record(FREE,(void*)(uintptr_t)(0x20000000U+core*1024+i),0,nullptr);
    };
    std::thread one(produce,0),two(produce,1);one.join();two.join();
    stop();assert(report(write,&text));
    assert(text.find("count=128 dropped=72 capacity=128")!=std::string::npos);
    unsigned lines=0;for(char ch:text) if(ch=='\n') ++lines;
    assert(lines==129);
    text.clear();start();stop();assert(report(write,&text));
    assert(text.find("count=0 dropped=0 capacity=128")!=std::string::npos);
    std::puts("Bounded heap trace: markers, realloc pairs, two cores, overflow and reset PASS");
}
