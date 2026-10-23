#ifndef MK61_PICOCALC_SOURCE_DOCUMENT_HPP
#define MK61_PICOCALC_SOURCE_DOCUMENT_HPP
#include <cstring>
#include <memory>
#include <new>
#include <initializer_list>
#include "language_source_document.hpp"
#include "shared_memory_buffer.hpp"
#include "storage.hpp"
#include "buffers.hpp"

namespace picocalc {
// The editor uses the same 1-KiB document window as STM32. Its immutable
// original and two private draft banks use the shared external-buffer owner;
// no maximum-size source or draft is reserved in resident SRAM.
class SourceDocument {
    using Document = language_vm::source::Document;
    struct Store {
        shared_memory::Buffer original, draft;
        u16 length=0;
        bool window_ready=false;
        std::unique_ptr<Document> editor;
        mutable u8 cache[512]{};
        mutable unsigned cache_at=0,cache_size=0;
        bool read(u16 at,u8* out,u16 count) const {
            return editor ? editor->read(at,out,count) : original.read(at,out,count);
        }
        static bool initial(void* raw,u16 at,u8* out,u16 count) {
            return ((Store*)raw)->original.read(at,out,count);
        }
        static bool begin(void* raw,u32*,u16 capacity) {
            auto& self=*(Store*)raw;
            if(capacity!=language_vm::source::DRAFT_PAGES*2) return false;
            return self.draft.acquire(shared_memory::Owner::STORAGE_WORKSPACE,
                unsigned(capacity)*language_vm::source::DRAFT_PAGE_SIZE,
                shared_memory::BufferAccess::BLOCK);
        }
        static bool page(void* raw,u32 key,u8* out) {
            auto& self=*(Store*)raw;
            if(key<language_vm::source::DRAFT_FIRST_KEY) return false;
            return self.draft.read((key-language_vm::source::DRAFT_FIRST_KEY)*512U,out,512);
        }
        static bool write(void* raw,u32 key,const u8* bytes) {
            auto& self=*(Store*)raw;
            if(key<language_vm::source::DRAFT_FIRST_KEY) return false;
            return self.draft.write((key-language_vm::source::DRAFT_FIRST_KEY)*512U,bytes,512);
        }
        static bool forget(void*,u32,u16) { return true; }
        static void end(void* raw) { (void)((Store*)raw)->draft.reset(); }
        bool edit() {
            if(editor) return true;
            auto next=std::unique_ptr<Document>(new(std::nothrow) Document(
                {this,initial,length},{this,begin,page,write,forget,end}));
            if(!next || !next->open()) return false;
            editor=std::move(next);return true;
        }
    };
    std::unique_ptr<Store> store_;
    unsigned revision_=1;
    enum class Error : u8 { NONE,LIMIT,MEMORY,READ,WRITE };
    mutable Error error_=Error::NONE;
    bool fail(Error error) const { error_=error;return false; }
    bool assign(std::unique_ptr<Store> next) {
        store_=std::move(next);++revision_;error_=Error::NONE;return true;
    }
public:
    struct Statistics { unsigned bytes=0,sram_bytes=0,external_bytes=0,window_bytes=0; };
    Statistics statistics() const {
        Statistics result;result.bytes=size();
        if(store_) {
            result.sram_bytes=sizeof(Store)+(store_->editor?sizeof(Document):0);
            result.window_bytes=store_->editor?Document::WINDOW_SIZE:0;
            for(const auto* b:{&store_->original,&store_->draft}) {
                if(b->data()) result.sram_bytes+=(unsigned)b->size();
                else result.external_bytes+=(unsigned)b->size();
            }
        }
        return result;
    }
    static constexpr unsigned CAPACITY=language_vm::source::MAX_SIZE+1U;
    const char* error() const {
        switch(error_) {
        case Error::LIMIT:return "Source limit: 65534 bytes";
        case Error::MEMORY:return "Not enough memory for editor";
        case Error::READ:return "Cannot read source";
        case Error::WRITE:return "Cannot write editor draft";
        default:return "";
        }
    }
    unsigned size() const { return store_ ? store_->editor ? store_->editor->size() : store_->length : 0; }
    unsigned revision() const { return revision_; }
    void clear() { store_.reset();++revision_;error_=Error::NONE; }
    bool read(u16 at,u8* out,u16 count) const {
        if(at>size() || count>size()-at || (count && !out)) return fail(Error::READ);
        if(count && (!store_ || !store_->read(at,out,count))) return fail(Error::READ);
        return true;
    }
    language_vm::source::Input input() const {
        return {const_cast<SourceDocument*>(this),
            [](void* raw,u16 at,u8* out,u16 n) { return ((SourceDocument*)raw)->read(at,out,n); },(u16)size()};
    }
    bool load(language_vm::source::Input source) {
        if(!buffers::init()) return fail(Error::MEMORY);
        if(source.size>=CAPACITY || (source.size && !source.read)) return fail(Error::LIMIT);
        auto next=std::unique_ptr<Store>(new(std::nothrow) Store);
        if(!next || (source.size && !next->original.acquire(shared_memory::Owner::STORAGE_WORKSPACE,
                source.size,shared_memory::BufferAccess::BLOCK))) return fail(Error::MEMORY);
        u8 bytes[512];
        for(unsigned at=0;at<source.size;) {
            const unsigned n=source.size-at<sizeof(bytes)?source.size-at:sizeof(bytes);
            if(!source.read(source.context,(u16)at,bytes,(u16)n) || !next->original.write(at,bytes,n)) return fail(Error::READ);
            at+=n;
        }
        next->length=source.size;return assign(std::move(next));
    }
    bool load(const char* path) {
        if(!buffers::init()) return fail(Error::MEMORY);
        files::Entry info{};
        if(!files::stat(path,info) || info.directory) return fail(Error::READ);
        auto next=std::unique_ptr<Store>(new(std::nothrow) Store);
        const unsigned capacity=info.size<CAPACITY?info.size:CAPACITY-1;
        if(!next || (capacity && !next->original.acquire(shared_memory::Owner::STORAGE_WORKSPACE,
                capacity,shared_memory::BufferAccess::BLOCK))) return fail(Error::MEMORY);
        struct Output { Store& store;unsigned at=0; } output{*next};
        unsigned used=0;
        if(!files::read_text_stream(path,[](void* raw,const u8* bytes,unsigned n) {
                auto& out=*(Output*)raw;
                if(!out.store.original.write(out.at,bytes,n)) return false;
                out.at+=n;return true;
            },&output,CAPACITY,used)) return fail(Error::READ);
        next->length=(u16)used;return assign(std::move(next));
    }
    bool save(const char* path) const {
        auto* writer=files::begin_write(path,true);
        if(!writer) return false;
        u8 bytes[512];bool ok=true;
        for(unsigned at=0;ok && at<size();) {
            const unsigned n=size()-at<sizeof(bytes)?size()-at:sizeof(bytes);
            ok=read((u16)at,bytes,(u16)n) && files::append_write(writer,bytes,n);at+=n;
        }
        if(ok) return files::commit_write(writer);
        files::cancel_write(writer);return false;
    }
    // Leaving the editor retains its logical document in PSRAM but releases
    // the SRAM window and private draft banks. Failure keeps the old owner.
    bool park() { return !store_ || !store_->editor || load(input()); }
    char byte(unsigned at) const {
        if(at>=size() || !store_) return 0;
        auto& s=*store_;
        if(!s.cache_size || at<s.cache_at || at-s.cache_at>=s.cache_size) {
            s.cache_at=at/sizeof(s.cache)*sizeof(s.cache);
            const unsigned n=size()-s.cache_at<sizeof(s.cache)?size()-s.cache_at:sizeof(s.cache);
            if(!read((u16)s.cache_at,s.cache,(u16)n)) { s.cache_size=0;return 0; }
            s.cache_size=n;
        }
        return (char)s.cache[at-s.cache_at];
    }
    u16 line_start(u16 at) const {
        if(at>size()) at=(u16)size();
        while(at && byte(at-1)!='\n') --at;
        return at;
    }
    u16 line_end(u16 at) const {
        while(at<size() && byte(at)!='\n') ++at;
        return at;
    }
    u16 next_line(u16 at) const { at=line_end(at);return at<size()?(u16)(at+1):at; }
    u16 previous_line(u16 at) const { return line_start(at?(u16)(at-1):0); }
    void move_line(u16& at,int delta) const {
        const unsigned column=at-line_start(at);
        u16 start=line_start(at);
        if(delta<0) { if(!start) return;start=previous_line(start); }
        else { const u16 next=next_line(start);if(next==start || next>=size()) { at=(u16)size();return; }start=next; }
        const unsigned end=line_end(start);at=(u16)(start+(column<end-start?column:end-start));
    }
    bool replace(u16 begin,u16 end,const char* text,u16& cursor) {
        if(!text || begin>end || end>size() || std::strlen(text)>CAPACITY-1-(size()-(end-begin))) return fail(Error::LIMIT);
        if(!buffers::init()) return fail(Error::MEMORY);
        if(!store_) store_.reset(new(std::nothrow) Store);
        if(!store_ || !store_->edit()) return fail(Error::MEMORY);
        auto& doc=*store_->editor;
        text_editor::Buffer editor{};
        if(!store_->window_ready || begin<doc.start() || end>unsigned(doc.start())+doc.used() ||
           unsigned(doc.used())-(end-begin)+std::strlen(text)>Document::WINDOW_SIZE) {
            // seek() reads through the public window before publishing its
            // new range. Keep the old bytes if a PSRAM read fails partway.
            char previous[sizeof(doc.window)];
            if(store_->window_ready) std::memcpy(previous,doc.window,sizeof(previous));
            if(!doc.seek(editor,begin)) {
                if(store_->window_ready) std::memcpy(doc.window,previous,sizeof(previous));
                return fail(Error::WRITE);
            }
            store_->window_ready=true;
        } else text_editor::init(editor,doc.window,sizeof(doc.window));
        const unsigned first=begin-doc.start(),last=first+(end-begin);
        editor.cursor=(u16)first;
        if(last>editor.len || !text_editor::replace_range(editor.source,editor.len,editor.cursor,
                sizeof(doc.window),(u16)first,(u16)last,text) || !doc.accept(editor.len)) return fail(Error::WRITE);
        cursor=(u16)(doc.start()+editor.cursor);store_->cache_size=0;++revision_;error_=Error::NONE;return true;
    }
};
static_assert(sizeof(SourceDocument)<=16,"Only a document owner belongs in the resident");
}
#endif
