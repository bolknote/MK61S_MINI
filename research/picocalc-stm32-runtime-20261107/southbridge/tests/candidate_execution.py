"""Run the existing ARM checks against a separately staged resident candidate."""
import argparse
import importlib.util
from pathlib import Path
import sys

P=Path(__file__).resolve().parent
ROOT=P.parents[3]
sys.path.insert(0,str(P))

def load(name):
 spec=importlib.util.spec_from_file_location('candidate_'+name,P/(name+'.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--build-dir',type=Path,required=True)
 args=parser.parse_args();build=args.build_dir.resolve()
 if not build.is_relative_to(ROOT):parser.error('build directory must be in the repository')
 import arm_execution
 arm_execution.vectors.B=build
 arm_execution.vectors.main()
 for name in ('uart_dma_execution','combined_execution'):
  module=load(name);module.B=build;module.main()

if __name__=='__main__':main()
