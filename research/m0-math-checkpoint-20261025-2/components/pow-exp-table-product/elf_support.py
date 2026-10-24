"""Small read-only ELF32 helpers for the private table-product experiment."""
import hashlib, struct


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_elf(path):
    data = path.read_bytes()
    assert data[:7] == b'\x7fELF\x01\x01\x01'
    off = struct.unpack_from('<I', data, 32)[0]
    size,count,strings_index = struct.unpack_from('<HHH', data, 46)
    headers = [struct.unpack_from('<10I',data,off+i*size) for i in range(count)]
    contents = lambda s:data[s[4]:s[4]+s[5]]
    names = contents(headers[strings_index])
    string = lambda b,n:b[n:b.index(b'\0',n)].decode()
    sections = [dict(name=string(names,s[0]),type=s[1],flags=s[2],address=s[3],
                     size=s[5],align=s[8],data=contents(s)) for s in headers]
    symbols = []
    for s in headers:
        if s[1] != 2:continue
        strings = contents(headers[s[6]])
        for p in range(s[4],s[4]+s[5],s[9]):
            name,value,length,info,other,index = struct.unpack_from('<IIIBBH',data,p)
            symbols.append(dict(name=string(strings,name),value=value,size=length,
                                type=info&15,bind=info>>4,other=other,section=index))
    return sections,symbols


def section_bases(object_path, resident_path):
    sections,symbols = read_elf(object_path)
    rs,rr = read_elf(resident_path)
    residents = {}
    for row in rr:
        if row['section'] and row['section'] < len(rs):
            residents.setdefault(row['name'],[]).append(row)
    bases = {}
    witnesses = {}
    for row in symbols:
        index = row['section']
        if row['type'] not in (1,2) or not (0<index<len(sections)):continue
        if not sections[index]['flags']&2:continue
        for old in residents.get(row['name'],[]):
            if row['size'] != old['size'] or row['type'] != old['type']:continue
            clear = ~1 if row['type']==2 else -1
            base = (old['value']&clear)-(row['value']&clear)
            bases.setdefault(index,set()).add(base)
            witnesses.setdefault(index,[]).append(dict(name=row['name'],base=base,size=row['size']))
    return sections,bases,witnesses
