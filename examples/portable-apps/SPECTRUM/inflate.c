#include "inflate.h"
#include <string.h>

/* RFC 1950/1951. A page is its own LZ77 history, so the decoder needs no
 * additional 32 KiB dictionary. Read the SD source in bounded chunks. */
typedef struct {
    const spectrum_source* source;
    uint32_t at,end;
    uint8_t input[512];
    unsigned cursor,available,bits,held;
    enum spectrum_error error;
} stream;

static unsigned take(stream* in,unsigned bits) {
    while(in->held<bits) {
        if(in->cursor==in->available) {
            if(in->at==in->end) {in->error=SPECTRUM_FORMAT;return 0;}
            const unsigned left=in->end-in->at;
            in->available=left<sizeof(in->input)?left:sizeof(in->input);
            if(!in->source->read(in->source->context,in->at,in->input,in->available)) {
                in->error=SPECTRUM_IO;return 0;
            }
            in->at+=in->available;in->cursor=0;
        }
        in->bits|=(unsigned)in->input[in->cursor++]<<in->held;in->held+=8;
    }
    const unsigned result=in->bits&((1u<<bits)-1);
    in->bits>>=bits;in->held-=bits;
    return result;
}

typedef struct { uint16_t count[16],symbols[288]; } huffman;

static bool make_tree(huffman* tree,const uint8_t* widths,unsigned n,bool complete) {
    memset(tree->count,0,sizeof(tree->count));
    for(unsigned s=0;s<n;++s) ++tree->count[widths[s]];
    unsigned codes=1;
    uint16_t offsets[16]={0};
    for(unsigned width=1;width<=15;++width) {
        codes<<=1;
        if(tree->count[width]>codes) return false;
        codes-=tree->count[width];
        if(width>1) offsets[width]=offsets[width-1]+tree->count[width-1];
    }
    if(codes && (complete || n-tree->count[0]!=tree->count[1])) return false;
    for(unsigned s=0;s<n;++s) if(widths[s]) tree->symbols[offsets[widths[s]]++]=(uint16_t)s;
    return true;
}

static unsigned symbol(stream* in,const huffman* tree) {
    unsigned code=0,first=0,index=0;
    for(unsigned n=1;n<=15;++n) {
        code|=take(in,1);
        const unsigned count=tree->count[n];
        if(in->error) break;
        if(code-first<count) return tree->symbols[index+code-first];
        index+=count;first=(first+count)<<1;code<<=1;
    }
    if(!in->error) in->error=SPECTRUM_FORMAT;
    return 0;
}

static bool trees(stream* in,unsigned type,huffman* lit,huffman* dist) {
    uint8_t lengths[320];
    if(type==1) {
        memset(lengths,8,144);memset(lengths+144,9,112);
        memset(lengths+256,7,24);memset(lengths+280,8,8);memset(lengths+288,5,32);
        return make_tree(lit,lengths,288,true) && make_tree(dist,lengths+288,32,true);
    }
    if(type!=2) return false;
    const unsigned nl=take(in,5)+257,nd=take(in,5)+1,nc=take(in,4)+4;
    if(nl>286 || in->error) return false;
    uint8_t width[19]={0};
    static const uint8_t order[]={16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15};
    for(unsigned i=0;i<nc;++i) width[order[i]]=(uint8_t)take(in,3);
    if(in->error || !make_tree(lit,width,19,true)) return false;
    for(unsigned i=0;i<nl+nd;) {
        const unsigned s=symbol(in,lit);
        if(in->error) return false;
        if(s<16) {lengths[i++]=(uint8_t)s;continue;}
        if(s==16 && !i) return false;
        const unsigned count=s==16?take(in,2)+3:s==17?take(in,3)+3:take(in,7)+11;
        if(in->error || count>nl+nd-i) return false;
        memset(lengths+i,s==16?lengths[i-1]:0,count);i+=count;
    }
    return lengths[256] && make_tree(lit,lengths,nl,false) && make_tree(dist,lengths+nl,nd,false);
}

static uint8_t* output_at(const spectrum_inflate_output* out,unsigned i) {
    return i<out->split?out->first+i:out->second+(i-out->split);
}
static bool compressed(stream* in,const huffman* literal,const huffman* distance,
                       const spectrum_inflate_output* out,unsigned* used) {
    unsigned at=*used;
    for(;;) {
        const unsigned sym=symbol(in,literal);
        if(in->error) return false;
        if(sym==256) {*used=at;return true;}
        if(sym<256) {
            if(at==out->limit) return false;
            *output_at(out,at++)=(uint8_t)sym;
            continue;
        }
        if(sym>285) return false;
        const unsigned l=sym-257;
        const unsigned le=l<8 || l==28?0:(l>>2)-1;
        const unsigned length=(l<8?3+l:l==28?258:3+((4+(l&3))<<le))+take(in,le);
        const unsigned d=symbol(in,distance);
        if(d>=30) return false;
        const unsigned de=d<4?0:(d>>1)-1;
        const unsigned offset=(d<4?d+1:1+((2+(d&1))<<de))+take(in,de);
        if(in->error || offset>at || length>out->limit-at) return false;
        for(unsigned n=0;n<length;++n,++at) *output_at(out,at)=*output_at(out,at-offset);
    }
}

enum spectrum_error spectrum_inflate(const spectrum_source* source,uint32_t offset,uint32_t bytes,
                                      const spectrum_inflate_output* out,unsigned* used) {
    if(!source || !source->read || offset>source->size || bytes>source->size-offset || bytes<6)
        return SPECTRUM_FORMAT;
    if(!out || !out->first || !used || out->split>out->limit ||
       (out->split!=out->limit && !out->second)) return SPECTRUM_UNSUPPORTED;
    stream in={.source=source,.at=offset,.end=offset+bytes};
    *used=0;
    const unsigned cm=take(&in,8),flg=take(&in,8);
    if((cm&15)!=8 || cm>>4>7 || ((cm<<8)|flg)%31 || (flg&32)) goto bad;
    unsigned final;
    do {
        final=take(&in,1);
        const unsigned type=take(&in,2);
        if(in.error) goto bad;
        if(type==0) {
            in.bits=0;in.held=0;
            const unsigned len=take(&in,16),inverse=take(&in,16);
            if((len^inverse)!=65535 || len>out->limit-*used) goto bad;
            for(unsigned i=0;i<len;++i) *output_at(out,(*used)++)=(uint8_t)take(&in,8);
        } else {
            huffman lit,dist;
            if(!trees(&in,type,&lit,&dist) || !compressed(&in,&lit,&dist,out,used)) goto bad;
        }
        if(in.error) goto bad;
    } while(!final);
    in.bits=0;in.held=0;
    uint32_t checksum=0;
    for(unsigned i=0;i<4;++i) checksum=(checksum<<8)|take(&in,8);
    if(in.error || in.at!=in.end || in.cursor!=in.available) goto bad;
    unsigned a=1,b=0;
    for(unsigned i=0;i<*used;++i) {
        a+=*output_at(out,i);if(a>=65521) a-=65521;
        b+=a;if(b>=65521) b-=65521;
    }
    if(((uint32_t)b<<16|a)==checksum) return SPECTRUM_OK;
bad:
    return in.error?in.error:SPECTRUM_FORMAT;
}
