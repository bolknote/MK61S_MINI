"""Run the existing independent Thumb-2/wire vectors against the compact port."""
from pathlib import Path
import importlib.util,sys
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tests'))
spec=importlib.util.spec_from_file_location('original_arm_vectors',R/'tests/arm_execution.py')
vectors=importlib.util.module_from_spec(spec);spec.loader.exec_module(vectors)
vectors.B=vectors.B/'southbridge-runtime'
if __name__=='__main__':vectors.main()
