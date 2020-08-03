#******************************************************************************
# Copyright (c) 2020, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
#******************************************************************************

from distutils.core import setup
import os.path

def get_version():
    if os.path.isfile('Makefile.version'):
        with open('Makefile.version', 'r') as f:
            return f.read()


setup(
    name='cloudblue_connector',
    version=get_version(),
    packages=['cloudblue_connector',],
    scripts=['cloudblue-fulfillments', 'cloudblue-usage', 'cloudblue-usage-files'],
    long_description=open('README.txt').read(),
)
