#!/usr/bin/env python3
"""Prepare short grounded-reading exercises from the checksum-verified official bAbI archive."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import re
import tarfile
from common import core
from prepare import fingerprint


TASKS = {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}
SHA = 'f7f0bee187efca0d81c3daac1b162cda4eb7f9505dee5ad6846eabbed3dbf92e'
FEMALE = 'Alice Anna Bella Ella Emma Eva Grace Jane Kate Lily Lisa Lucy Mia Nina Rose Ruth Sara Tina Zoe'.split()
MALE = 'Adam Ben Carl Dan Eli Finn Hank Ian Jack James Ken Leo Liam Luke Mark Max Nick Owen Paul Sam Tom Zack'.split()


def main():
    from transformers import AutoTokenizer
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    assert core.digest(args.archive) == SHA
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, trust_remote_code=False)
    tokenizer.model_max_length = 1000000  # Tokenize/filter raw stories; never feed an oversized prompt to the model.
    out = Path(args.output)
    assert not out.exists()
    out.mkdir(parents=True)
    rng = random.Random(641927)
    rows = {'train':{}, 'test':{}}
    skipped = Counter()
    support_offsets = Counter()
    with tarfile.open(args.archive, 'r:gz') as archive:
        license = archive.extractfile('tasks_1-20_v1-2/LICENSE.txt').read().decode()
        assert 'Attribution 3.0 Unported' in license
        (out / 'LICENSE-DATA.txt').write_text(license)
        members = sorted(archive.getmembers(), key=lambda m:m.name)
        for member in members:
            match = re.fullmatch(r'tasks_1-20_v1-2/en-10k/qa(\d+)_.*_(train|test)\.txt', member.name)
            if not match or int(match[1]) not in TASKS:
                continue
            task, split = int(match[1]), match[2]
            facts = {}
            episode = 0
            for line in archive.extractfile(member).read().decode().splitlines():
                number, content = line.split(' ', 1)
                number = int(number)
                if number == 1:
                    facts = {}
                    episode += 1
                if '\t' not in content:
                    facts[number] = content.strip()
                    continue
                question, answer, supports = content.split('\t')
                question, answer = question.strip(), answer.strip()
                support = {int(v) for v in supports.split()}
                assert support <= set(facts)
                # The answer-bearing fact must NOT always become the first visible fact.
                # Keep the longest recent suffix that fits, including earlier irrelevant facts.
                selected = list(facts.items())[-20:]
                names = {}
                if split == 'train':
                    names.update(zip(['Mary','Sandra','Julie'], rng.sample(FEMALE, 3)))
                    names.update(zip(['John','Daniel','Fred','Bill','Jeff'], rng.sample(MALE, 5)))
                def rename(text):
                    return re.sub(r'\b(?:Mary|Sandra|Julie|John|Daniel|Fred|Bill|Jeff)\b',
                                  lambda m:names.get(m[0], m[0]), text)
                fraction = rng.uniform(.25, .75) if rng.random() < .5 else None
                acknowledgment = rng.choice(['Okay.', 'Got it.', 'I am following.'])
                while selected and support <= {n for n, _ in selected}:
                    texts = [rename(text) for _, text in selected]
                    if task in {7, 8}:
                        texts.insert(0, 'Everyone starts with empty hands.')
                    if fraction is not None and len(texts) > 1:
                        cut = max(1, min(len(texts) - 1, int(len(texts) * fraction)))
                        messages = [{'role':'user', 'content':' '.join(texts[:cut])},
                            {'role':'assistant', 'content':acknowledgment},
                            {'role':'user', 'content':' '.join(texts[cut:] + [rename(question)])}]
                    else:
                        messages = [{'role':'user', 'content':' '.join(texts + [rename(question)])}]
                    if len(tokenizer.encode(core.render(messages), add_special_tokens=False)) + 40 <= 128:
                        break
                    selected.pop(0)
                else:
                    skipped[f'{split}:support_does_not_fit'] += 1
                    continue
                assert support <= {n for n, _ in selected}
                if support:
                    support_offsets[sum(n < min(support) for n, _ in selected)] += 1
                answer = rename(answer)
                if answer == 'maybe':
                    target = 'I do not know.'
                elif ',' in answer:
                    items = answer.split(',')
                    target = (', '.join(items[:-1]) + ' and ' + items[-1]).capitalize() + '.'
                else:
                    target = answer.capitalize() + '.'
                identity = fingerprint(messages)
                row = {'id':f'babi:{split}:task{task}:{episode}:{number}', 'messages':messages,
                    'kind':'grounded_qa', 'intent_label':'remember_other', 'plain_target':target,
                    'target':'<|tt_intent:remember_other|> ' + target, 'canonical_answer':answer,
                    'source':'Facebook bAbI en-10k', 'task':task, 'source_file':member.name,
                    'support_ids':sorted(support), 'included_fact_ids':[n for n, _ in selected]}
                rows[split].setdefault(identity, row)
    overlap = set(rows['train']).intersection(rows['test'])
    for key in overlap:
        del rows['test'][key]
    for split, content in rows.items():
        path = out / (split + '.jsonl')
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in content.values()))
    report = {'archive_sha256':SHA, 'archive_url':'https://parl.ai/downloads/babi/babi.tar.gz',
        'license':'CC BY 3.0; Copyright Facebook', 'citation':'Weston et al., Towards AI-Complete Question Answering: A Set of Prerequisite Toy Tasks (2015)',
        'tasks':sorted(TASKS), 'train_rows':len(rows['train']), 'test_rows':len(rows['test']),
        'train_sha256':core.digest(out / 'train.jsonl'), 'test_sha256':core.digest(out / 'test.jsonl'),
        'train_tasks':dict(Counter(r['task'] for r in rows['train'].values())), 'skipped':dict(skipped),
        'exact_test_overlap_removed':len(overlap), 'all_supplied_supporting_facts_preserved':True,
        'context_policy':'Longest recent contiguous suffix fitting the context, independent of answer position',
        'first_support_offsets':dict(support_offsets), 'train_entities_varied_with_gender_consistent_bijections':True,
        'official_test_names_preserved':True,
        'purpose':'Grounded-reading exercises; separate from ordinary-chat quality evaluation',
        'ordinary_conversation_final_audit_used':False}
    core.save(out / 'manifest.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
