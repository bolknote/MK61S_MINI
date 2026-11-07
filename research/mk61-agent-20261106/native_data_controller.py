"""Prepare language data in the cached image, without changing the shared image."""
from run_experiment import run,SCRIPT,BASE

if __name__=='__main__':
    (BASE/'native-mixed-v1').mkdir(exist_ok=True)
    run('native-mixed-v1/language-data.log',SCRIPT+'native_language_data.py',timeout=10800)
