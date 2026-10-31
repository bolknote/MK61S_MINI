"""Small owned benchmark namespace, independent of the full Pico SD audit.

The caller supplies fresh exact-helper OP1 listings, including hidden entries.
Only the three small benchmark files may be read through public fsget. These
snapshots prove no claim about other user files: complete initial bytes and
final independent all-SD verification remain mandatory in the outer session.
"""
import re
from session import Files,Hold


class Namespace:
    def __init__(self,directory,listing,read):
        if not re.fullmatch('/MCHR-[A-Z0-9-]{1,24}',directory):raise Hold('Unreserved Pico benchmark namespace')
        self.directory=directory;self.listing=listing;self.read=read

    @staticmethod
    def entries(rows,parent):
        rows=list(rows);seen=set()
        for row in rows:
            path=row['path'];prefix=parent.rstrip('/')+'/'
            name=path[len(prefix):] if path.startswith(prefix) else ''
            if (not name or '/' in name or name in ('.','..') or '"' in name or
                any(ord(c)<32 or ord(c)==127 for c in name) or path.casefold() in seen):
                raise Hold('Ambiguous or malformed Pico helper inventory')
            seen.add(path.casefold())
            if row['kind'] not in ('file','directory'):raise Hold('Unknown Pico inventory node type')
        return rows

    def scan(self):
        roots=self.entries(self.listing('/'),'/')
        found=[r for r in roots if r['path'].casefold()==self.directory.casefold()]
        if not found:return Files({},set())
        root=found[0]
        if (root['path']!=self.directory or root['kind']!='directory' or
            not root['fat_attributes']&0x10 or root['fat_attributes']&~0x30):
            raise Hold('Pico reserved namespace changed name/type/attributes')
        files={}
        for row in self.entries(self.listing(self.directory),self.directory):
            path=row['path'];name=path.rsplit('/',1)[-1].casefold()
            if (row['kind']!='file' or name not in ('chrben.app','input.bin','result.bin') or
                row['fat_attributes']&~0x20 or not isinstance(row['bytes'],int) or
                not 0<=row['bytes']<=65534):
                raise Hold('Unknown/changed Pico namespace child preserved: '+path)
            data=self.read(path)
            if len(data)!=row['bytes']:raise Hold('Pico namespace file length differs')
            files[path]=data
        return Files(files,{self.directory}).validate()
