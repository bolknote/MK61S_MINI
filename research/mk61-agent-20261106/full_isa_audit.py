"""Audit actual supervised/test coverage against every classic opcode byte."""
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess

from tasks import BUILD
from full_isa_protocol import answer,linear_instructions,REGISTERS

HERE=Path(__file__).parent
ROOT=BUILD/'full-isa-v1'
SOURCE=Path('/Users/bolk/Projects/MK-61')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return [json.loads(x)for x in path.read_text().splitlines()]
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def group(code):
    if code<=0x0C:return 'Ввод чисел, десятичная точка, знак, порядок'
    if code in [0x0D,0x0E,0x0F,0x14,0x25]:return 'Стек и очистка'
    if 0x10<=code<=0x13 or code in [0x22,0x31]:return 'Базовая арифметика и модуль'
    if 0x15<=code<=0x18 or 0x20<=code<=0x24:return 'Степени, корень, логарифмы, константа π'
    if 0x19<=code<=0x1E:return 'Тригонометрия и обратные функции'
    if code in [0x26,0x2A,0x30,0x33]:return 'Преобразования градусов/минут/секунд'
    if code in [0x32,0x34,0x35,0x36]:return 'Знак, целая/дробная часть, максимум'
    if 0x37<=code<=0x3A:return 'Логические операции'
    if code==0x3B:return 'Генератор псевдослучайных чисел'
    if 0x40<=code<=0x4E or 0x60<=code<=0x6E:return 'Прямая работа со всеми R0–RE'
    if code in [0x50,0x51,0x52,0x53,0x54,0x55,0x56]:return 'Останов, переход, подпрограмма, возврат, НОП'
    if code in [0x57,0x59,0x5C,0x5E]:return 'Прямые условные переходы'
    if code in [0x58,0x5A,0x5B,0x5D]:return 'Все четыре счётчика циклов L0–L3'
    if 0x70<=code<=0xEE and code%16<15:return 'Косвенная адресация, память, вызовы и условия'
    return 'Служебные, ошибочные и недокументированные коды'


def coverage(codes):
    count=collections.Counter();errors=[]
    for identity,code in codes:
        try:
            for row in linear_instructions(code):count[row['opcode']]+=1
        except ValueError as e:errors.append({'id':identity,'error':str(e)})
    return count,errors


