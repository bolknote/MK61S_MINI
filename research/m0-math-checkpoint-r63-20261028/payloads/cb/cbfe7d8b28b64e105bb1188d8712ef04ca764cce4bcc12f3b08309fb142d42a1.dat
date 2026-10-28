#ifndef MK61_C9_INODE_WIRE_HPP
#define MK61_C9_INODE_WIRE_HPP
#include "rust_types.h"
#include <stddef.h>
#include <string.h>

namespace c9_inode_wire {
struct Inode {
  u32 address;
  u16 data_len;
  u16 record_len;
  u16 parent_id;
  u16 first_child;
  u16 next_sibling;
  u16 prev_sibling;
  u16 name_hash;
  u8 kind_type;
  u8 flags;
  u16 exported_size;
  u32 fat_address;
};
static constexpr usize SIZE = 26;
// The naturally aligned RAM object has only two padding bytes, immediately
// before fat_address. Neither padding byte belongs to the physical C9 inode.
static_assert(sizeof(Inode) == 28 && offsetof(Inode,address) == 0 &&
  offsetof(Inode,data_len) == 4 && offsetof(Inode,record_len) == 6 &&
  offsetof(Inode,parent_id) == 8 && offsetof(Inode,first_child) == 10 &&
  offsetof(Inode,next_sibling) == 12 && offsetof(Inode,prev_sibling) == 14 &&
  offsetof(Inode,name_hash) == 16 && offsetof(Inode,kind_type) == 18 &&
  offsetof(Inode,flags) == 19 && offsetof(Inode,exported_size) == 20 &&
  offsetof(Inode,fat_address) == 24, "C9 RAM prefix layout changed");
inline u16 read16(const u8* p) { return (u16)(p[0] | (u16)p[1]<<8); }
inline u32 read32(const u8* p) { return (u32)read16(p) | (u32)read16(p+2)<<16; }
inline void write16(u8* p,u16 v) { p[0]=(u8)v; p[1]=(u8)(v>>8); }
inline void write32(u8* p,u32 v) { write16(p,(u16)v); write16(p+2,(u16)(v>>16)); }
inline void encode(const Inode& v,u8* out) {
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__ && !defined(MK61_C9_SCALAR_CODEC)
  memcpy(out,&v,22);
#else
  write32(out,v.address); write16(out+4,v.data_len);write16(out+6,v.record_len);
  write16(out+8,v.parent_id);write16(out+10,v.first_child);
  write16(out+12,v.next_sibling);write16(out+14,v.prev_sibling);
  write16(out+16,v.name_hash);out[18]=v.kind_type;out[19]=v.flags;
  write16(out+20,v.exported_size);
#endif
  write32(out+22,v.fat_address);
}
inline Inode decode(const u8* data) {
  Inode v;
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__ && !defined(MK61_C9_SCALAR_CODEC)
  memcpy(&v,data,22);
#else
  v.address=read32(data);v.data_len=read16(data+4);v.record_len=read16(data+6);
  v.parent_id=read16(data+8);v.first_child=read16(data+10);
  v.next_sibling=read16(data+12);v.prev_sibling=read16(data+14);
  v.name_hash=read16(data+16);v.kind_type=data[18];v.flags=data[19];
  v.exported_size=read16(data+20);
#endif
  v.fat_address=read32(data+22);
  return v;
}
}
#endif
