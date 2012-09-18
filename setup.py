#!/usr/bin/env python
from distribute_setup import use_setuptools
use_setuptools()

from setuptools import setup
import sys, os
try:
    import py2exe
except ImportError:
    py2exe = None

import version

args = {
    'name': 'stratum_mining_proxy',
    'version': version.VERSION,
    'description': 'Getwork-compatible proxy for Stratum mining pools',
    'author': 'slush',
    'author_email': 'info@bitcion.cz',
    'url': 'http://mining.bitcoin.cz/stratum-mining/',
    'py_modules': ['client_service', 'getwork_listener', 'jobs', 'midstate',
                   'multicast_responder', 'stratum_listener', 'utils',
                   'version', 'worker_registry'],
    'install_requires': ['setuptools', 'twisted', 'stratum', 'argparse'],
    'scripts': ['mining_proxy.py'],
}

if py2exe != None:
    args.update({
        # py2exe options
        'options': {'py2exe':
                      {'optimize': 2,
                       'bundle_files': 1,
                       'compressed': True,
                       'dll_excludes': ['mswsock.dll', 'powrprof.dll'],
                      },
                  },
        'console': ['mining_proxy.py'],
        'zipfile': None,
    })

setup(**args)
