"""Original state text; optional student hypothesis is the only input change."""
from hf_runtime import prompt
from am_runtime import hypothesis_text


def render(state,plan=None):
    runs={int(k):v for k,v in state['runs'].items()}
    notes=(f'Осталось действий: {state["remaining"]}. '
      'Исправление: WRITE с полным HEX программы. '
      'Проверяй результат по условию; stopped означает только останов. '
      'DONE заявляет решение. Если условие неполно или решение не найдено, UNSURE. ')
    if plan is not None:notes+=hypothesis_text(plan,runs)
    text=prompt(state['view'],'asm',current=state['body']or None,observation=state['observation'],case=state['case'],
      notes=notes,revision=state['revision'],runs=runs)
    text=text.replace('<patch>HH LL новый суффикс</patch><run/>, ','').replace('Позиция суффикса HH LL — два байта индекса в текущем HEX. ','')
    return text+'<'


def bounded_render(tokenizer,state,plan=None):
    from ac_protocol import prompt_ids
    text=render(state,plan)
    if plan is not None and len(prompt_ids(tokenizer,text))>=900:text=render(state)
    return text
