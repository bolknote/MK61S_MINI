"""Paired execution outcomes and descriptive scenario-cluster bootstrap intervals."""
import collections
import random


def comparison(tasks,hex_rows,h32_rows,repeats=10000):
    hex_by={r['id']:bool(r['pass'])for r in hex_rows};h32_by={r['id']:bool(r['pass'])for r in h32_rows}
    expected={t['id']for t in tasks};assert set(hex_by)==set(h32_by)==expected
    groups=collections.defaultdict(list);clustered=collections.defaultdict(lambda:collections.defaultdict(list))
    for task in tasks:
        level=task['level'];a=hex_by[task['id']];b=h32_by[task['id']];groups[level].append((a,b))
        # Two/three-op wordings share a scenario; each simple wording is its
        # own authored situation. This does not group all shared math families.
        key=task['id']if level==1 else task['id'].rsplit(':',1)[0]
        clustered[level][key].append(int(b)-int(a))
    levels={}
    for level,rows in groups.items():
        levels[str(level)]={'total':len(rows),'hex_passed':sum(a for a,b in rows),'h32_passed':sum(b for a,b in rows),
          'both_pass':sum(a and b for a,b in rows),'hex_only':sum(a and not b for a,b in rows),
          'h32_only':sum(b and not a for a,b in rows),'both_fail':sum(not a and not b for a,b in rows)}
    macro=sum((x['h32_passed']-x['hex_passed'])/x['total']for x in levels.values())/len(levels)
    clusters={level:[sum(values)/len(values)for values in rows.values()]for level,rows in clustered.items()}
    rng=random.Random(6114521);samples=[]
    for _ in range(repeats):
        value=sum(sum(rng.choice(values)for _ in values)/len(values)for values in clusters.values())/len(clusters)
        samples.append(value)
    samples.sort();low=samples[int(.025*(repeats-1))];high=samples[int(.975*(repeats-1))]
    return {'levels':levels,'macro_delta_h32_minus_hex':macro,'macro_delta_bootstrap95':[low,high],
      'bootstrap_repeats':repeats,'scenario_clusters':sum(map(len,clusters.values())),
      'shared_mathematical_families_not_independent':True,'independent_human_population_claim':False}
