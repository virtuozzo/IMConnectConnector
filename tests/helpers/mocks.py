# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import logging

import pytest

from tests.helpers.fake_methods import make_fake_mock_method, make_fake_mock_parametrized_method

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


class ClientAttrMock(object):

    def __init__(self, parent_name, name, data):
        self._parent_name = parent_name
        self._name = name
        self._data = data

    def __getattr__(self, item):
        key = '{}.{}'.format(self._name, item)
        result = None
        if key in self._data:
            result = self._data[key]
        elif any([_.startswith(key) for _ in self._data]):
            result = ClientAttrMock(self._name, item, self._data)
        else:
            pytest.fail('"{}.{}" not mocked.'.format(self._parent_name, key))
        LOG.info('KEY: %r -> %r', key, result)
        return result


class OpenstackClientMock(object):

    def __init__(self, name, fake_methods=None, fake_attrs=None):
        self._name = name

        if fake_attrs is None:
            fake_attrs = ()
        if fake_methods is None:
            fake_methods = ()

        _data = {}
        if isinstance(fake_methods, dict):
            fake_methods = tuple(fake_methods.items())
        for fake_method_path, method_result in fake_methods:
            _data[fake_method_path] = make_fake_mock_method(
                fake_method_path, method_result)
        for fake_attr_name, fake_attr_result in fake_attrs:
            _data[fake_attr_name] = fake_attr_result
        self._data = _data

    def __getattr__(self, item):
        default = ClientAttrMock(self._name, item, self._data)
        return self._data.get(item, default) if self._data else default


class OpenstackClientParametrizedMock(OpenstackClientMock):

    def __init__(self, name, fake_parametrized_methods=None, fake_attrs=None):
        super(OpenstackClientParametrizedMock, self).__init__(name, None, fake_attrs)

        if fake_parametrized_methods is None:
            fake_parametrized_methods = ()

        if isinstance(fake_parametrized_methods, dict):
            fake_parametrized_methods = tuple(fake_parametrized_methods.items())
        for fake_method_path, method_parametrized_result in fake_parametrized_methods:
            self._data[fake_method_path] = make_fake_mock_parametrized_method(
                fake_method_path, method_parametrized_result)
