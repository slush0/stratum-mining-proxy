#!/usr/bin/env python
from distribute_setup import use_setuptools
use_setuptools()

from setuptools import setup

setup(name='stratum_mining_proxy',
      version='0.1.0',
      description='Getwork-compatible proxy for Stratum mining pools',
      author='slush',
      author_email='info@bitcion.cz',
      url='http://mining.bitcoin.cz/stratum-mining/',
      py_modules=['midstate',],
      install_requires=['twisted', 'stratum',],
      scripts=['mining_proxy.py'],
     )
