"""Reuse frozen v1 execution/evaluation, changing only the input protocol."""
import argparse
import ar_run
from as_common import ROOT, check_frozen
from as_runtime import Session, goal_prompt, view_of

ar_run.ROOT=ROOT
ar_run.check_frozen=check_frozen
ar_run.Session=Session
ar_run.goal_prompt=goal_prompt
ar_run.view_of=view_of


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('model',choices=['small','teacher']);a=p.parse_args();ar_run.run(a.model)
