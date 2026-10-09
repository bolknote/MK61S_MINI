#ifndef MK61_FOCAL_HOST_FIXTURE_HPP
#define MK61_FOCAL_HOST_FIXTURE_HPP
#include <stdint.h>
#include <stdio.h>
#include <string.h>
namespace focal_host_fixture {
inline bool russian=false, write_ok=true;
inline const char* refused_remove=nullptr;
inline char last_write[1537]={};
struct File {bool used;uint16_t id;char name[32],source[1537];};
inline File files[8]={};
inline void reset() {russian=false;write_ok=true;refused_remove=nullptr;last_write[0]=0;memset(files,0,sizeof(files));}
inline bool exists(const char* name) {for(const auto& f:files)if(f.used && !strcmp(f.name,name))return true;return false;}
inline const char* content(const char* name) {for(const auto& f:files)if(f.used && !strcmp(f.name,name))return f.source;return nullptr;}
inline bool write(uint16_t,uint16_t preferred,const char* name,const char* source,uint16_t length,uint16_t& saved) {
 if(!write_ok || !name || strlen(name)>=32 || length>=1537)return false;
 File* file=nullptr;
 for(auto& f:files)if(f.used && (f.id==preferred || !strcmp(f.name,name))){file=&f;break;}
 if(!file)for(auto& f:files)if(!f.used){file=&f;break;}
 if(!file)return false;
 file->used=true;file->id=uint16_t(file-files+1);strcpy(file->name,name);
 memcpy(file->source,source,length);file->source[length]=0;strcpy(last_write,file->source);saved=file->id;return true;
}
inline bool remove(uint16_t id,const char* name) {
 if(refused_remove && name && !strcmp(refused_remove,name))return false;
 for(auto& f:files)if(f.used && ((id!=0xFFFF && f.id==id) || (name && !strcmp(f.name,name)))){f.used=false;return true;}
 return false;
}
struct SerialLog {
 char output[8192]={};unsigned used=0;
 void clear(){used=0;output[0]=0;}
 void print(const char* text){if(!text)return;unsigned n=(unsigned)strlen(text);if(n>sizeof(output)-used-1)n=sizeof(output)-used-1;memcpy(output+used,text,n);used+=n;output[used]=0;}
 void print(char c){char s[2]={c,0};print(s);}
 void print(unsigned value){char s[32];snprintf(s,sizeof(s),"%u",value);print(s);}
 void print(int value){char s[32];snprintf(s,sizeof(s),"%d",value);print(s);}
 void print(double value,int digits=8){char s[48];snprintf(s,sizeof(s),"%.*g",digits,value);print(s);}
 void println(const char* text=""){print(text);print("\n");}
 void flush(){}
};
inline SerialLog serial;
}
#endif
