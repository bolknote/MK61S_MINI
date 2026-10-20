#ifndef MK61_PICOCALC_NATIVE_ASSETS_HPP
#define MK61_PICOCALC_NATIVE_ASSETS_HPP
#include "storage.hpp"
#include <cstdio>
#include <cstring>
namespace picocalc { namespace native_assets {
// An optional sibling supplies artwork for this panel. Original links and
// compact assets remain usable on every other model and in legacy USB Screen.
inline bool image(const char* path,char out[files::PATH_SIZE],files::Entry& info) {
    const char* dot=std::strrchr(path,'.');
    const char* slash=std::strrchr(path,'/');
    if(!dot || (slash && dot<slash) || dot-path>=(int)files::PATH_SIZE) return false;
    const int n=std::snprintf(out,files::PATH_SIZE,"%.*s-320%s",(int)(dot-path),path,dot);
    return n>0 && n<(int)files::PATH_SIZE && files::stat(out,info) && !info.directory;
}
} }
#endif
