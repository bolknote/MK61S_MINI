#include "file_associations.hpp"
#include "loadable_module_format.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <vector>
namespace picocalc {
namespace {
std::map<std::string,std::vector<u8>> image;
std::set<std::string> directories;
unsigned scans=0,launches=0;
std::string launched,message;
constexpr auto spectrum_magic=program_store::make_type_magic('Z','1');
void directory(std::string path) {
    while(!path.empty()) {
        directories.insert(path);
        if(path=="/")break;
        const auto slash=path.rfind('/');path=slash?path.substr(0,slash):"/";
    }
}
void file(const std::string& path,const std::vector<u8>& bytes={}) {
    directory(path.substr(0,path.rfind('/')));image[path]=bytes;
}
void app(const std::string& path,u16 magic=spectrum_magic,bool corrupt=false) {
    loadable_module::Header h{};h.kind=loadable_module::Kind::APPLICATION;h.compression=loadable_module::Compression::ZX0;
    h.flags=MK61_PORTABLE_APP_FLAG|MK61_APP_RELOCATABLE_FLAG|MK61_APP_ARMV6M_FLAG;h.load_address=MK61_PORTABLE_APP_ADDRESS;
    h.stored_size=h.code_stored_size=16;h.image_size=h.memory_size=32;h.handled_type_magic=magic;
    std::vector<u8> bytes(64);assert(loadable_module::encode_header(h,4096,bytes.data()));
    if(corrupt)bytes[4]^=1;
    file(path,bytes);
}
void reset() { image.clear();directories.clear();scans=launches=0;launched.clear();message.clear();directory("/"); }
}
namespace diagnostics { void feed_watchdog() {} }
namespace files {
constexpr unsigned PATH_SIZE=384;
struct Entry { char name[256];bool directory; };
bool list(const char* path,unsigned skip,Entry* entries,unsigned capacity,unsigned& used,bool& more) {
    ++scans;used=0;more=false;if(!directories.count(path))return false;
    const std::string prefix=std::string(path)+(std::string(path)=="/"?"":"/");
    std::map<std::string,bool> names;
    for(const auto& p:directories)if(p.compare(0,prefix.size(),prefix)==0) {
        auto leaf=p.substr(prefix.size());if(!leaf.empty() && leaf.find('/')==std::string::npos)names[leaf]=true;
    }
    for(const auto& p:image)if(p.first.compare(0,prefix.size(),prefix)==0) {
        auto leaf=p.first.substr(prefix.size());if(!leaf.empty() && leaf.find('/')==std::string::npos)names[leaf]=false;
    }
    unsigned at=0;for(const auto& item:names) {
        if(at++<skip)continue;
        if(used==capacity){more=true;break;}
        auto& e=entries[used++];std::snprintf(e.name,sizeof(e.name),"%s",item.first.c_str());e.directory=item.second;
    }
    return true;
}
bool read_range(const char* path,u32 offset,u8* out,unsigned n,unsigned& used) {
    used=0;auto it=image.find(path);if(it==image.end())return false;
    if(offset<it->second.size()) {
        used=std::min(n,unsigned(it->second.size()-offset));std::copy_n(it->second.data()+offset,used,out);
    }
    return true;
}
}
namespace script {
bool register_file(const char* path,program_store::Entry& out) {
    if(!image.count(path))return false;out={};out.id=37;return true;
}
}
enum class ServicePage { BROWSER };
class Services {
public:
    u8 run_handled(const char*,u16);
    u8 run_native(const char* path,u16 document) { assert(document==37);++launches;launched=path;return 0; }
    void message(const char* value,ServicePage) { picocalc::message=value; }
};
#include "picocalc_file_handler_production.inc"
}
int main() {
    using namespace picocalc;Services service;
    for(const char* path:{"/games/A.Z80","/games/A.sna","/games/A.TRD","/games/A.ScL"})assert(file_associations::handler(path)==spectrum_magic);
    for(const char* path:{"/games/A.z80.txt","/A.sna/file","/A.img","/A.tap"})assert(!file_associations::handler(path));
    reset();file("/Games/Sub/Title.sna");app("/Games/Sub/Local.App");app("/Apps/ZX/SPECTRUM.APP");
    assert(!service.run_handled("/Games/Sub/Title.sna",spectrum_magic) && launched=="/Games/Sub/Local.App");
    reset();file("/Collection/ZX/Sub/Title.Z80");app("/Collection/ZX/SPECTRUM.APP");
    assert(!service.run_handled("/Collection/ZX/Sub/Title.Z80",spectrum_magic) && launched=="/Collection/ZX/SPECTRUM.APP");
    reset();file("/Elsewhere/My Game.trd");app("/Apps/ZX/00broken.APP",spectrum_magic,true);app("/Apps/ZX/01other.APP",0x3143);app("/Apps/ZX/Spectrum.aPp");
    assert(!service.run_handled("/Elsewhere/My Game.trd",spectrum_magic) && launched=="/Apps/ZX/Spectrum.aPp");
    reset();file("/Games/Title.scl");app("/MK61S-HIL/SPECTRUM/SPECTRUM.APP");
    assert(!service.run_handled("/Games/Title.scl",spectrum_magic) && launched=="/MK61S-HIL/SPECTRUM/SPECTRUM.APP");
    reset();file("/Games/Title.sna");assert(service.run_handled("/Games/Title.sna",spectrum_magic)==1 && !launches && !message.empty());
    reset();for(unsigned i=0;i<5000;++i)file("/Apps/F"+std::to_string(i)+".txt");
    file("/Games/Title.sna");assert(service.run_handled("/Games/Title.sna",spectrum_magic)==1 && scans<1100);
    std::puts("Production file associations: local/ancestor/nested APP discovery, mixed case, real header CRC/type, document ID, no-handler and finite scan PASS");
}
