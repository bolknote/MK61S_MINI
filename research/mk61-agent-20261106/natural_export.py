"""Reuse the audited full-ISA exporter with stage-specific provenance."""
import json
import shutil

from natural_common import ROOT,INITIAL,PREVIOUS,write


def main():
    import full_isa_export as exporter
    exporter.ROOT=ROOT;exporter.INITIAL=INITIAL;exporter.main()
    policy=json.loads((ROOT/'policy.json').read_text());final=json.loads((ROOT/'final-export.json').read_text())
    for label in final['exports']:
        folder=ROOT/'export'/label;manifest=json.loads((folder/'manifest.json').read_text())
        if label.endswith('-endpoint'):manifest['selected_step']=policy['steps_each']
        manifest['base_stage']='full-isa-v1/protected-best step2000'
        manifest['current_stage']='full-isa-natural-v1'
        manifest['cumulative_updates_from_codec_base']=2000+manifest['selected_step']
        manifest['fresh_language_test_used_for_selection']=False
        manifest['previous_isa_and_153_natural_are_observed_retests']=True
        write(folder/'manifest.json',manifest);final['exports'][label]=manifest
    shutil.copytree(ROOT/'export'/final['selected_label'],ROOT/'export/selected-budget',dirs_exist_ok=True)
    write(ROOT/'final-export.json',final)


if __name__=='__main__':main()

