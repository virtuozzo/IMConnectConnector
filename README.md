<!--
#******************************************************************************
# Copyright (c) 2020, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
#******************************************************************************
-->

# cloudblue-connector
This repository contains applications that connects CloudBlue Connect API with virtual infrastructure managed by OpenStack API. All functions are provided by three applications
 - cloudblue-fulfillments - processes Fulfillments, creates and manages Domain, Projects and Users.
 - cloudblue-usage - sends usage report for active Assets.
 - cloudblue-usage-files - confirms processed usage files.

## Configuration
Connector accept configuration file in json format, next parameters are expected to be find in the config file:
 - infraKeystoneEndpoint - compute keystone authentication endpoint url.
 - infraDomain - compute user domain name.
 - infraProject - compute user project name.
 - infraUser - compute user name.
 - infraPassword - compute user password.
 - apiEndpoint - CloudBlue Connect API endpoint url.
 - apiKey - CloudBlue Connect API key.
 - projects - a list of product IDs from CloudBlue Connect.
 - templates - set of template IDs that are used when Fulfillment is confirmed of cancelled.
 
The repository contains configuration example:
 - config.json.example

Fulfillment processing application takes it's configuration from /etc/cloudblue-connector/config.json
Usage processing application takes it's configuration from /etc/cloudblue-connector/config-usage.json

## Installation
List of python dependencies:
- typing
- pathlib
- python-cinderclient
- gnocchiclient
- python-keystoneclient
- python-neutronclient
- python-novaclient
- python-magnumclient
- python-octaviaclient
- connect-sdk

Repository contains setup.py files that can be used with python pip/easy_install.
