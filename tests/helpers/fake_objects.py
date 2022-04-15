# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import logging

import pytest
from marshmallow.fields import String, Integer, Nested

from tests.data import SUPPORTED_DEFAULTS_KEY_TYPE

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


class FakeBaseObject(object):

    def __init__(self, **kwargs):
        self._data = kwargs

    def __getitem__(self, item):
        return self._data[item]

    def __getattr__(self, item):
        if item not in self._data:
            raise AttributeError
        return self._data[item]

    def update(self, **kwargs):
        self._data.update(kwargs)
        return self

    def to_dict(self):
        return self._data

    def __repr__(self):
        return '{self.__class__.__name__}(data={self._data})'.format(self=self)


class FakeProject(FakeBaseObject):
    pass


class FakeQuotas(FakeBaseObject):
    pass


class FakeRole(FakeBaseObject):
    pass


class FakeDomain(FakeBaseObject):
    pass


class FakeUser(FakeBaseObject):
    pass


class FakeServer(FakeBaseObject):
    pass


def gen_fake_by_schema(schema, inners=None, defaults=None):
    """
    Generate fake dict by schema for responses content/data.

    :type schema: Schema
    :type inners: list
    :type defaults: dict
    :rtype: dict
    """

    def capitalize(chunk):
        return chunk.capitalize()

    if inners is None:
        inners = []
    if defaults is None:
        defaults = {}
    elif not isinstance(defaults, dict):
        pytest.fail('Incorrect defaults type. Must be dict.')
    else:
        incorrects = list(
            filter(lambda key: not isinstance(key, (list, tuple)), defaults)
        )
        if incorrects:
            LOG.warning(
                'Defaults have not list or tuple formatted key. '
                'Try to change the key. List of incorrect defaults: %s', incorrects
            )
        for incorrect in incorrects:
            if not isinstance(incorrect, SUPPORTED_DEFAULTS_KEY_TYPE):
                pytest.fail(
                    'Unable to prepare {!r} to correct tuple format, '
                    'which required for defaults dict. '
                    'Unsupported type: {!r}. Expected: {!r}'.format(
                        incorrect, type(incorrect), SUPPORTED_DEFAULTS_KEY_TYPE
                    )
                )
            else:
                value = defaults.pop(incorrect)
                defaults[(incorrect,)] = value

    fake_dict = {}
    for field_name, field in schema.fields.items():
        value = defaults.get(tuple(inners + [field_name]))
        if value:
            if value == 'None':
                value = None
            fake_dict[field_name] = value
            continue
        if isinstance(field, String):
            fake_dict[field_name] = "".join(
                ["Test"] + list(map(capitalize, field_name.split('_'))))
        elif isinstance(field, Integer):
            fake_dict[field_name] = 0
        elif isinstance(field, Nested):
            if field_name not in ['parent', 'agreements', 'children']:
                result = gen_fake_by_schema(
                    field.schema, inners=inners + [field_name, ],
                    defaults=defaults
                )
                if field.many:
                    fake_dict[field_name] = [result]
                else:
                    fake_dict[field_name] = result
    return fake_dict
