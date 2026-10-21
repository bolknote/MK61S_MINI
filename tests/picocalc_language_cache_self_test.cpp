#include "services.hpp"
#include "script.hpp"
#include "language_cache.hpp"
#include "mk61_ref.hpp"
#include "crc32.hpp"
#include "mk8_codec.hpp"
#include "psram.hpp"
#include "external_cache.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <filesystem>
#include <string>
#include <vector>

namespace {
using namespace picocalc;
namespace cache=picocalc::language_cache;
void source(const char* path,const char* text) {
    assert(files::write_text(path,text,(unsigned)std::strlen(text)));
}
double reg(unsigned index) {
    double value=0;assert(mk61_ref::read({mk61_ref::Kind::R,(u8)index},value));return value;
}
std::string stored(const char* path,bool rf=true) {
    char name[files::PATH_SIZE];
    std::snprintf(name,sizeof(name),"/System/VMCache/Pico/%08lX-1-%u.cache",
        (unsigned long)mk61_crc32::calculate((const u8*)path,std::strlen(path)),rf?1:0);
    return name;
}
struct Input {
    const char* keys;
    bool invalidate=false;
    static bool pump(void* raw,u8& key) {
        auto& input=*(Input*)raw;
        if(!*input.keys) return false;
        if(input.invalidate) {
            cache::discard();
            source("/Cache Tests/input.bas","10 INPUT A\n20 .R1=A+1\n30 END\n");
            input.invalidate=false;
        }
        key=(u8)*input.keys++;return true;
    }
};
}

