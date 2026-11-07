"""Small read-only ELF32/ARM reader used to package our freestanding modules."""
import struct
from pathlib import Path
class ELF:
 def __init__(self,path):
  self.data=Path(path).read_bytes();e=struct.unpack_from('<16sHHIIIIIHHHHHH',self.data)
  assert e[0][:7]==b'\x7fELF\x01\x01\x01' and e[2]==40,'Expected ELF32 little-endian ARM'
  self.entry=e[4];self.sections=[];self.symbols={}
  for i in range(e[12]):self.sections.append(struct.unpack_from('<10I',self.data,e[6]+i*e[11]))
  for s in self.sections:
   if s[1]!=2:continue
   strings=self.section_data(self.sections[s[6]])
   for at in range(s[4],s[4]+s[5],s[9]):
    name,value,size,info,other,index=struct.unpack_from('<IIIBBH',self.data,at)
    end=strings.find(b'\0',name);label=strings[name:end].decode()
    if label:self.symbols[label]=dict(value=value,size=size,info=info,index=index)
  self.segments=[]
  for i in range(e[10]):
   typ,off,va,pa,fs,ms,flags,align=struct.unpack_from('<8I',self.data,e[5]+i*e[9])
   if typ==1:self.segments.append(dict(address=va,physical=pa,data=self.data[off:off+fs],memsz=ms,flags=flags))
 def section_data(self,s):return self.data[s[4]:s[4]+s[5]]
 def relocations(self):
  for s in self.sections:
   if s[1]!=9 or not(self.sections[s[7]][2]&2):continue
   for at in range(s[4],s[4]+s[5],s[9]):
    address,info=struct.unpack_from('<II',self.data,at);yield address,info&255
