"""Extract only the established transport/file/statistics closure, with stdlib imports."""
import ast
import hashlib
import json
from pathlib import Path
ROOT=Path.cwd();WORK=Path(__file__).resolve().parent
origins=[];pieces=[]
def node(path,name,parent=None):
    file=ROOT/path;tree=ast.parse(file.read_text())
    if parent:tree=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==parent)
    value=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
    origins.append(dict(path=path,name=(parent+'.' if parent else '')+name,
        source_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
        ast_sha256=hashlib.sha256(ast.dump(value,include_attributes=False).encode()).hexdigest()))
    return value
for name in ['cobs_encode','cobs_decode','packbits']:
    pieces.append(ast.unparse(node('tests/hil_portable_apps.py',name)))
pieces.append(ast.unparse(node('tests/hil_rtc_alarm.py','Port')))
screen=ast.ClassDef(name='ScreenPort',bases=[ast.Name(id='Port',ctx=ast.Load())],keywords=[],
    body=[node('tests/hil_portable_apps.py',name,'ScreenPort') for name in ['__init__','send','receive_packet','pump']],decorator_list=[])
pieces.append(ast.unparse(ast.fix_missing_locations(screen)))
math=ast.ClassDef(name='MathPort',bases=[ast.Name(id='ScreenPort',ctx=ast.Load())],keywords=[],
    body=[node('tests/hil_m0_math_compare.py','command','MathPort'),node('tests/hil_picocalc_apps.py','status','AppsPort')],decorator_list=[])
pieces.append(ast.unparse(ast.fix_missing_locations(math)))
for path,names in [('tests/hil_usb_disk_transaction.py',['posix_cksum','require_file_contents']),
                   ('tests/hil_c5_stack.py',['read_file','write_file']),
                   ('tests/hil_rtc_alarm.py',['canonical_state_reply']),
                   ('tests/hil_m0_math_compare.py',['ordered','order_balanced','decode'])]:
    for name in names:pieces.append(ast.unparse(node(path,name)))
prefix='"""Frozen established project methods; stdlib only. No import-time device access."""\nimport binascii\nimport fcntl\nimport hashlib\nimport os\nimport re\nimport select\nimport statistics\nimport struct\nimport termios\nimport time\nPROMPT=re.compile(rb"(?:^|[\\r\\n])[^\\r\\n]*>\\s*$")\n'
target=WORK/'frozen_helpers.py';target.write_text(prefix+'\n\n'.join(pieces)+'\n')
tree=ast.parse(target.read_text())
allowed={'binascii','fcntl','hashlib','os','re','select','statistics','struct','termios','time'}
assert all(isinstance(n,ast.Import) and all(a.name in allowed for a in n.names) for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom)))
record=dict(status='PASS_FROZEN_PROJECT_METHOD_AST_EXTRACTION_STDLIB_ONLY',file=str(target),
    sha256=hashlib.sha256(target.read_bytes()).hexdigest(),methods=origins,
    source_changes='Only class composition/bases: established Port+four ScreenPort methods+MathPort.command+AppsPort.status. Every extracted method/function body AST is unchanged. Keyboard/UI command methods and their project imports are excluded.')
(WORK/'helper-proof.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',len(origins),'established project function/method ASTs frozen; stdlib-only closure.')
