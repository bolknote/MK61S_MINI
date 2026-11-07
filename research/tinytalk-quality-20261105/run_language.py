#!/usr/bin/env python3
"""Prepare 100M language tokens and fill the expanded transformer's capacity."""
import json
from run_remote import container, command, status, ROOT


def main():
    status('installing_isolated_data_reader')
    command(container(1, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-deps', '--target', 'pydeps',
                      '--report', 'dependency-report.json', 'pyarrow==24.0.0'), 'dependency.log', 600)
    status('preparing_language_data', target_tokens=100000000)
    command(container(1, 'prepare_lm.py'), 'prepare-language.log', 3600)
    for batch in [128, 64, 32]:
        output = f'lm-b{batch}'
        status('language_pretraining', batch_size=batch, target_tokens=100000000)
        try:
            command(container(1, 'pretrain_language.py', '--output', output, '--batch-size', str(batch)), output + '.log', 14400)
        except RuntimeError:
            if 'out of memory' in (ROOT / (output + '.log')).read_text().lower() and batch > 32:
                status('retrying_smaller_batch', failed_batch=batch);continue
            raise
        report = json.loads((ROOT / output / 'training.json').read_text())
        (ROOT / 'language-selection.json').write_text(json.dumps({'directory': output, 'step': report['best_step'],
            'best_sha256': report['best_sha256'], 'token_exposures': report['token_exposures'],
            'conversation_audit_opened': False}, indent=2))
        status('language_pretrained_needs_conversation_training', selected=output, step=report['best_step'])
        return
    raise RuntimeError('No batch size completed language pretraining')


if __name__ == '__main__':
    try:main()
    except BaseException as error:
        status('failed', error=f'{type(error).__name__}: {error}');raise
