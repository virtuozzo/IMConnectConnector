# coding=utf-8
# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

LOGS_DATA = {
    'log_messages': [
        u'Function `ApiClient.get` return: (u\'[{"params": [{"value": "1q2w3e","type": "password","id": "password"}]},'
        u'{"params": [{"value": "1q2w3e`$%()","type": "password","id": "password"}]}]\', 200)',
        u'Function `ApiClient.post` return: (u\'{"asset": {"params": [{"value": "1q2w3e","type": "password",'
        u'"id": "password"}]}}\', 200)',
        u'Function `ApiClient.get` return: (u\'[{"params": [{"id": "password","type": "password",'
        u'"value": "1q2w3e"}]}]\', 200)',
        u'Function `ApiClient.get` return: (u\'[{"params": [{"id": "I\'m not deserializable JSON",'
        u'"type": "password"},]}]\', 200)',
        u'return: (u\'[{"params": [{"id": "I\'m JSON not matching against password patterns",'
        u'"type": "password"}]}]\', 200)',
        u'Function `ApiClient.post` return: (u\'{"asset": {"params": [{"id": "password","type": "password",'
        u'"value": "1q2w3e"}]},"activation_key": "Virtual Datacenter \\n\\nLink: \\nPassword: 1q2w3e",'
        u'"template": {"message": "Virtual Datacenter \\n\\nLink: \\nPassword: 1q2w3e"}}\', 200)',
        u'Function `FulfillmentAutomation.dispatch` return: [{"activation_key": '
        u'"Virtual Datacenter \\n\\nLink: \\nPassword: 1q2w3e6y","asset": {"params": [{"value": "1q2w3e6y",'
        u'"type": "password","id": "password"}]},"template": {"message": '
        u'"Virtual Datacenter \\n\\nLink: \\nPassword: 1q2w3e6y"}}]',
        u'Function `FulfillmentAutomation.approve` return: {"asset": {"params": [{"id": "password",'
        u'"type": "password","value": "1q2w3e"}]}}',
        u'Function `ApiClient.get` return: (u\'[{"params": [{"value": "1q2w3e","type": "password",'
        u'"id": "password"}]},{"params": [{"value": "1q2w3e5t","type": "password","id": "password"}]},'
        u'{"params": [{"value": "1q2w3e6y","type": "password","id": "password"}]}]\', 200)',
        u'Function `ApiClient.put` return: (u\'{"tiers":{"customer":{"name":"Ols\xf8n LLC",'
        u'"contact_info":{"address_line1":"Jackson Cl\xf9b","address_line2":"L\xeahner Wells","city":"Amap\xe3",'
        u'"state":"Amap\xe3","contact":{"first_name":"Ladar\xefus","last_name":"Wehn\xf6r"}}}},'
        u'"asset": {"params": [{"id": "password","type": "password","value": "1q2w3e"}]}}\', 200)',
        u'Function `ApiClient.put` return: (\'{"tiers":{"customer":{"name":"Olsøn LLC",'
        u'"contact_info":{"address_line1":"Jackson Clùb","address_line2":"Lêhner Wells","city":"Amapã",'
        u'"state":"Amapã","contact":{"first_name":"Ladarïus","last_name":"Wehnör"}}}},'
        u'"asset": {"params": [{"id": "password","type": "password","value": "1q2w3e"}]}}\', 200)'

    ],
    'log_passwords': ['1q2w3e', '1q2w3e`$%()', '1q2w3e5t', '1q2w3e6y'],
}

__all__ = [
    'LOGS_DATA'
]
