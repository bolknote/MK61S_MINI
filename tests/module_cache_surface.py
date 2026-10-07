from pathlib import Path
import sys
from ui_contract_surface import body
root=Path(__file__).resolve().parents[1]
Path(sys.argv[1]).write_text(body(root/'code/loadable_module_runtime.cpp',"static RuntimeStatus load(Kind kind,"))
