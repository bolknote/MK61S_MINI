"""Full MK-61 program interface. No arithmetic AST limits the instruction set."""
import re

REGISTERS=tuple('R'+format(i,'X')for i in range(15))
ANGLE_MODES={'RAD':'радианы','DEG':'градусы','GRAD':'грады'}
OPERAND_OPCODES=frozenset([0x51,0x53,0x57,0x58,0x59,0x5A,0x5B,0x5C,0x5D,0x5E])

SYSTEM=('Ты составляешь программы для обычного МК-61: до 105 ячеек, регистры R0–RE, стек X/Y/Z/T/X1. '
        'Доступен полный набор команд МК-61. Числовые константы из условия вводи самой программой; '
        'входы из явно названных регистров читай из этих регистров. Соблюдай указанный режим углов. '
        'Предскажи программу целиком: <write>байты HEX через пробел</write><run/>. '
        'Для диагностики текущей программы можно вызвать <trace/>. '
        'После результата эмулятора исправь программу либо заверши ответом <done/>.\n')


def hex_code(code):
    if not isinstance(code,(list,tuple))or not 1<=len(code)<=105:raise ValueError('Program length must be 1..105')
    if any(type(x)is not int or not 0<=x<=255 for x in code):raise ValueError('Expected bytes 00..FF')
    return ' '.join(f'{x:02X}'for x in code)


def answer(code):return '<write>'+hex_code(code)+'</write><run/>'


def prompt(text,*,angle='RAD',initial_code=None,observation=None):
    if angle not in ANGLE_MODES:raise ValueError('Explicit angle mode required')
    result=SYSTEM+'Режим углов: '+angle+' ('+ANGLE_MODES[angle]+').\nЗадача: '+text.strip()+'\n'
    if initial_code is not None:result+='Текущий код: '+hex_code(initial_code)+'\n'
    if observation is not None:result+='Эмулятор: '+observation+'\n'
    return result+'Ассистент: '


def decode(reply):
    found=re.fullmatch(r'\s*<write>(.*?)</write>\s*<run/>\s*',reply,flags=re.S)
    if not found:raise ValueError('Expected a complete HEX program call')
    tokens=found.group(1).strip().split()
    if not tokens or any(not re.fullmatch('[0-9A-Fa-f]{2}',x)for x in tokens):raise ValueError('Invalid HEX')
    code=[int(x,16)for x in tokens];hex_code(code);return code


def linear_instructions(code):
    """Instruction starts, not address bytes. Overlays need dynamic traces."""
    hex_code(code);at=0;result=[]
    while at<len(code):
        opcode=code[at]
        if opcode in OPERAND_OPCODES and at+1>=len(code):raise ValueError('Missing jump address')
        result.append({'pc':at,'opcode':opcode,'operand':code[at+1]if opcode in OPERAND_OPCODES else None})
        at+=2 if opcode in OPERAND_OPCODES else 1
    return result
