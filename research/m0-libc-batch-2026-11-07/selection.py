"""Keep full rankings; resolve indistinguishable candidates by short inputs/size."""
def choose(ranking):
    if not ranking:raise ValueError('Empty candidate ranking')
    ranked=sorted(ranking,key=lambda v:v['ratio']);fastest=ranked[0]
    if not fastest['resolved_gain']:
        return dict(verdict='KEEP_CURRENT_NO_RESOLVED_GAIN',picked=fastest,unresolved_ties=[])
    tied=[v for v in ranked if v['resolved_gain'] and v['ratio']-fastest['ratio']<=max(v['noise_ratio'],fastest['noise_ratio'])]
    # A near tie must not buy a large secondary-workload loss when a
    # candidate in the same primary uncertainty envelope avoids that loss.
    safe=[v for v in tied if v['weighted_short_ratio']<=1 and all(r<=1 for r in v['sensitivity_ratios'].values())]
    preferred=safe or tied
    picked=min(preferred,key=lambda v:(v['weighted_short_ratio'],v['body_bytes'],v['ratio']))
    return dict(verdict='GAIN_UNDER_FROZEN_WORKLOAD',picked=picked,fastest_sample_mean=fastest,unresolved_ties=[v['profile'] for v in tied],secondary_regime_safe_profiles=[v['profile'] for v in safe],rule='Candidate differences within the larger observed quantization-plus-spread envelope are unresolved; prefer candidates without an observed aggregate loss in short/sensitivity regimes when available, then better weighted short-input behavior and smaller code. This is a deterministic engineering rule, not a statistical confidence interval.')

def compare_matched(reference, observed):
    """Compare candidate/native ratios only on the same declared input subset.

    A previously disclosed short-only regression does not invalidate a whole
    workload gain. A new worsening beyond both observed envelopes does.
    """
    assert reference['profile'] == observed['profile']
    assert reference['physical_cases'] == observed['physical_cases']
    drift = observed['ratio'] - reference['ratio']
    bound = observed['noise_ratio'] + reference['noise_ratio']
    return dict(ratio_drift=drift, combined_uncertainty_ratio=bound,
                no_resolved_extra_regression=drift <= bound)
