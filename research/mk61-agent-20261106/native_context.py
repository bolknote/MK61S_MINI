"""Bounded context exercises; the task remains text-only and model-written."""
import random

TRAIN_NOTES=[
 'Архивная заметка: обложка тетради зелёная, а закладка сделана из бумаги.',
 'Служебная запись сообщает о расположении стола у окна. Она не меняет расчёт.',
 'В каталоге описаны обложки книг и пустые страницы для заметок.',
 'Эта вспомогательная заметка относится к оформлению журнала, а не к программе.',
 'На полке стоят коробки разных цветов. Сведения не являются входом задачи.'
]
AUDIT_NOTES=[
 'Вне вычислительного задания: у переплёта тканевая поверхность и светлая лента.',
 'Заметка библиотекаря описывает рисунок на полях; новых условий расчёта здесь нет.',
 'Сведения об оформлении: конверт лежит возле чистого блокнота.',
 'Вспомогательный текст про канцелярские принадлежности не содержит команд калькулятора.'
]


def wrap(text,tokenizer,context,seed,*,audit=False):
    if context==512:return text
    rng=random.Random(seed);notes=AUDIT_NOTES if audit else TRAIN_NOTES
    header=('Основное вычислительное задание: '+text+'\n'
            'Далее идут посторонние заметки, которые не изменяют основное задание.\n')
    end='\nВыполни только основное вычислительное задание из начала записи. Посторонние заметки игнорируй.'
    parts=[];target=context-384
    length=len(tokenizer.encode(header+end,add_special_tokens=False))
    sizes={s:len(tokenizer.encode(' '+s,add_special_tokens=False))for s in notes}
    while length<target:
        note=rng.choice(notes);parts.append(note);length+=sizes[note]
    result=header+' '.join(parts)+end
    if len(tokenizer.encode(result,add_special_tokens=False))>context-280:raise ValueError('Context wrapper exceeded budget')
    return result
