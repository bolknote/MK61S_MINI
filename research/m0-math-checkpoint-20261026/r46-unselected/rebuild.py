from pathlib import Path
import difflib,hashlib,importlib.util,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
exec(compile((W/'build.py').read_text().split("spec=importlib.util.spec_from_file_location",1)[1].join(["spec=importlib.util.spec_from_file_location",""]),str(W/'build.py'),'exec'))
