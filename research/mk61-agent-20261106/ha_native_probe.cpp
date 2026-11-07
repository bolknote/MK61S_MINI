#include "ha_native.hpp"
extern "C" {
unsigned ha_state_bytes(){return sizeof(mk61ha::State);}
unsigned ha_workspace_bytes(){return sizeof(mk61ha::Workspace);}
int ha_pool(const char *task,char *out,unsigned capacity,unsigned *count){
  mk61ha::Pool pool;int result=mk61ha::extract_pool(task,pool);if(result)return result;
  if(capacity<pool.count*mk61ha::NumberMax)return -10;
  std::memcpy(out,pool.values,pool.count*mk61ha::NumberMax);*count=pool.count;return 0;
}
int ha_assemble(const unsigned char *body,unsigned size,const char *const *values,unsigned count,int macros,unsigned char *out,unsigned *used){
  if(count>mk61ha::PoolMax)return -10;mk61ha::Pool pool;pool.count=count;
  for(unsigned i=0;i<count;++i){if(std::strlen(values[i])>=mk61ha::NumberMax)return -11;std::strcpy(pool.values[i],values[i]);}
  mk61ha::Workspace work;return mk61ha::assemble(body,size,pool,macros!=0,out,*used,work);
}
int ha_patch(unsigned char *body,unsigned *size,const unsigned char *values,unsigned count){return mk61ha::patch(body,*size,values,count);}
int ha_reply(const char *reply,unsigned char *body,unsigned *size,const char *const *values,unsigned count,int macros,int *action,unsigned *test,unsigned char *program,unsigned *used){
  if(*size>mk61ha::BodyMax||count>mk61ha::PoolMax)return -10;mk61ha::State state;state.size=*size;std::memcpy(state.body,body,*size);state.pool.count=count;
  for(unsigned i=0;i<count;++i){if(std::strlen(values[i])>=mk61ha::NumberMax)return -11;std::strcpy(state.pool.values[i],values[i]);}
  mk61ha::Workspace work;mk61ha::Action kind;int result=mk61ha::parse_reply(reply,state,macros!=0,kind,*test,program,*used,work);
  if(result)return result;std::memcpy(body,state.body,state.size);*size=state.size;*action=int(kind);return 0;
}
}
