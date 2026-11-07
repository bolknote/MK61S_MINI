"""Extra semantic supervision; marker-only tokens do not dilute core AST loss."""


def core_labels(token_ids,offsets,start,end,eos):
    if len(token_ids)!=len(offsets)or not 0<=start<end:raise ValueError('Invalid semantic target span')
    labels=[token if right>start and left<end else -100 for token,(left,right)in zip(token_ids,offsets)]
    if not any(x!=-100 for x in labels):raise ValueError('No semantic tokens in target span')
    return labels+[eos]
