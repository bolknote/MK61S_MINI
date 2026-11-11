"""Reuse the frozen BZ loop, changing only its ordinary Session.request method."""
from ca_common import ROOT,VARIANTS
from ca_runtime import session_type
import bz_eval as inherited

Cache=inherited.Cache


def evaluate(actor,translator,tok,split,mode,variant,policy,progress,cache):
    old=inherited.ROOT,inherited.Session
    try:
        inherited.ROOT=ROOT;inherited.Session=session_type(variant)
        def update(phase,**extra):progress(phase,variant=variant,**extra)
        result=inherited.evaluate(actor,translator,tok,split,mode,policy,update,cache)
        result.update(format=variant,ablation='one section only')
        return result
    finally:inherited.ROOT,inherited.Session=old


def choose(reports,parents,savings):
    decisions={};keys={}
    for variant in VARIANTS:
        decision=inherited.selection(reports[variant],parents)
        a=reports[variant]['own']['own']['summary'];g=reports[variant]['gold']['own']['summary']
        key=[a['passed'],a['wrong_starts_repaired'],g['passed'],g['wrong_starts_repaired'],
            -a['false_DONE'],-a['correct_starts_corrupted'],savings[variant]]
        decisions[variant]={'checks':decision['checks'],'eligible':decision['all_checks_passed'],'key':key};keys[variant]=key
    eligible=[v for v in VARIANTS if decisions[v]['eligible']]
    selected=max(eligible,key=lambda v:keys[v])if eligible else'original'
    audit=selected if selected!='original'else max(VARIANTS,key=lambda v:keys[v])
    return {'chosen_format':selected,'audit_variant':audit,'decisions':decisions,'closed_seen':False,'optimizer_updates':0,
        'candidate_count':3,'audit_variant_is_not_necessarily_eligible':True,'product_profile_modified':False}
