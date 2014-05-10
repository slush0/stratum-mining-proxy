#!/usr/bin/env python
from distribute_setup import use_setuptools
use_setuptools()

from setuptools import setup, Extension
import sys, os
try:
    import py2exe
except ImportError:
    py2exe = None

from mining_libs import version

args = {
    'name': 'stratum_mining_proxy',
    'version': version.VERSION,
    'description': 'Getwork-compatible proxy for Stratum mining pools',
    'author': 'slush',
    'author_email': 'slush@satoshilabs.com',
    'url': 'http://mining.bitcoin.cz/stratum-mining/',
    'ext_modules': [
      Extension(
        'midstate', 
        ['midstatec/midstatemodule.c'],
        include_dirs=['/usr/include/python2.7'],
        extra_compile_args=['-march=native', '-Wall', '-funroll-all-loops', '-O3', '-fstrict-aliasing', '-Wall', '-std=c99',  '-fPIC', '-shared'],
        libraries=['python2.7'],
        extra_link_args=['-Wl,-O1', '-Wl,--as-needed']
        )
      ],
    'py_modules': ['mining_libs.client_service', 'mining_libs.getwork_listener',
                   'mining_libs.jobs', 'mining_libs.midstate',
                   'mining_libs.multicast_responder', 'mining_libs.stratum_listener',
                   'mining_libs.utils', 'mining_libs.version', 'mining_libs.worker_registry',
                   'midstatec.midstatec'],
    'install_requires': ['setuptools>=0.6c11', 'twisted>=12.2.0', 'stratum>=0.2.15', 'argparse'],
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
