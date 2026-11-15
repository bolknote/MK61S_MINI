#include "heap_trace.hpp"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <string>

thread_local unsigned test_core=0;
struct _reent;
extern "C" {
void* __wrap_malloc(size_t);void* __wrap_calloc(size_t,size_t);
void* __wrap_realloc(void*,size_t);void __wrap_free(void*);
void* __wrap__malloc_r(_reent*,size_t);void* __wrap__calloc_r(_reent*,size_t,size_t);
void* __wrap__realloc_r(_reent*,void*,size_t);void __wrap__free_r(_reent*,void*);
void* __real_malloc(size_t n) { return __wrap__malloc_r(nullptr,n); }
void* __real_calloc(size_t n,size_t size) { return __wrap__calloc_r(nullptr,n,size); }
void* __real_realloc(void* p,size_t n) { return __wrap__realloc_r(nullptr,p,n); }
void __real_free(void* p) { __wrap__free_r(nullptr,p); }
void* __real__malloc_r(_reent*,size_t n) { return std::malloc(n); }
void* __real__calloc_r(_reent*,size_t n,size_t s) { return std::calloc(n,s); }
void* __real__realloc_r(_reent*,void* p,size_t n) { return std::realloc(p,n); }
void __real__free_r(_reent*,void* p) { std::free(p); }
}
static void write(void* raw,const char* value,unsigned n) { ((std::string*)raw)->append(value,n); }
int main() {
    using namespace picocalc::heap_trace;
    start();
    void* first=__wrap_malloc(10);assert(first);
    void* second=__wrap_calloc(8,4);assert(second);
    first=__wrap_realloc(first,40);assert(first);
    __wrap_free(first);__wrap_free(second);
    test_core=1;void* direct=__wrap__malloc_r(nullptr,5);assert(direct);
    __wrap__free_r(nullptr,direct);
    stop();std::string result;assert(report(write,&result));
    assert(result.find("count=8 dropped=0 capacity=128")!=std::string::npos);
    assert(result.find("kind=1 core=0")!=std::string::npos);
    assert(result.find("kind=2 core=0")!=std::string::npos);
    assert(result.find("kind=4 core=0")!=std::string::npos);
    assert(result.find("kind=5 core=0")!=std::string::npos);
    assert(result.find("kind=1 core=1")!=std::string::npos);
    assert(result.find("kind=3 core=1")!=std::string::npos);
    std::puts("Heap trace wrappers: allocator mutex, public/newlib nesting and both cores PASS");
}
