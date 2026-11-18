#include "../examples/portable-apps/ANOTHER/display_storm.h"
#include <cassert>
#include <cstring>
#include <vector>

namespace {
constexpr unsigned pixels = AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT;
constexpr unsigned storage_base = 65536;
uint8_t ram[170000], scratch[2 * AW_STORM_BLOCK];
uint16_t gram[2][pixels];
uint8_t live[AW_VIDEO_PAGE_BYTES];
const uint16_t palette[16] = {0x1234, 0xabcd, 0xf01d};
aw_display_compact slots[2];
aw_display_pages pages;
aw_display_storm storm;
unsigned selected, visible, writes, reads, last_lead;
bool store_fails, dma_busy;

void put16(uint8_t *p, unsigned x) { p[0]=x; p[1]=x>>8; }
void put32(uint8_t *p, uint32_t x) { put16(p,x); put16(p+2,x>>16); }

void seal(std::vector<uint8_t> &data) {
    uint32_t hash = AW_STORM_HASH_INIT;
    for (size_t i=8; i<data.size(); ++i) hash=aw_storm_hash_byte(hash,data[i]);
    put32(data.data()+4,hash);
}

std::vector<uint8_t> fixture(bool ahead = false) {
    std::vector<uint8_t> file(AW_STORM_HEADER + (ahead ? AW_STORM_PALETTE_BYTES : 0));
    std::memcpy(file.data(),ahead ? "AWS2" : "AWS1",4);
    put16(file.data()+8,41);
    std::memset(live,0,sizeof(live));
    for (unsigned i=0;i<AW_STORM_WARM_FRAMES;++i)
        put32(file.data()+12+i*4,aw_storm_frame_hash(live,palette));
    for (unsigned i=0;i<16;++i) {
        put16(file.data()+32+i*2,palette[i]);
        if (ahead) put16(file.data()+AW_STORM_HEADER+i*2,palette[i]);
    }

    std::memset(live,0x11,sizeof(live));
    for (unsigned i=0;i<AW_STORM_FRAMES;++i) {
        if (i==1) {
            if (ahead) std::memset(live,0,sizeof(live));
            live[80*AW_VIDEO_STRIDE+5]=0x22;
        }
        if (ahead && i==2) live[80*AW_VIDEO_STRIDE+6]=0x11;
        uint8_t header[6]={};
        put32(header,aw_storm_frame_hash(live,palette));
        header[4]=ahead && i>0;
        header[5]=i==0 ? AW_STORM_WARM_FRAMES : i==1 || (ahead && i==2);
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
        } else if (ahead && i==2) {
            const uint8_t r[]={6,80,1,1,1,0,0x11};
            file.insert(file.end(),r,r+7);
        }
    }
    seal(file);
    return file;
}

std::vector<uint8_t> prelude_fixture() {
    auto file = fixture(true);
    file[3] = '3';
    uint8_t meta[AW_STORM_PRELUDE_HEADER] = {};
    meta[16] = 1;
    file.insert(file.end(), meta, meta + sizeof(meta));
    // A ZX0 strip consisting of 6400 repeats of packed index 0x11.
    const uint8_t strip[] = {0x90, 0x11, 0x15, 0x55, 0x75, 0x55, 0x58};
    for (unsigned image = 0; image < 2; ++image) {
        file.resize(file.size() + AW_STORM_PALETTE_BYTES);
        for (unsigned y = 0; y < AW_VIDEO_HEIGHT; y += AW_STORM_STRIP_ROWS) {
            const uint8_t r[] = {0, uint8_t(y), AW_VIDEO_STRIDE, AW_STORM_STRIP_ROWS, sizeof(strip), 0};
            file.insert(file.end(), r, r + sizeof(r));
            file.insert(file.end(), strip, strip + sizeof(strip));
        }
    }
    const uint8_t delta[] = {0, 0, 1, 1, 1, 0, 0x11};
    file.insert(file.end(), delta, delta + sizeof(delta));
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
    ++reads;
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
bool wait(void *, unsigned lead) { if (lead) last_lead=lead; return true; }
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
unsigned try_select(void *ctx,unsigned page) {
    if (dma_busy) return 2;
    return select(ctx,page);
}
unsigned try_draw(void *ctx,unsigned x,unsigned y,unsigned w,unsigned h,
                  const uint8_t *data,const uint16_t *colors,bool clear) {
    if (dma_busy) return 2;
    assert(selected!=visible);
    return draw(ctx,x,y,w,h,data,colors,clear);
}
const aw_storm_output lcd{select,show,draw,wait,try_select,try_draw,24000000,nullptr,nullptr};

void init_pages(aw_assets &assets, unsigned front) {
    pages={};
    for (unsigned i=0;i<2;++i) {
        slots[i]={};slots[i].assets=&assets;slots[i].scratch=scratch;slots[i].valid=true;
        pages.slot[i]=&slots[i];
        for (auto &p:gram[i]) p=palette[0];
    }
    visible=selected=pages.visible=pages.selected=front;
    writes=reads=last_lead=0;
}
}

