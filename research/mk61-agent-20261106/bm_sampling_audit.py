"""Replay just the RNG draws; accept the audit only if the training digest matches."""
import collections
import json
from bl_common import ROOT,read,write
from bl_spec import equal_spec
import bl_course


def main():
    counts=collections.Counter();origins=collections.Counter()
    def encoded(tokenizer,row,arm='spec'):
        origin=row['origin']
        if origin not in ['natural','review_fix','review_keep']:
            counts['action_rows']+=1;origins[origin]+=1
            correct=row.get('own_hypothesis_correct')
            if correct is None:
                correct=equal_spec(row['state']['declared_spec'],row['target_spec'])
            counts['correct_hypothesis'if correct else'wrong_hypothesis']+=1
        return [1],[-100],0,0
    bl_course.encoded=encoded;course=bl_course.Course(None)
    for step in range(1,read(ROOT/'policy.json')['steps']+1):course.batch(step,'cpu')
    result={'draw_digest':course.digest,'counts':dict(counts),'origins':dict(origins),
            'wrong_hypothesis_fraction':counts['wrong_hypothesis']/counts['action_rows'],
            'requires_exact_actual_training_digest_match':True}
    write(ROOT/'sampling-audit-pending.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
