"""Fixture compiler for scientific expressions, never a model-output restriction."""
import math
from decimal import Decimal

UNARY={'neg':0x0B,'pow10':0x15,'exp':0x16,'log10':0x17,'ln':0x18,'asin':0x19,'acos':0x1A,'atan':0x1B,
 'sin':0x1C,'cos':0x1D,'tan':0x1E,'sqrt':0x21,'square':0x22,'reciprocal':0x23,'abs':0x31,'sign':0x32,'int':0x34,'frac':0x35}
BINARY={'+':0x10,'-':0x11,'*':0x12,'/':0x13,'pow':0x24}
WORDS={'neg':'противоположное число','pow10':'десять в указанной степени','exp':'экспоненту','log10':'десятичный логарифм',
 'ln':'натуральный логарифм','asin':'арксинус','acos':'арккосинус','atan':'арктангенс','sin':'синус','cos':'косинус','tan':'тангенс',
 'sqrt':'квадратный корень','square':'квадрат','reciprocal':'обратное число','abs':'модуль','sign':'знак по правилу К ЗН',
 'int':'целую часть с отсечением к нулю','frac':'дробную часть с исходным знаком'}


def literal(value):
    value=Decimal(str(value));text=format(abs(value),'f').rstrip('0').rstrip('.')if value%1 else format(abs(value),'f')
    if not text or len(text)>18:raise ValueError('Literal out of bounded fixture range')
    code=[0x0E,0x0D]+[0x0A if c=='.'else int(c)for c in text]
    if value<0:code.append(0x0B)
    return code


def compile_expr(expr):
    if isinstance(expr,str):return [0x60+int(expr[1:],16)]
    if isinstance(expr,dict):return [0x20]if 'pi'in expr else literal(expr['constant'])
    op,*args=expr
    if op in UNARY:return compile_expr(args[0])+[UNARY[op]]
    if op=='pow':
        # MK-61 x^y retains Y. Clear the now-unused exponent below the result
        # so enclosing numeric expressions have the normal binary stack effect.
        return compile_expr(args[1])+compile_expr(args[0])+[0x24,0x14,0x0D,0x10]
    return compile_expr(args[0])+compile_expr(args[1])+[BINARY[op]]


def value(expr,values,angle):
    if isinstance(expr,str):return float(values[expr])
    if isinstance(expr,dict):return math.pi if 'pi'in expr else float(expr['constant'])
    op,*args=expr;xs=[value(x,values,angle)for x in args];a=xs[0]
    to_rad={'RAD':1.,'DEG':math.pi/180,'GRAD':math.pi/200}[angle]
    if op=='sin':return math.sin(a*to_rad)
    if op=='cos':return math.cos(a*to_rad)
    if op=='tan':return math.tan(a*to_rad)
    if op=='asin':return math.asin(a)/to_rad
    if op=='acos':return math.acos(a)/to_rad
    if op=='atan':return math.atan(a)/to_rad
    if op in UNARY:
        functions={'neg':lambda x:-x,'pow10':lambda x:10**x,'exp':math.exp,'log10':math.log10,'ln':math.log,
          'sqrt':math.sqrt,'square':lambda x:x*x,'reciprocal':lambda x:1/x,'abs':abs,
          'sign':lambda x:-1 if x<0 else 1,'int':math.trunc,'frac':lambda x:x-math.trunc(x)}
        return functions[op](a)
    b=xs[1]
    if op=='pow'and a<=0:raise ValueError('MK-61 power requires positive base')
    return {'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b,'pow':lambda:a**b}[op]()


def registers(expr):
    if isinstance(expr,str):return {expr}
    if isinstance(expr,dict):return set()
    return set().union(*(registers(x)for x in expr[1:]))


def words(expr):
    if isinstance(expr,str):return expr
    if isinstance(expr,dict):return 'числа π'if'pi'in expr else str(expr['constant'])
    op,*args=expr;items=[words(a)for a in args]
    if op=='pow10':return '10 в степени ('+items[0]+')'
    if op in WORDS:return WORDS[op]+' от ('+items[0]+')'
    if op=='pow':return '('+items[0]+') в степени ('+items[1]+')'
    return '('+items[0]+') '+{'+':'плюс','-':'минус','*':'умножить на','/':'разделить на'}[op]+' ('+items[1]+')'