void picocalc_language_cache_test() {
    using namespace picocalc;
    Calculator calc;calc.init(true);
    static Services services;
    script::attach(calc,services);script::memory_mode(2);
    assert(files::mkdir("/Cache Tests"));
    const char* a="/Cache Tests/a.bas";
    const char* b="/Cache Tests/b.bas";
    source(a,"10 READ A\n20 @(1)=@(1)+A\n30 .R0=@(1)\n40 DATA 2\n50 END\n");
    source(b,"10 @(1)=@(1)*3\n20 .R0=@(1)\n30 END\n");
    const auto revision=files::revision();
    const auto before=cache::statistics();
    assert(services.run_external(a)==0 && reg(0)==2);
    assert(services.run_external(b)==0 && reg(0)==6);
    const auto cold=cache::statistics();
    assert(cold.compiles==before.compiles+2);
    for(unsigned i=0;i<10;++i) services.tick();
    script::prepare_files(); // The device loop and next launch retain physical IDs.
    assert(services.run_external(a)==0 && reg(0)==8);
    assert(services.run_external(b)==0 && reg(0)==24);
    const auto warm=cache::statistics();
    assert(warm.ram_hits==cold.ram_hits+2 && warm.compiles==cold.compiles);
    assert(files::revision()==revision); // Derived cache writes preserve source identities.
    assert(warm.allocated<=32768 && warm.used<=warm.allocated);
    source("/Cache Tests/screen.bas","10 PRINT \"CACHE FRAME\"\n20 END\n");
    source("/Cache Tests/arithmetic.bas","10 .R4=31\n20 END\n");
    assert(services.run_external("/Cache Tests/screen.bas")==0);
    const std::vector<u8> retained(script::native_frame(),script::native_frame()+12800);
    const auto frame_revision=script::frame_revision();
    assert(services.run_external("/Cache Tests/arithmetic.bas")==0 && reg(4)==31);
    assert(script::frame_revision()==frame_revision);
    std::vector<u8> overwritten(12800,0xA5);script::show_native_frame(overwritten.data());
    assert(services.run_external("/Cache Tests/arithmetic.bas")==0);
    assert(std::memcmp(script::native_frame(),retained.data(),retained.size())==0);
    const auto previous_profile=script::text_profile();
    assert(script::text_profile({8,3,5,0}));
    assert(services.run_external("/Cache Tests/arithmetic.bas")==0);
    char restored_row[65];script::text_row(0,restored_row,sizeof(restored_row));
    assert(std::strstr(restored_row,"CACHE FRAME"));
    assert(script::text_profile(previous_profile));
    program_store::Entry draft{};
    const char* recipe="print \"DRAFT\"\nret\n";
    assert(script::register_source(b,recipe,(u16)std::strlen(recipe),draft));
    script::prepare_files();
    assert(script::register_file(b,draft) && draft.type==program_store::ProgramType::TINYBASIC);
    const std::string full(65534,'Q');
    source("/Cache Tests/full.txt",full.c_str());
    assert(services.load_document("/Cache Tests/full.txt") && services.source_size()==65534);
    assert(!cache::statistics().allocated);
    assert(services.save_document("/Cache Tests/full-copy.txt"));
    std::vector<char> recovered(65535);unsigned recovered_size=0;
    assert(files::read_text("/Cache Tests/full-copy.txt",recovered.data(),recovered.size(),recovered_size));
    assert(recovered_size==full.size() && std::memcmp(recovered.data(),full.data(),full.size())==0);
    assert(services.load_document(b));

    script::reset_files(); // A fresh node registry must also accept the persistent cache.
    auto start=cache::statistics();
    assert(services.run_external(a)==0 && reg(0)==26);
    auto current=cache::statistics();
    if(current.disk_hits!=start.disk_hits+1 || current.compiles!=start.compiles || current.stores!=start.stores)
        std::fprintf(stderr,"Pico cache persistent cold stores=%lu; before hit/compile/store=%lu/%lu/%lu after=%lu/%lu/%lu rejected=%lu rf=%u\n",
            (unsigned long)cold.stores,(unsigned long)start.disk_hits,(unsigned long)start.compiles,(unsigned long)start.stores,
            (unsigned long)current.disk_hits,(unsigned long)current.compiles,(unsigned long)current.stores,
            (unsigned long)current.rejected,core_61::expanded_program_is_on());
    assert(current.disk_hits==start.disk_hits+1 && current.compiles==start.compiles && current.stores==start.stores);
    source(a,"10 READ A\n20 @(1)=@(1)+A\n30 .R0=@(1)\n40 DATA 3\n50 END\n");
    start=cache::statistics();
    assert(services.run_external(a)==0 && reg(0)==29);
    assert(cache::statistics().compiles==start.compiles+1);
    assert(files::rename(a,"/Cache Tests/renamed.bas"));
    assert(services.run_external("/Cache Tests/renamed.bas")==0 && reg(0)==32);
    assert(files::remove("/Cache Tests/renamed.bas"));
    assert(services.run_external("/Cache Tests/renamed.bas")==2);

    // Payload corruption is rejected by C6 CRCs, then rebuilt using the
    // independently checked owner marker. An unrelated collision is kept.
    const auto cached_b=stored(b);
    std::vector<u8> bytes(language_vm::MAX_MODULE+1024);unsigned used=0;
    assert(files::read(cached_b.c_str(),bytes.data(),bytes.size(),used) && used>100);
    bytes[used-1]^=1;
    assert(files::write(cached_b.c_str(),bytes.data(),used));
    start=cache::statistics();
    assert(services.run_external(b)==0 && reg(0)==96);
    current=cache::statistics();
    assert(current.rejected>start.rejected && current.compiles==start.compiles+1);
    cache::discard();start=cache::statistics();
    assert(services.run_external(b)==0 && reg(0)==288);
    assert(cache::statistics().disk_hits==start.disk_hits+1 && cache::statistics().compiles==start.compiles);
    const char* collision="/Cache Tests/collision.bas";
    source(collision,"10 .R2=17\n20 END\n");
    const auto colliding=stored(collision);
    assert(files::write(colliding.c_str(),(const u8*)"KEEP",4));
    assert(services.run_external(collision)==0 && reg(2)==17);
    assert(files::read(colliding.c_str(),bytes.data(),bytes.size(),used) && used==4 && !std::memcmp(bytes.data(),"KEEP",4));

    // INPUT pins the image across callbacks, even if an edit requests cache
    // reclamation. Next execution sees the newly edited source.
    const char* input_path="/Cache Tests/input.bas";
    source(input_path,"10 INPUT A\n20 .R1=A\n30 END\n");
    Input input{"7\n"};services.set_pump(Input::pump,&input);
    assert(services.run_external(input_path)==0 && reg(1)==7);
    input.keys="8\n";input.invalidate=true;start=cache::statistics();
    assert(services.run_external(input_path)==0 && reg(1)==8);
    assert(cache::statistics().ram_hits==start.ram_hits+1 && !cache::statistics().allocated);
    input.keys="9\n";
    assert(services.run_external(input_path)==0 && reg(1)==10);
    input.keys="\x1B";
    assert(services.run_external(input_path)==1);
    services.set_pump(nullptr,nullptr);
    assert(services.run_external(b)==0 && reg(0)==864);
    assert(files::begin_usb());
    assert(!cache::find(b,language_vm::Language::BASIC,true));
    assert(services.run_external(b)==2 && reg(0)==864);
    files::usb_eject();assert(files::end_usb());start=cache::statistics();
    assert(services.run_external(b)==0 && reg(0)==2592);
    assert(cache::statistics().compiles==start.compiles && cache::statistics().disk_hits==start.disk_hits+1);

    source("/Cache Tests/rf.bas","10 .RF=12\n20 END\n");
    assert(services.run_external("/Cache Tests/rf.bas")==0 && reg(15)==12);
    calc.init(false);script::memory_mode(0);
    assert(services.run_external("/Cache Tests/rf.bas")==2);
    calc.init(true);script::memory_mode(2);

    // Compile the actual corpus once, then repeat every part in reverse
    // order without recompilation, regardless of RAM eviction.
    assert(files::mkdir("/Cache Tests/Turochamp"));
    std::vector<std::string> game;
    for(const auto& entry:std::filesystem::directory_iterator("programs/games/Turochamp")) {
        if(entry.path().extension()!=".tbi") continue;
        std::ifstream file(entry.path());
        const std::string text((std::istreambuf_iterator<char>(file)),{});
        const std::string path="/Cache Tests/Turochamp/"+entry.path().filename().string();
        // The game uses M8 on the device; compile its UTF-8 source through
        // the same conversion as the installed corpus.
        std::vector<u8> m8(text.size()+1);usize n=0;
        assert(mk8::from_utf8((const u8*)text.data(),text.size(),m8.data(),m8.size(),n));
        assert(files::write_text(path.c_str(),(const char*)m8.data(),n));
        game.push_back(path);
    }
    std::vector<u8> module(language_vm::MAX_MODULE);
    std::vector<char> text(65535);
    assert(game.size()>20);
    unsigned corpus_bytes=0;
    for(const auto& path:game) {
        unsigned n=0;assert(files::read_text(path.c_str(),text.data(),text.size(),n));
        const language_vm::ResourceSource resources{0,0,language_vm::ResourceMode::EMBEDDED};
        cache::compilation();
        const auto compiled=language_vm::compile(language_vm::Language::BASIC,text.data(),(u16)n,
            module.data(),module.size(),true,&resources);
        if(compiled.error!=language_vm::Error::NONE)
            std::fprintf(stderr,"Cache corpus %s: %s line %u\n",path.c_str(),language_vm::error_name(compiled.error),compiled.line);
        assert(compiled.error==language_vm::Error::NONE);
        corpus_bytes+=compiled.size;
        language_vm::View view{};
        assert(language_vm::inspect(module.data(),compiled.size,view)==language_vm::Error::NONE);
        cache::remember(path.c_str(),true,files::revision(),text.data(),(u16)n,view);
    }
    start=cache::statistics();
    for(auto it=game.rbegin();it!=game.rend();++it) {
        auto ready=cache::find(it->c_str(),language_vm::Language::BASIC,true,module.data(),module.size());
        if(ready) cache::release(ready);
        else {
            unsigned n=0;assert(files::read_text(it->c_str(),text.data(),text.size(),n));
            language_vm::View view{};
            assert(cache::load(it->c_str(),language_vm::Language::BASIC,true,text.data(),(u16)n,module.data(),view));
            cache::remember(it->c_str(),true,files::revision(),text.data(),(u16)n,view,false);
        }
    }
    assert(cache::statistics().compiles==start.compiles);
    assert(cache::statistics().packs>0 && cache::statistics().thaws>start.thaws);
    std::printf("PicoCalc Turochamp cache corpus: %zu BASIC modules, %u bytecode bytes, repeat needs zero compiles\n",game.size(),corpus_bytes);
    // More than 32 independent programs force the bounded RAM/disk policies.
    for(unsigned i=0;i<40;++i) {
        const auto path="/Cache Tests/pressure"+std::to_string(i)+".bas";
        source(path.c_str(),"10 .R3=123\n20 END\n");
    }
    for(unsigned i=0;i<40;++i) {
        const auto path="/Cache Tests/pressure"+std::to_string(i)+".bas";
        assert(services.run_external(path.c_str())==0 && reg(3)==123);
    }
    assert(cache::statistics().allocated<=32768 && cache::statistics().evictions>0);
    assert(files::read(colliding.c_str(),bytes.data(),bytes.size(),used) && used==4 && !std::memcmp(bytes.data(),"KEEP",4));
    cache::discard();script::reset_files();
    // With the optional chip present, programs evicted from the 32 KiB hot
    // cache are copied back into the existing compiler image. No PSRAM
    // pointer is executed, and the fallback still owns an ordinary SRAM VM.
    std::vector<u8> external_memory(psram::CAPACITY);
    psram::test_memory(external_memory.data(),external_memory.size());
    assert(psram::init() && external_cache::init());
    assert(files::mkdir("/Cache Tests/External"));
    for(unsigned i=0;i<48;++i)
        source(("/Cache Tests/External/"+std::to_string(i)+".bas").c_str(),"10 .R3=.R3+1\n20 END\n");
    for(unsigned i=0;i<48;++i)
        assert(services.run_external(("/Cache Tests/External/"+std::to_string(i)+".bas").c_str())==0);
    cache::discard();
    script::reset_files(); // Recycle IDs; persistent PSRAM owners must still match paths.
    start=cache::statistics();
    for(unsigned i=48;i--;) assert(services.run_external(("/Cache Tests/External/"+std::to_string(i)+".bas").c_str())==0);
    current=cache::statistics();
    assert(current.psram_hits>=start.psram_hits+30 && current.compiles==start.compiles);
    // Source mutation changes the media revision before any external lookup.
    source("/Cache Tests/External/0.bas","10 .R3=733\n20 END\n");
    assert(services.run_external("/Cache Tests/External/0.bas")==0 && reg(3)==733);
    cache::discard();script::reset_files();external_cache::invalidate_modules();
    psram::test_memory(nullptr,0);
    assert(!psram::init());
    std::printf("PicoCalc PSRAM VM reuse: %lu hits across 48 programs, SRAM VM and edit invalidation PASS\n",
        (unsigned long)(current.psram_hits-start.psram_hits));
    std::puts("PicoCalc VM cache: RAM/SD reuse, DATA/state, edits/rename/delete, corrupt/foreign files, INPUT pins/cancel, RF and bounded eviction PASS");
}
