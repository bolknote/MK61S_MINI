#if defined(MK61_BUILD_VM_FILE_CACHE_MODULE) && defined(MK61_LINKED_VM_POC) && MK61_LINKED_VM_POC
#include "language_linked_program.hpp"

namespace language_vm { namespace linked {
uint32_t load(LoadRequest* r,void* context,LocateFragment locate) {
  if(!r || r->size!=sizeof(*r) || r->magic!=LOAD_MAGIC || !locate ||
     !r->storage || !r->members || !r->program || !r->capacity ||
     r->input.bytes || !r->input.paged.read || !r->input.epoch || !r->poll)return 0;
  *r->program={};*r->storage={};r->error=Error::IO;
  auto& s=*r->storage;
  s.revision=r->input.epoch(r->input.epoch_context);
  auto current=[&](){return s.revision==r->input.epoch(r->input.epoch_context);};
  for(unsigned i=0;i<MAX_FRAGMENTS;++i) {
    char name[]="LVP00.bin";name[3]=char('0'+i/10);name[4]=char('0'+i%10);
    Fragment file={};
    const bool found=locate(context,r->directory,name,file);
    if(!r->poll(r->input.paged.context) || !current())return 1;
    if(!found)break;
    if(!file.size || file.size>FRAGMENT_BYTES || file.id==0xFFFF) {
      r->error=Error::INVALID_IMAGE;return 1;
    }
    s.files[i]=file.id;s.size+=file.size;
    if(file.size<FRAGMENT_BYTES)break;
  }
  if(s.size<HEADER_BYTES)return 1;
  Input input=r->input;input.size=input.paged.size=s.size;
  flash::IO scratch{};scratch.context=input.paged.context;scratch.service=r->poll;
  // Accepted members fit the verifier's existing fixed boundary bitmap.
  // The common verifier still checks every opcode, target and image CRC.
  scratch.read=[](void*,flash::Space,uint32_t,uint8_t*,uint16_t){return false;};
  scratch.write=[](void*,flash::Space,uint32_t,const uint8_t*,uint16_t){return false;};
  scratch.truncate=[](void*,flash::Space,uint32_t){return false;};
  Program checked;
  r->error=inspect(input,r->members,r->capacity,checked,scratch);
  if(r->error!=Error::NONE)return 1;
  for(unsigned i=0;i<checked.count;++i)if(!r->members[i].validated.wide ||
      r->members[i].validated.size>8192 || r->members[i].source_id>=4096 ||
      r->members[i].validated.flags) {
    r->error=Error::INVALID_IMAGE;return 1;
  }
  if(!current()){r->error=Error::IO;return 1;}
  *r->program=checked;return 1;
}
}}
#endif