int main() {
    aw_storm_tail timing{};
    timing.available = true;
    aw_storm_configure_timing(&timing, 125000000u, 24000000u);
    assert(!timing.overlap && timing.writeback[0].min_pixels == 1000 && timing.writeback[0].round_pixels == 1400);
    assert(timing.writeback[1].min_pixels == 5000 && !timing.writeback[1].round_pixels && !timing.writeback[2].min_pixels);
    assert(timing.black_before_rows[1] == 56 && timing.black_before_rows[2] == 88);
    aw_storm_configure_timing(&timing, 200000000u, 24000000u);
    assert(timing.overlap);
    for (const auto &policy : timing.writeback) assert(!policy.min_pixels);
    for (auto rows : timing.black_before_rows) assert(!rows);
    aw_storm_configure_timing(&timing, 125000000u, 12000000u);
    assert(!timing.overlap && !timing.writeback[0].min_pixels && !timing.writeback[1].min_pixels);
    timing.available = false;
    aw_storm_configure_timing(&timing, 125000000u, 24000000u);
    assert(!timing.writeback[0].min_pixels && !timing.writeback[1].min_pixels);

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
        assert(aw_storm_present(&storm,&pages,0,live,palette,&lcd,nullptr));
        assert(writes==5 && visible==(front^1));
        for (auto p:gram[visible]) assert(p==palette[1]);
        live[80*AW_VIDEO_STRIDE+5]=0x22;
        assert(aw_storm_present(&storm,&pages,1,live,palette,&lcd,nullptr));
        assert(writes==6 && gram[visible][80*AW_VIDEO_WIDTH+10]==palette[2]);
        live[AW_VIDEO_PAGE_BYTES-1]^=1; // Mismatch outside all replayed rectangles.
        assert(!aw_storm_present(&storm,&pages,2,live,palette,&lcd,nullptr));
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

    store_fails=false;
    data=fixture(true);
    for (bool mismatch:{false,true}) {
        init_pages(assets,1);
        assert(load(data.size()) && storm.ahead);
        std::memset(live,0,sizeof(live));
        for (unsigned n=0;n<AW_STORM_WARM_FRAMES;++n)
            assert(aw_storm_warm(&storm,&pages,n,live,palette,select,draw,nullptr));
        std::memset(live,0x11,sizeof(live));
        // Block the speculative page selection, then its rectangle submit.
        dma_busy=true;
        assert(aw_storm_present(&storm,&pages,0,live,palette,&lcd,nullptr));
        assert(visible==0 && selected==0 && writes==5 && storm.pending==1);
        dma_busy=false;
        assert(try_select(nullptr,1)==1);
        pages.selected=1;
        dma_busy=true;
        const unsigned before=reads;
        aw_storm_pump(&storm,&pages,&lcd,nullptr);
        assert(storm.staged && visible==0 && writes==5 && reads==before+1);
        aw_storm_pump(&storm,&pages,&lcd,nullptr);
        assert(reads==before+1); // No second PSRAM read on a busy worker.
        dma_busy=false;
        aw_storm_pump(&storm,&pages,&lcd,nullptr);
        assert(!storm.staged && visible==0 && writes==6 && reads==before+1);
        std::memset(live,0,sizeof(live));
        live[80*AW_VIDEO_STRIDE+5]=mismatch ? 0x33 : 0x22;
        assert(aw_storm_present(&storm,&pages,1,live,palette,&lcd,nullptr)!=mismatch);
        if (mismatch) {
            assert(!storm.ready && visible==0 && !slots[1].valid);
        } else {
            assert(visible==1 && writes==6 && gram[1][80*AW_VIDEO_WIDTH+10]==palette[2]);
            live[80*AW_VIDEO_STRIDE+6]=0x11;
            assert(aw_storm_present(&storm,&pages,2,live,palette,&lcd,nullptr));
            assert(visible==1 && writes==7 && last_lead && gram[1][80*AW_VIDEO_WIDTH+12]==palette[1]);
        }
    }

    data = prelude_fixture();
    assert(load(data.size()) && storm.prelude.available && !storm.prelude.idle_return.available);
    const auto prelude_end = data.size();
    data[3] = '4';
    uint8_t meta[AW_STORM_IDLE_RETURN_HEADER] = {};
    put32(meta, 0x99833f62u);
    put32(meta + 4, 1);
    meta[8] = 1;
    data.insert(data.end(), meta, meta + sizeof(meta));
    const uint8_t delta[] = {0, 0, 2, 1, 2, 0, 0x22, 0x33};
    data.insert(data.end(), delta, delta + sizeof(delta));
    seal(data);
    assert(load(data.size()) && storm.prelude.available && storm.prelude.idle_return.available);
    const auto &ret = storm.prelude.idle_return;
    assert(ret.hash == 0x99833f62u && ret.dirty_bands == 1 && ret.end == ret.first + 1);
    assets.capacity = storm.rects[ret.first].offset;
    assert(load(data.size()) && storm.prelude.available && !storm.prelude.idle_return.available);
    assets.capacity = sizeof(ram);
    assert(!load(data.size() - 1));
    auto invalid = data;
    put32(invalid.data() + prelude_end + 4, 1u << AW_VIDEO_BANDS);
    seal(invalid);
    assert(!aw_storm_load(&storm, &assets, storage_base - 1, scratch, invalid.size(), read_file, &invalid));

    const auto tail_start = data.size();
    data[3] = '5';
    uint8_t black[AW_STORM_BLACK_HEADER] = {};
    put32(black, 0xaad13b0au);
    black[4] = 0x33; // The first black entry in the synthetic palette.
    data.insert(data.end(), black, black + sizeof(black));
    const uint8_t tail_frame[] = {0, 0, 0, 0, 1, 0, 0, 1, 1, 1, 0, 0x22};
    for (unsigned i = 0; i < AW_STORM_TAIL_FRAMES; ++i)
        data.insert(data.end(), tail_frame, tail_frame + sizeof(tail_frame));
    seal(data);
    assert(load(data.size()) && storm.tail.available && storm.tail.black_pair == 0x33);
    assets.capacity = storm.rects[storm.tail.frames[0].first].offset;
    assert(load(data.size()) && storm.prelude.idle_return.available && !storm.tail.available);
    assets.capacity = sizeof(ram);
    assert(!load(data.size() - 1));
    data[tail_start + 4] = 0x34;
    seal(data);
    assert(!load(data.size()));
}
