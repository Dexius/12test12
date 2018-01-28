# coding: utf-8
import os

from cx_Freeze import setup, Executable

os.environ['TCL_LIBRARY'] = 'C:\\ProgramData\\Anaconda3\\Library\\lib\\tcl8.6'
os.environ['TK_LIBRARY'] = 'C:\\ProgramData\\Anaconda3\\Library\\lib\\tk8.6'
executables = [Executable('cli_beta.py')]

excludes = []
includes = ['numpy.core._methods', 'numpy.lib.format', 'terminaltables']

zip_include_packages = ['collections', 'encodings', 'importlib']

options = {
    'build_exe': {
        'include_msvcr': True,
        'excludes': excludes,
        'includes': includes,
        'zip_include_packages': zip_include_packages,
        'build_exe': 'build_windows',
    }
}

setup(name='cointrader',
      version='1.0.0.1',
      description='Coin`s trader bot',
      executables=executables,
      options=options)
