#!/usr/bin/env python3
"""Use the verified local chat interface with accurate derivative-model provenance."""
import importlib.util
import argparse
import json
from pathlib import Path
import sys

precision_parser=argparse.ArgumentParser(add_help=False)
precision_parser.add_argument('--fp16-kv',action='store_true')
precision,remaining=precision_parser.parse_known_args()
sys.argv=[sys.argv[0],*remaining]

path=Path(__file__).resolve().parents[1]/'squeal-chat-20261105/chat.py'
spec=importlib.util.spec_from_file_location('compact_chat_cli',path)
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
args=cli.arguments()
config=args.model_dir/'config.json'
model_config=json.loads(config.read_text()) if config.exists() else {}
if model_config.get('tinytalk_answer_focus_separator_id') is not None or model_config.get('tinytalk_control_input_rows',0):
    raise SystemExit('Для этой версии используйте focus_chat.py --model <папка модели> --packed <файл Q4>.')
if config.exists()and args.profile=='tinytalk':
    backbone=model_config.get('tinytalk_backbone',{})
    if backbone:
        cli.PROFILES['tinytalk']['model']='CompactChat ('+backbone['repository']+')'
        cli.PROFILES['tinytalk']['revision']=backbone['revision']
cache_provider=None
processor_provider=None
if precision.fp16_kv:
    from common import fp16_cache_factory
    print('KV-кэш: FP16; вычисления внимания на компьютере: FP32.',flush=True)
    cache_provider=lambda model:fp16_cache_factory(model)()
if model_config.get('tinytalk_structured_intent_decoding'):
    from common import control_format_processor
    processor_provider=lambda model,tokenizer,length:[control_format_processor(model,tokenizer,length)]
cli.main(cache_factory=cache_provider,logits_processor_factory=processor_provider)
