from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.logger import (logger, info, warning, debug, shprint, info_main)

class GameLogic(CompiledComponentsPythonRecipe):    
    version = '0.17'
    url = 'https://github.com/cristivlas/GameLogic/raw/master/GameLogic.zip'
    name = 'GameLogic'    
    depends = ['setuptools']
    call_hostpython_via_targetpython = False

    def __init__(self):
        super().__init__()
        info ('!!! Using GameLogic Recipe !!!')

recipe = GameLogic()