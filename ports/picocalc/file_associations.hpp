#ifndef MK61_PICOCALC_FILE_ASSOCIATIONS_HPP
#define MK61_PICOCALC_FILE_ASSOCIATIONS_HPP
#include "program_store.hpp"
#include <cstring>
namespace picocalc::file_associations {
// The resident only chooses an APP. Parsing, machine selection and disk
// behavior remain in that APP; no program-specific names are registered.
inline program_store::TypeMagic handler(const char* path) {
    if(!path) return program_store::TYPE_MAGIC_NONE;
    const char* dot=std::strrchr(path,'.');
    if(!dot || std::strlen(dot)!=4) return program_store::TYPE_MAGIC_NONE;
    if((dot[1]|32)=='m' && (dot[2]|32)=='p' && dot[3]=='3')
        return program_store::make_type_magic('A','3');
    static constexpr const char* spectrum[]={".z80",".sna",".szx",".trd",".scl",".tap",".tzx"};
    for(const char* extension:spectrum) {
        unsigned i=1;while(i<4 && (dot[i]|32)==extension[i]) ++i;
        if(i==4) return program_store::make_type_magic('Z','1');
    }
    return program_store::TYPE_MAGIC_NONE;
}
}
#endif
