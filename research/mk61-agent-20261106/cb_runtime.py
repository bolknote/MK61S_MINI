"""Expose real review availability; never consult task truth in actor requests."""
import copy
from bj_runtime import Session as Parent,render as original_render,snapshot as old_snapshot
from ca_runtime import shorten


def snapshot(session):
    state=old_snapshot(session);state['replan_attempted']=bool(session.replan_attempted)
    return state


def render(state,format='notes'):
    assert format in ['original','full','notes']
    text=original_render(state,'spec')
    if state.get('body')is None:return text
    if format=='notes':text=shorten(text,'notes')
    if format!='original':
        attempted=state['replan_attempted']
        if attempted:
            text=text.replace('DIAG 04 FF FF 00 00 означает ошибку гипотезы; затем повторный разбор условия без изменения программы.',
                'Повторный разбор SPEC уже выполнен. Если гипотеза всё ещё неверна, UNSURE.')
        text=text.replace('Ассистент: <','Разборов SPEC осталось: '+('0'if attempted else'1')+'.\nАссистент: <')
    return text


def session_type(format):
    class ActorSession(Parent):
        def request(self):return render(snapshot(self),format)
    return ActorSession
