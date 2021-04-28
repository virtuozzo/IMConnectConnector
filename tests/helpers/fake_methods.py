# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import functools
import logging

import pytest

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def make_fake_apimethod(method, fakes_responses):
    """
    Wrapper for ApiClient method.

    :type method: str
    :type fakes_responses: dict
    """

    def fake_apimethod(api, path='', **kwargs):
        LOG.info(
            'ApiClient.%r(api=%r, base_path=%r, path=%r, kwargs=%r)',
            method, api, api.base_path, path, kwargs
        )
        key = (api.base_path, path)
        try:
            return fakes_responses[key]
        except KeyError:
            pytest.fail(
                'Request({!r}) to {!r} not found in fakes_responses: '
                '{!r}'.format(method, key, fakes_responses)
            )

    return fake_apimethod


def make_fake_mock_method(name, method_result):
    def fake_method(*args, **kwargs):
        LOG.info(
            '%s(args=%r, kwargs=%r) -> %r', name, args, kwargs, method_result
        )
        return method_result

    return fake_method


def make_fake_mock_parametrized_method(name, method_parametrized_result):
    def fake_method(*args, **kwargs):
        method_result = None
        for search in method_parametrized_result.keys():
            if all(s in kwargs.items() for s in search):
                method_result = method_parametrized_result[search]
        LOG.info(
            '%s(args=%r, kwargs=%r) -> %r', name, args, kwargs, method_result
        )
        return method_result

    return fake_method


def process_request_wrapper(method, expected_exception=None, expected_value_checker=None):
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        try:
            value = method(*args, **kwargs)
            if expected_value_checker is not None:
                expected_value_checker(value)
            return value
        except Exception as ex:
            if expected_exception is None:
                pytest.fail(
                    'Unexpected error was raised ({!r}). '
                    'And not covered.'.format(ex)
                )
            elif not isinstance(ex, expected_exception):
                pytest.fail(
                    'Unexpected error was raised ({!r}). Expected: {!r}'.format(
                        ex, expected_exception
                    )
                )
            else:
                raise

    return wrapper


def make_value_type_checker(expected_type_instance):
    def wrp(value):
        if not isinstance(value, expected_type_instance):
            pytest.fail(
                'Unexpected instance ({!r} after execution. '
                'Expected: {!r}'.format(value, expected_type_instance)
            )

    return wrp
