#!/usr/bin/env python
from distribute_setup import use_setuptools
use_setuptools()

from setuptools import setup
import sys, os
try:
    import py2exe
except ImportError:
    py2exe = None


args = {
    'name': 'stratum_mining_proxy',
    'version': '0.3.1',
    'description': 'Getwork-compatible proxy for Stratum mining pools',
    'author': 'slush',
    'author_email': 'info@bitcion.cz',
    'url': 'http://mining.bitcoin.cz/stratum-mining/',
    'py_modules': ['midstate',],
    'install_requires': ['twisted', 'stratum',],
    'scripts': ['mining_proxy.py'],
}

if py2exe != None:
    args.update({
        # py2exe options
        'options': {'py2exe':
                      {'optimize': 2,
                       'bundle_files': 1,
                       'compressed': True,
                      },
                  },
        'console': ['mining_proxy.py'],
        'zipfile': None,
    })

setup(**args)
