<!--
# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
-->

# cloudblue-connector
This repository contains applications that connects CloudBlue Connect API with virtual infrastructure managed by OpenStack API. All functions are provided by three applications
 - cloudblue-fulfillments - processes Fulfillments, creates and manages Domains, Projects and Users.
 - cloudblue-usage - sends usage report for active Assets.
 - cloudblue-usage-files - confirms processed usage files.

## Configuration
Connector accepts configuration file in json format. Next parameters are expected to be set in the config file:
 - infraKeystoneEndpoint - compute keystone authentication endpoint url.
 - infraDomain - compute user domain name.
 - infraProject - compute user project name.
 - infraUser - compute user name.
 - infraPassword - compute user password.
 - misc - additional configuration options to define connector behavior:
   - domainCreation - domain creation mode. If set to _true_, domain will be created automatically.
     If set to _false_, manual creation is required.
     (default: _true_)
   - imageUpload - image upload permission. If set to _true_, user role will include _image_upload_ permission.
     (default: _true_)
   - hidePasswordsInLog - wipe plain-text passwords Connector events output.
     (default: _true_)
   - testMarketplaceId - ID of Marketplace, to place asset requests for evaluation. If not set, all asset requests from all Marketplaces will be processed regardless of **testMode** setting.   
   - testMode - test mode enabled or not.
     If set to _true_, requests made in **testMarketplaceId** will be processed only.
     If set to _false_, requests made in **testMarketplaceId** will be ignored.
     (default: _false_)
 - apiEndpoint - CloudBlue Connect API endpoint url.
 - apiKey - CloudBlue Connect API key.
 - products - list of product IDs from CloudBlue Connect.
 - report_usage - list of product IDs with PAYG resource model from CloudBlue Connect.
 - dataRetentionPeriod - period (in days) to keep customer data after subscription cancellation
   (default: _15_)
 - templates - set of template IDs that are used when Fulfillment is confirmed of cancelled.
 
The repository contains configuration example:
 - config.json.example

Processing applications take configuration parameters from /etc/cloudblue-connector/config.json file.

## Logging
By default, Connector prints all events to console. This behavior can be changed with modification of configuration file.

The repository contains configuration example with time-rotating file handle in addition to console handle:
 - config-logging.json.example

For more details about logging facilities please refer to standard library documentation https://docs.python.org/2.7/library/logging.html

Processing applications take logging configuration parameters from /etc/cloudblue-connector/config-logging.json file, if exists.

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
