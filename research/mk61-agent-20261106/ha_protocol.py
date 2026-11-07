"""Lossless HEX assembler, typed constant table and bounded suffix patches."""
from decimal import Decimal
import re

from full_isa_math import literal
from full_isa_protocol import OPERAND_OPCODES,linear_instructions

MAX_BODY=512
MAX_PROGRAM=105
NUMBER=re.compile(r'(?<![\w])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?![\w])')


def canonical(value):
    number=Decimal(str(value))
    if not number.is_finite():raise ValueError('Finite decimal required')
    if number==0:return '0'
    text=format(number,'f')
    return text.rstrip('0').rstrip('.')if'.'in text else text


def constants(text):
    text=re.sub(r'МК[\s\-‑–]?61','МК',text,flags=re.I).replace('−','-')
    values=['0','1','-1']
    for match in NUMBER.finditer(text):
        value=canonical(match.group())
        if value not in values:values.append(value)
    if len(values)>256:raise ValueError('Constant pool overflow')
    return values


def address(cell):
    if type(cell)is not int or not 0<=cell<105:raise ValueError('Address outside classic MK-61')
    return (cell//10)*16+cell%10


def unaddress(byte):
    cell=(byte//16)*10+byte%16
    if byte%16>9 or not 0<=cell<105:raise ValueError('Not a canonical BCD address')
    return cell


def bytes_text(body):return ' '.join(f'{x:02X}'for x in body)


def parse_bytes(text,*,empty=False):
    words=text.strip().split()
    if(not words and not empty)or len(words)>MAX_BODY or any(not re.fullmatch('[0-9A-Fa-f]{2}',x)for x in words):raise ValueError('Invalid HEX body')
    return [int(x,16)for x in words]


def assemble(body,pool,arm):
    if arm not in ['direct','asm']or not 1<=len(body)<=MAX_BODY:raise ValueError('Invalid body')
    if any(type(x)is not int or not 0<=x<=255 for x in body):raise ValueError('Expected byte values')
    if arm=='direct':
        if len(body)>MAX_PROGRAM:raise ValueError('Program longer than 105 cells')
        return list(body)
    output=[];labels={};relocations=[];at=0
    while at<len(body):
        op=body[at];at+=1
        if op!=0xFF:output.append(op)
        else:
            if at>=len(body):raise ValueError('Incomplete escape')
            directive=body[at];at+=1
            if directive==0:output.append(0xFF)
            else:
                if at>=len(body):raise ValueError('Missing directive argument')
                argument=body[at];at+=1
                if directive==1:
                    if argument>=len(pool):raise ValueError('Unknown constant')
                    output.extend(literal(pool[argument]))
                elif directive==2:
                    if argument in labels:raise ValueError('Duplicate label')
                    labels[argument]=len(output)
                elif directive==3:relocations.append((len(output),argument));output.append(0)
                else:raise ValueError('Unknown assembler directive')
        if len(output)>MAX_PROGRAM:raise ValueError('Expanded program longer than 105 cells')
    for at,label in relocations:
        if label not in labels:raise ValueError('Undefined label')
        output[at]=address(labels[label])
    if not output:raise ValueError('Empty program')
    return output


def encode(code,pool,arm):
    """Recognize exact existing literal sequences and canonical jump addresses.

    The transform never chooses an operation or synthesizes an algorithm.
    Unrecognized bytes, including all undocumented opcodes, stay raw.
    """
    if arm=='direct':return list(code)
    try:instructions=linear_instructions(code)
    except ValueError:instructions=[]
    starts={x['pc']for x in instructions};destinations=set();operands={}
    for row in instructions:
        if row['opcode']not in OPERAND_OPCODES:continue
        try:cell=unaddress(row['operand'])
        except ValueError:continue
        if cell in starts:destinations.add(cell);operands[row['pc']+1]=cell
    labels={cell:i for i,cell in enumerate(sorted(destinations))}
    expansions={}
    for i,value in enumerate(pool):
        try:raw=literal(value)
        except (ValueError,ArithmeticError):continue
        expansions.setdefault(tuple(raw),i)
    candidates=sorted(expansions,key=len,reverse=True);body=[];at=0
    while at<len(code):
        if at in labels:body.extend([0xFF,2,labels[at]])
        if at in operands:body.extend([0xFF,3,labels[operands[at]]]);at+=1;continue
        found=False
        if at in starts and code[at:at+2]==[0x0E,0x0D]:
            for raw in candidates:
                end=at+len(raw)
                if tuple(code[at:end])==raw and not any(at<x<end for x in destinations):
                    # A longer digit sequence is not the shorter constant.
                    if end<len(code)and code[end]<=0x0A:continue
                    body.extend([0xFF,1,expansions[raw]]);at=end;found=True;break
        if found:continue
        body.extend([0xFF,0]if code[at]==0xFF else[code[at]]);at+=1
    if assemble(body,pool,'asm')!=list(code):raise AssertionError('Assembler transform changed bytes')
    return body


def write_call(body):return '<write>'+bytes_text(body)+'</write><run/>'


def suffix_patch(current,wanted):
    at=0
    while at<min(len(current),len(wanted))and current[at]==wanted[at]:at+=1
    return [at>>8,at&255,*wanted[at:]]


def patch_call(current,wanted):return '<patch>'+bytes_text(suffix_patch(current,wanted))+'</patch><run/>'


def parse_call(reply,current=None):
    reply=reply.strip()
    found=re.fullmatch(r'<write>(.*?)</write>\s*<run/>',reply,re.S)
    if found:return 'write',parse_bytes(found.group(1))
    found=re.fullmatch(r'<patch>(.*?)</patch>\s*<run/>',reply,re.S)
    if found:
        values=parse_bytes(found.group(1));at=values[0]*256+values[1]if len(values)>=2 else-1
        if current is None or not 0<=at<=len(current):raise ValueError('Invalid patch position')
        body=list(current[:at])+values[2:]
        if not 1<=len(body)<=MAX_BODY:raise ValueError('Invalid patched body size')
        return 'patch',body
    if reply=='<trace/>':return 'trace',None
    if reply=='<done/>':return 'done',None
    found=re.fullmatch(r'<run>([0-9A-Fa-f]{2})</run>',reply)
    if found:return 'run',int(found.group(1),16)
    raise ValueError('Invalid tool call')


def pool_text(pool):return ';'.join(f'{i:02X}={x}'for i,x in enumerate(pool))


def prompt(task,arm,*,current=None,observation=None,case=0,notes=''):
    pool=task.get('constants')or constants(task['task'])
    mode='обычный HEX'if arm=='direct'else'HEX+макросы FF00=байт FF, FF01kk=константа kk, FF02ll=метка ll, FF03ll=адрес метки ll'
    text=(f'МК-61: {task["angle"]}; 105 ячеек; R0–RE, стек X/Y/Z/T/X1. {mode}.\n'
      'Вызовы: <write>HEX</write><run/>, <patch>HH LL новый суффикс</patch><run/>, <run>номер теста HEX</run>, <trace/>, <done/>. '
      'Позиция суффикса HH LL — два байта индекса в текущем HEX. Эмулятор сообщает фактическое состояние.\n'
      'Константы: '+pool_text(pool)+'\nЗадача: '+task['task'].strip()+'\n')
    if notes:text+='Заметки: '+notes+'\n'
    if current is not None:
        text+='Текущий HEX (индекс в начале каждой строки):\n'
        text+='\n'.join(f'{i:04X}: '+bytes_text(current[i:i+8])for i in range(0,len(current),8))+'\n'
    if observation is not None:text+='Эмулятор: '+observation+'\n'
    return text+'Ассистент: '

