#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#define RCC_AHBENR_CRCEN 0x40u
#define CRC_CR_RESET 1u
static uint32_t clock_bits=0,irq_mask=0,accumulator=0,words=0,resets=0,reads=0;
static uint32_t __get_PRIMASK(){return irq_mask;}
static void __disable_irq(){irq_mask=1;}
static void __set_PRIMASK(uint32_t mask){irq_mask=mask;}
static uint32_t __RBIT(uint32_t value){
    uint32_t reversed=0;
    for(unsigned i=0;i<32;++i){reversed=(reversed<<1)|(value&1);value>>=1;}
    return reversed;
}
struct ClockRegister {
    operator uint32_t() const{return clock_bits;}
    void operator|=(uint32_t bits){assert(irq_mask);clock_bits|=bits;}
    void operator&=(uint32_t bits){assert(irq_mask);clock_bits&=bits;}
};
struct CrcDataRegister {
    void operator=(uint32_t value){
        assert(irq_mask && (clock_bits&RCC_AHBENR_CRCEN));++words;
        accumulator^=value;
        // Independent RM0008 MSB-first peripheral model; no byte/table
        // implementation or reflected-wire polynomial is used here.
        for(unsigned i=0;i<32;++i)
            accumulator=(accumulator<<1)^((accumulator&0x80000000u)?0x04c11db7u:0u);
    }
    operator uint32_t() const{assert(irq_mask && (clock_bits&RCC_AHBENR_CRCEN));++reads;return accumulator;}
};
struct CrcControlRegister {
    void operator=(uint32_t value){
        assert(irq_mask && (clock_bits&RCC_AHBENR_CRCEN) && value==CRC_CR_RESET);
        accumulator=~0u;++resets;
    }
};
static struct {ClockRegister AHBENR;} modeled_rcc;
static struct {CrcDataRegister DR;CrcControlRegister CR;} modeled_crc;
#define RCC (&modeled_rcc)
#define CRC (&modeled_crc)
#include "bios/stm3_crc_f103.h"

static uint32_t reference(const uint8_t* p,size_t count){
    uint32_t result=~0u;
    for(size_t i=0;i<count;++i){
        result^=p[i];
        for(unsigned j=0;j<8;++j)result=(result>>1)^((result&1)?0xedb88320u:0u);
    }
    return ~result;
}
int main(){
    std::array<uint8_t,6468> data{};uint32_t random=1234567;
    for(auto& byte:data){random^=random<<13;random^=random>>17;random^=random<<5;byte=uint8_t(random);}
    for(unsigned prior_irq:{0u,1u})for(unsigned prior_clock:{0x5u,0x45u})
      for(unsigned offset=0;offset<4;++offset)for(unsigned count=0;count<=6464;++count){
        clock_bits=prior_clock;irq_mask=prior_irq;words=resets=reads=0;
        const auto actual=stm3_f103_crc32(data.data()+offset,count);
        assert(actual==reference(data.data()+offset,count));
        assert(clock_bits==prior_clock && irq_mask==prior_irq && words==count/4);
        assert(reads==(count>=4) && resets==(count>=4));
      }
    assert(stm3_f103_crc32(nullptr,0)==0);
    assert(stm3_f103_crc32("123456789",9)==0xcbf43926u);
    puts("F103 hardware CRC: 103440 independent vectors, all alignments/tails, no padding, exact IEEE CRC, clock/IRQ restoration PASS");
}
