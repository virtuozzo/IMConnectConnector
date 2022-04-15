# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

import json
import logging
import os
import re
import threading
from functools import wraps
from logging.config import dictConfig

from connect.config import Config
from connect.logger import logger

# Configure logging
if os.path.exists('/etc/cloudblue-connector/config-logging.json'):
    with open('/etc/cloudblue-connector/config-logging.json') as config_log_file:
        settings = json.load(config_log_file)
        dictConfig(settings['logging'])

# Set connect log level / default level ERROR
logger.setLevel('DEBUG')

context_data = threading.local()
context_data.request_id = None


class ContextFilter(logging.Filter):
    """
    This is a filter which injects contextual information into the log record.
    """

    def filter(self, record):
        if context_data.request_id:
            record.name += "." + context_data.request_id
        return True


class PasswordFilter(logging.Filter):
    """
    This is a filter which wipes password information from the log record.
    """

    is_enabled = None

    type_pattern = re.compile(r'"type":\s?"password"', re.MULTILINE)
    password_patterns = [
        re.compile(r'^Function\s`.*?`\sreturn:\s\(u?\'(.*)\',\s\d+\)$', re.MULTILINE + re.DOTALL),
        re.compile(r'^Function\s`.*?`\sreturn:\s(.*)$', re.MULTILINE + re.DOTALL),
    ]

    def filter(self, record):
        def get_function_rv():
            if PasswordFilter.is_enabled is None:
                PasswordFilter.is_enabled = Config.get_instance().misc['hidePasswordsInLog']
            if PasswordFilter.is_enabled and re.search(PasswordFilter.type_pattern, record.msg):
                msg = record.msg.replace("\n", "\\n").replace("\\'", "'")
                for pattern in PasswordFilter.password_patterns:
                    match = re.search(pattern, msg)
                    if match:
                        return match.group(1)
                logger.warning("Message does not match against password patterns")
            return None

        raw_json = get_function_rv()
        if not raw_json:
            return True

        try:
            raw_json = raw_json.replace("\\x", "\\u00")
            payload = json.loads(raw_json)
            if not isinstance(payload, list):
                payload = [payload]
            found_passwords = {}
            for node in payload:
                for params in node.get('params', []), node.get('asset', {}).get('params', []):
                    for p in params:
                        if p.get('type', None) == 'password' and p.get('value', None):
                            pwd = re.escape(p['value'])
                            if pwd not in found_passwords:
                                found_passwords[pwd] = ''
            record.msg = re.sub("|".join(found_passwords.keys()), "***hidden***", record.msg, flags=re.M)
        except ValueError:
            logger.exception("Cannot deserialize API payload. Raw data: %s", raw_json)
        except Exception:
            logger.exception("Cannot patch API payload")
        return True


def getLogger(name):
    log = logging.getLogger(name)
    log.setLevel('DEBUG')
    log.addFilter(ContextFilter())
    return log


def context_log(func):
    """Store and clean context for logging"""

    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        context_data.request_id = request.id
        result = func(self, request, *args, **kwargs)
        context_data.request_id = None
        return result
    return wrapper


# Add context filter to external loggers
ext_loggers = ["keystoneauth.session", "decorators"]
for logger_name in ext_loggers:
    ext_logger = logging.getLogger(logger_name)
    ext_logger.addFilter(ContextFilter())

# Add filters to root logger
logger.addFilter(ContextFilter())
logger.addFilter(PasswordFilter())
