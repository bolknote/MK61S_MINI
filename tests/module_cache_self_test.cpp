#include "rust_types.h"
#include <cassert>
#include <cstdio>
enum class RuntimeStatus {OK,DISABLED,UNAVAILABLE,INVALID_MODULE,IO_ERROR};
enum class Kind {APPLICATION,LANGUAGE_VM,LANGUAGE_INPUT};
namespace program_store {
constexpr u16 INVALID_ID=0xFFFF;
struct Entry {u16 id;};
bool mounted=true;
u32 revision=1;
unsigned queries;
bool missing;
bool ready(){return mounted;}
u32 media_revision(){return revision;}
bool entry_by_id(u16 id,Entry& out){++queries;out.id=id;return !missing;}
}
struct Cache {bool live=false;bool ok(){return live;}} g_app_cache;
static bool flash_is_ok=true,available=true,initialize_mutates;
static Kind g_active_kind=Kind::APPLICATION;
static void* g_active_entry;
static u16 g_active_file_id=program_store::INVALID_ID;
static u32 g_active_revision;
static unsigned activations;
static RuntimeStatus activation_error=RuntimeStatus::OK;
static bool enabled(Kind){return available;}
static bool find_system_app(Kind kind,program_store::Entry& out){
  ++program_store::queries;out.id=kind==Kind::LANGUAGE_VM?10:11;return !program_store::missing;
}
static RuntimeStatus load_entry(Kind kind,const program_store::Entry& entry){
  ++activations;
  if(activation_error!=RuntimeStatus::OK)return activation_error;
  g_active_kind=kind;g_active_file_id=entry.id;g_app_cache.live=true;
  g_active_entry=&g_app_cache;
  if(initialize_mutates)++program_store::revision;
  return RuntimeStatus::OK;
}
#include "module_cache.inc"
int main(){
  assert(load(Kind::LANGUAGE_VM)==RuntimeStatus::OK && program_store::queries==1);
  for(unsigned i=0;i<20;++i)assert(load(Kind::LANGUAGE_VM)==RuntimeStatus::OK);
  assert(program_store::queries==1 && activations==1);
  ++program_store::revision;
  assert(load(Kind::LANGUAGE_VM)==RuntimeStatus::OK && program_store::queries==2);
  available=false;assert(load(Kind::LANGUAGE_VM)==RuntimeStatus::DISABLED);available=true;
  program_store::mounted=false;assert(load(Kind::LANGUAGE_VM)==RuntimeStatus::UNAVAILABLE);
  program_store::mounted=true;flash_is_ok=false;
  assert(load(Kind::LANGUAGE_VM)==RuntimeStatus::UNAVAILABLE);flash_is_ok=true;
  g_app_cache.live=false;assert(load(Kind::LANGUAGE_VM)==RuntimeStatus::OK && program_store::queries==3);
  g_active_entry=nullptr;assert(load(Kind::LANGUAGE_VM)==RuntimeStatus::OK && program_store::queries==4);
  assert(load(Kind::APPLICATION,42)==RuntimeStatus::OK);
  const auto queries=program_store::queries;
  assert(load(Kind::APPLICATION,42)==RuntimeStatus::OK && program_store::queries==queries);
  assert(load(Kind::APPLICATION,43)==RuntimeStatus::OK && program_store::queries==queries+1);
  assert(load(Kind::APPLICATION)==RuntimeStatus::INVALID_MODULE);
  ++program_store::revision;program_store::missing=true;
  assert(load(Kind::APPLICATION,43)==RuntimeStatus::INVALID_MODULE);
  program_store::missing=false;activation_error=RuntimeStatus::IO_ERROR;
  assert(load(Kind::APPLICATION,43)==RuntimeStatus::IO_ERROR);
  activation_error=RuntimeStatus::OK;initialize_mutates=true;
  assert(load(Kind::LANGUAGE_INPUT)==RuntimeStatus::OK);
  const auto before=program_store::queries;
  initialize_mutates=false;assert(load(Kind::LANGUAGE_INPUT)==RuntimeStatus::OK);
  assert(program_store::queries==before+1);
  puts("APP cache: unchanged revision, eviction, missing/changed files, mount and failed activation PASS");
}