def main():
    ROOT.mkdir(exist_ok=True)
    catalog=json.loads(subprocess.check_output([str(ROOT/'catalog-probe')],text=True))
    assert len(catalog)==256 and {x['code']for x in catalog}==set(range(256))
    previous=BUILD/'semantic-3m-v1/server-results'
    datasets={'natural_train':[(r['id'],r['reference_code'])for r in read(previous/'train.jsonl')],
      'formal_98':[(r['id'],r['reference_code'])for r in read(BUILD/'tasks/test-extended-v2.jsonl')]}
    replay=[]
    for path in [previous/'replay.jsonl',previous/'actual-error-replay.jsonl']:
        for i,row in enumerate(read(path)):
            found=re.search(r'<write>([0-9A-Fa-f\s]+)</write>',row['answer'])
            if found:replay.append((f'{path.name}:{i}',[int(x,16)for x in found.group(1).split()]))
    datasets['tool_replay']=replay
    stats={k:coverage(v)for k,v in datasets.items()}
    supervised=stats['natural_train'][0]+stats['tool_replay'][0]
    for row in catalog:
        row['group']=group(row['code']);row['supervised_target_occurrences']=supervised[row['code']]
        row['formal_98_target_occurrences']=stats['formal_98'][0][row['code']]
        row['new_curriculum_required']=True
        row['old_presence_is_not_proof_of_mastery']=True
    write(ROOT/'catalog.json',catalog)
    groups=collections.defaultdict(list)
    for row in catalog:groups[row['group']].append(row)
    # The encoding head is derived from the entire byte alphabet, not the
    # operations present in a restricted arithmetic generator.
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(previous/'export/selected-budget/hf',local_files_only=True,trust_remote_code=False)
    ids={tokenizer.eos_token_id};texts=[answer([x])for x in range(256)]+[answer([x,y])for x in range(256)for y in range(256)]+['<trace/>','<done/>']
    for at in range(0,len(texts),2048):
        encoded=tokenizer(texts[at:at+2048],add_special_tokens=False)['input_ids']
        for values in encoded:ids.update(values)
    write(ROOT/'output-token-ids.json',sorted(ids))
    policy={'version':'full-isa-v1','status':'corrected_scope_and_protocol_only; full semantic corpus and training not yet complete',
      'model':'selected 3M HEX','input_russian_vocab_unchanged':True,'output':'ordinary HEX; no seven-operation calc grammar',
      'all_256_byte_values_representable':True,'output_rows':len(ids),'registers':REGISTERS,'program_cells':105,
      'angle_modes':['RAD','DEG','GRAD'],'numeric_literals':True,'initial_stack':['X','Y','Z','T','X1'],
      'coverage_accounting':'every opcode, every register variant, every angle mode and every control-flow path',
      'curriculum':[
        {'stage':'instruction_semantics','scope':'Every catalog entry; documented commands, errors and raw aliases explicitly labelled. All operands, stack/memory changes, domains and angle modes verified.'},
        {'stage':'composition','scope':'All scientific/arithmetic functions combined with literals, registers, stack and conversions; no seven-operation AST restriction.'},
        {'stage':'programming','scope':'Conditional branches, L0/L1/L2/L3, calls/returns, all indirect families and memory changes.'},
        {'stage':'books_and_games','scope':'Verified fragments and complete interactions from existing sources; presence in LM text does not count as operational mastery.'}],
      'release_gates':{'minimum_standard_opcode_reference_coverage':1.0,'no_missing_standard_opcode_groups':True,
        'balanced_heldout_by_opcode_and_register':True,'novel_numeric_inputs_and_new_wordings':True,
        'Q4_actual_packet_evaluation':True,'learned_quality_not_yet_measured':True},
      'grader_requirements':['Real microcode core','Configured angle mode per case','X/Y/Z/T/X1 and all 15 memory registers as needed',
        'Raw BCD/display comparisons for logical and nondecimal results','Expected error outcomes and domain boundaries',
        'Both paths of each condition; all four loop counters','Indirect register side effects; no blind R0–R3 renaming',
        'RNG state and sequence properties','Program continuations across stop/resume for games'],
      'full_coverage_training_launched':False,'old_98_of_98_is_not_full_isa_coverage':True}
    write(ROOT/'curriculum.json',policy)
    report={'catalog_entries':256,'catalog_risks':dict(collections.Counter(r['risk']for r in catalog)),
      'supervised_target_unique_opcodes':len(supervised),'formal_98_target_unique_opcodes':len(stats['formal_98'][0]),
      'groups':{name:{'entries':len(rows),'old_supervised_covered':sum(r['supervised_target_occurrences']>0 for r in rows),
        'old_formal_covered':sum(r['formal_98_target_occurrences']>0 for r in rows),'missing_supervised':[r['hex']for r in rows if not r['supervised_target_occurrences']]}for name,rows in groups.items()},
      'decode_errors':{k:v[1]for k,v in stats.items()},'output_rows_full_hex':len(ids),
      'scope_note':'Instruction presence is an audit of targets, not model pass rate. Linear decoding is exact for these generated suites; overlapping code/data needs dynamic traces.',
      'catalog_source':str(SOURCE/'native/src/core/opcodes.cpp'),
      'source_sha256':{str(p):sha(p)for p in [SOURCE/'native/src/core/opcodes.cpp',SOURCE/'docs/03-command-reference.md',HERE/'full_isa_protocol.py']},
      'catalog_discrepancies':['3E is marked keyboard-enterable by the sibling implementation but described as raw/unenterable in its reference. It remains explicitly marked undocumented, not silently dropped.']}
    write(ROOT/'coverage.json',report)
    lines=['# Полный набор МК-61: исправление объёма обучения','',
      'Предыдущий курс составных выражений был ошибочно ограничен семью действиями и R0–R3. Это ограничение генератора и промежуточного `<calc>`, а не памяти модели, HEX или МК-61.',
      '',f'В старых 98 формальных задачах в эталонных программах представлены **{report["formal_98_target_unique_opcodes"]} разных кодов инструкций**; адресные операнды не засчитаны как инструкции. В проверенных целевых программах последнего обучения и повторения — {report["supervised_target_unique_opcodes"]}. Это присутствие в заданиях, а не доказательство владения командами.',
      '', '| Группа | Кодов в каталоге | Были в обучающих ответах | Были в 98 проверках |', '|---|---:|---:|---:|']
    for name,item in report['groups'].items():lines.append(f'| {name} | {item["entries"]} | {item["old_supervised_covered"]} | {item["old_formal_covered"]} |')
    lines+=['',f'Каталог сохраняет все 256 значений 00–FF с отдельной маркировкой документированных, ошибочных и недокументированных кодов. HEX-голова нового протокола содержит {len(ids)} существующих токенов; русский входной словарь и число параметров не меняются.',
      '', '## Исправленный курс','',
      'Полная семантика команд → составные вычисления всех функций → условия/циклы/подпрограммы/косвенная память → проверенные фрагменты игр и книг. Нужны все R0–RE, стек, ввод числовых констант, три режима углов, области определения, ошибки, BCD-логика, состояние генератора и продолжение программ после останова.',
      'Программа выдаётся прямо в HEX. Семикомандный арифметический `<calc>` удалён из нового интерфейса; он не подходит как обязательное представление программы с циклами, памятью и вызовами. Краткие объяснения можно оставить отдельным учебным заданием.',
      '', '**На этом шаге подготовлены полный учёт, новый интерфейс и контракт покрытия. Полный семантический корпус ещё не готов; обучение полной ISA не запускалось. Перечисление каталога не означает, что модель выучила команды.**',
      '', 'Следующий запуск должен блокироваться при пропуске стандартной команды в проверенных примерах и публиковать результаты по каждой группе, регистру и режиму углов. Старые 98/98 не используются как заявление о полном наборе.',
      '', 'Артефакты: `'+str(ROOT.resolve())+'` (`catalog.json`, `coverage.json`, `curriculum.json`, `output-token-ids.json`).',
      'Источники: локальные `native/src/core/opcodes.cpp`, `docs/03-command-reference.md` соседнего проекта МК-61; исходное руководство: https://www.wass.net/manuals/Elektronika%20MK-61.pdf . Каталожная отметка клавиатурного ввода для 3E расходится с текстовым справочником; это недокументированный код, расхождение сохранено явно.']
    (HERE/'FULL_ISA_COVERAGE.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k in ['catalog_entries','supervised_target_unique_opcodes','formal_98_target_unique_opcodes','output_rows_full_hex']},ensure_ascii=False))


if __name__=='__main__':main()
