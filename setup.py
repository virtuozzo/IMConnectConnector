# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from distutils.core import setup
import os.path


def get_version():
    if os.path.isfile('Makefile.version'):
        with open('Makefile.version', 'r') as f:
            return f.read().strip()


setup(
    name='cloudblue_connector',
    version=get_version(),
    packages=[
        'cloudblue_connector',
        'cloudblue_connector.automation',
        'cloudblue_connector.consumption',
        'cloudblue_connector.quota',
        'cloudblue_connector.core'
    ],
    # entry_points not supported in python2.7
    #entry_points = {
    #    'console_scripts': [
    #        'cloudblue-fulfillments=cloudblue_connector:process_fulfillment',
    #        'cloudblue-usage=cloudblue_connector:process_usage',
    #    ],
    #},
    scripts=['cloudblue-fulfillments', 'cloudblue-usage', 'cloudblue-usage-files'],
    long_description=open('README.txt').read(),
)
