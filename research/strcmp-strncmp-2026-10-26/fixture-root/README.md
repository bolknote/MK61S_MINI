Frozen comparison experiment source snapshot1fdc92e67 (base6e).
Compiler fixtures only; no production include refers to this tree.
Headers are copied transitively to reproduce the already qualified ARM code.
The shared strcmp bridge additionally requires a true flag value; =0 is local.
This preprocessor correction does not change any previously tested =1 body.
