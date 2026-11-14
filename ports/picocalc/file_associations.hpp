#ifndef MK61_PICOCALC_FILE_ASSOCIATIONS_HPP
#define MK61_PICOCALC_FILE_ASSOCIATIONS_HPP
#include "program_store.hpp"
#include <cstring>
namespace picocalc::file_associations {
// The resident chooses an APP. The APP parses the media and selects the machine.
inline program_store::TypeMagic handler(const char* path) {
    if(!path) return program_store::TYPE_MAGIC_NONE;
    const char* dot=std::strrchr(path,'.');
    if(!dot || std::strlen(dot)!=4) return program_store::TYPE_MAGIC_NONE;
    const char* leaf = std::strrchr(path, '/');
    leaf = leaf ? leaf + 1 : path;
    // Only the distributed game collection has a reserved IMG name.
    if(dot - leaf == 5 && (leaf[0]|32) == 'g' && (leaf[1]|32) == 'a' &&
       (leaf[2]|32) == 'm' && (leaf[3]|32) == 'e' && (leaf[4]|32) == 's' &&
       (dot[1]|32) == 'i' && (dot[2]|32) == 'm' && (dot[3]|32) == 'g')
        return program_store::make_type_magic('Z','1');
    static constexpr const char* spectrum[]={".z80",".sna",".szx",".trd",".scl",".tap",".tzx"};
    for(const char* extension:spectrum) {
        unsigned i=1;while(i<4 && (dot[i]|32)==extension[i]) ++i;
        if(i==4) return program_store::make_type_magic('Z','1');
    }
    return program_store::TYPE_MAGIC_NONE;
}
}
#endif
