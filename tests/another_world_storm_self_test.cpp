#include "../examples/portable-apps/ANOTHER/display_storm.h"
#include <cassert>
#include <cstring>
#include <vector>

namespace {
constexpr unsigned pixels = AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT;
constexpr unsigned storage_base = 65536;
uint8_t ram[120000], scratch[2 * AW_STORM_BLOCK];
uint16_t gram[2][pixels];
uint8_t live[AW_VIDEO_PAGE_BYTES];
const uint16_t palette[16] = {0x1234, 0xabcd, 0xf01d};
aw_display_compact slots[2];
aw_display_pages pages;
aw_display_storm storm;
unsigned selected, visible, writes;
bool store_fails;

void put16(uint8_t *p, unsigned x) { p[0]=x; p[1]=x>>8; }
void put32(uint8_t *p, uint32_t x) { put16(p,x); put16(p+2,x>>16); }

void seal(std::vector<uint8_t> &data) {
    uint32_t hash = AW_STORM_HASH_INIT;
    for (size_t i=8; i<data.size(); ++i) hash=aw_storm_hash_byte(hash,data[i]);
    put32(data.data()+4,hash);
}

std::vector<uint8_t> fixture() {
    std::vector<uint8_t> file(AW_STORM_HEADER);
    std::memcpy(file.data(),"AWS1",4);
    put16(file.data()+8,41);
    std::memset(live,0,sizeof(live));
    for (unsigned i=0;i<AW_STORM_WARM_FRAMES;++i)
        put32(file.data()+12+i*4,aw_storm_frame_hash(live,palette));
    for (unsigned i=0;i<16;++i) put16(file.data()+32+i*2,palette[i]);

    std::memset(live,0x11,sizeof(live));
    for (unsigned i=0;i<AW_STORM_FRAMES;++i) {
        if (i==1) live[80*AW_VIDEO_STRIDE+5]=0x22;
        uint8_t header[6]={};
        put32(header,aw_storm_frame_hash(live,palette));
        header[5]=i==0 ? AW_STORM_WARM_FRAMES : i==1;
        file.insert(file.end(),header,header+6);
        if (!i) {
            for (unsigned y=0;y<AW_VIDEO_HEIGHT;y+=AW_STORM_STRIP_ROWS) {
                uint8_t r[]={0,uint8_t(y),AW_VIDEO_STRIDE,AW_STORM_STRIP_ROWS,0,0};
                put16(r+4,AW_STORM_BLOCK);
                file.insert(file.end(),r,r+6);
                file.insert(file.end(),AW_STORM_BLOCK,0x11);
            }
        } else if (i==1) {
            const uint8_t r[]={5,80,1,1,1,0,0x22};
            file.insert(file.end(),r,r+7);
        }
    }
    seal(file);
    return file;
}

bool read_file(void *ctx, uint32_t at, void *out, uint32_t size) {
    const auto &data=*static_cast<const std::vector<uint8_t>*>(ctx);
    assert(at+size<=data.size() && size<=AW_ASSET_MAX_TRANSFER);
    std::memcpy(out,data.data()+at,size);
    return true;
}
bool read_store(void *, uint32_t at, void *out, uint32_t size) {
    assert(at>=storage_base && at+size<=sizeof(ram));
    if (store_fails) return false;
    std::memcpy(out,ram+at,size);
    return true;
}
bool write_store(void *, uint32_t at, const void *data, uint32_t size) {
    assert(at>=storage_base && at+size<=sizeof(ram));
    std::memcpy(ram+at,data,size);
    return true;
}
bool select(void *, unsigned page) { assert(page<2);selected=page;return true; }
bool show(void *, unsigned page) { assert(page==selected);visible=page;return true; }
bool wait(void *) { return true; }
bool draw(void *, unsigned x,unsigned y,unsigned w,unsigned h,
          const uint8_t *data, const uint16_t *colors, bool clear) {
    assert(!clear && data==scratch);
    for (unsigned row=0;row<h;++row)
        for (unsigned col=0;col<w;col+=2) {
            auto *out=gram[selected]+(y+row)*AW_VIDEO_WIDTH+x+col;
            const uint8_t pair=*data++;
            out[0]=colors[pair>>4];out[1]=colors[pair&15];
        }
    ++writes;
    return true;
}

void init_pages(aw_assets &assets, unsigned front) {
    pages={};
    for (unsigned i=0;i<2;++i) {
        slots[i]={};slots[i].assets=&assets;slots[i].scratch=scratch;slots[i].valid=true;
        pages.slot[i]=&slots[i];
        for (auto &p:gram[i]) p=palette[0];
    }
    visible=selected=pages.visible=pages.selected=front;
    writes=0;
}
}

int main() {
    aw_assets assets{};
    assets.capacity=sizeof(ram);assets.store_read=read_store;assets.store_write=write_store;
    auto data=fixture();
    auto load=[&] (unsigned limit) {
        return aw_storm_load(&storm,&assets,storage_base-1,scratch,limit,read_file,&data);
    };
    for (unsigned front:{0u,1u}) {
        init_pages(assets, front);
        assert(load(data.size()) && storm.first==41);
        std::memset(live,0,sizeof(live));
        for (unsigned n=0;n<AW_STORM_WARM_FRAMES;++n) {
            assert(aw_storm_warm(&storm,&pages,n,live,palette,select,draw,nullptr));
            assert(visible==front && !slots[front^1].valid && slots[front].valid);
        }
        assert(writes==5);
        std::memset(live,0x11,sizeof(live));
        assert(aw_storm_present(&storm,&pages,0,live,palette,select,show,draw,wait,nullptr));
        assert(writes==5 && visible==(front^1));
        for (auto p:gram[visible]) assert(p==palette[1]);
        live[80*AW_VIDEO_STRIDE+5]=0x22;
        assert(aw_storm_present(&storm,&pages,1,live,palette,select,show,draw,wait,nullptr));
        assert(writes==6 && gram[visible][80*AW_VIDEO_WIDTH+10]==palette[2]);
        live[AW_VIDEO_PAGE_BYTES-1]^=1; // Mismatch outside all replayed rectangles.
        assert(!aw_storm_present(&storm,&pages,2,live,palette,select,show,draw,wait,nullptr));
        assert(!storm.ready && writes==6 && !slots[visible].valid && !assets.fault);
    }
    init_pages(assets,1);
    assert(load(data.size()));
    std::memset(live,0,sizeof(live));
    assert(aw_storm_warm(&storm,&pages,0,live,palette,select,draw,nullptr));
    store_fails=true;
    assert(!aw_storm_warm(&storm,&pages,1,live,palette,select,draw,nullptr));
    assert(!storm.ready && visible==1 && slots[1].valid && !slots[0].valid && !assets.fault);
    assert(!load(data.size()-1));
    data.back()^=1;
    assert(!load(data.size()));
    data.back()^=1;
    data[AW_STORM_HEADER+6+2]=255; // Invalid geometry even with a matching file hash.
    seal(data);
    assert(!load(data.size()));
}
