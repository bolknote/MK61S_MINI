#ifndef MK61_ECMA_NUMBER_HPP
#define MK61_ECMA_NUMBER_HPP
#include <stddef.h>
namespace ecma_number {
bool format(double value,char* output,size_t capacity);
bool fractional(double value,char* output,size_t capacity);
using ParseFallback=bool (*)(const char* text,unsigned length,double& value);
bool parse(const char* text,double& value,ParseFallback fallback=nullptr);
}
#endif
