import json
import shutil
from vc_common import ROOT,INITIAL,sha,write


def main():
    selection=json.loads((ROOT/'preselected.json').read_text());records={}
    for label,source in [('baseline',INITIAL),('slow-best',ROOT/'slow/best'),('fast-best',ROOT/'fast/best')]:
        report=json.loads((ROOT/'results'/(label+'.json')).read_text());folder=ROOT/'export'/label;folder.mkdir(exist_ok=True,parents=True)
        shutil.copytree(source,folder/'hf',dirs_exist_ok=True);shutil.copyfile(ROOT/'results'/(label+'.mkqb'),folder/'model.mkqb')
        shutil.copyfile(ROOT/'output-token-ids.json',folder/'output-token-ids.json')
        record={'role':'semantic_verifier','arm':'q4','parameters':3022080,'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,
          'input_vocab_rows':8224,'output_rows':2,'classes':['d=correct','t=wrong'],'working_context':1024,'quantization_mode':'q4',
          'threshold':report['validation']['threshold'],'validation':report['validation'],'fresh':report['fresh'],
          'checkpoint_files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
          'source_coder_unchanged':True,'fresh_used_for_selection':False,'physical_picocalc_measured':False}
        write(folder/'manifest.json',record);records[label]=record
    chosen=selection['selected_arm']+'-best';shutil.copytree(ROOT/'export'/chosen,ROOT/'export/selected-budget',dirs_exist_ok=True)
    write(ROOT/'final-export.json',{'selected_label':chosen,'exports':records,'qualified_on_validation':records[chosen]['validation']['coverage']>=.8,
      'fresh_used_for_selection':False})


if __name__=='__main__':main()
