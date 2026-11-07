"""Broaden ordinary Russian phrasing while keeping exact, executable target algorithms."""
import argparse
from pathlib import Path

import teacher_data
from tasks import BUILD,compile_expr,split_of


STYLES=[
    'Живая разговорная просьба пользователя. Пиши просто, без канцелярских оборотов, по-разному начинай предложения.',
    'Короткая история: что было, что произошло, что требуется узнать. Сюжет должен точно соответствовать алгоритму.',
    'Прямой вопрос в одном предложении. Порядок упоминания регистров меняй; обязательно обозначь их роли.',
    'Небольшая игровая ситуация, если она естественна: результат раунда, штраф, перемещение, ресурс. Нужен только один результат.',
    'Бытовая ситуация, подходящая этой формуле: количество, покупки, запас, расстояние. Не добавляй лишних операций.',
    'Задача о величинах, изменении знака, отклонении или положении — только когда это подходит формуле.',
    'Пользователь объясняет своими словами, без слов «операнд», «вычислите» и без буквальной записи формулы.',
    'Условие из учебной книги с ясным описанием величин. Избегай одинаковых вводных фраз.',
    'Техническая инструкция для показаний прибора или коэффициентов. Одно-два коротких предложения.',
    'Сначала скажи, какой результат нужен, потом сообщи, в каких регистрах лежат исходные величины.',
    'Пользователь просит получить итог после двух-трёх простых действий. Для одношаговой формулы не выдумывай дополнительные шаги.',
    'Очень простая разговорная формулировка с понятными ролями величин. Не используй местоимения с неясной отсылкой.'
]


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=BUILD/'distill-broad');p.add_argument('--workers',type=int,default=4);args=p.parse_args()
    old=teacher_data.templates()
    basics=[[op,'R0','R1']for op in ['+','-','*','/']]+[[op,'R0']for op in ['abs','neg','square']]
    compounds=[];seen=set()
    for expr in old:
        key=teacher_data.canonical(expr)
        if len(compile_expr(expr))<=3 or split_of(expr)!='train' or key in seen:continue
        # Avoid many tautologies from repeated identical operands in random trees.
        if isinstance(expr,list)and len(expr)==3 and expr[1]==expr[2]:continue
        compounds.append(expr);seen.add(key)
        if len(compounds)==25:break
    frozen=basics+compounds
    teacher_data.STYLES=STYLES
    teacher_data.templates=lambda:frozen
    teacher_data.generate(args)


if __name__=='__main__':main()
