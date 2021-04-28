# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

log_messages = [
    u'Function `ApiClient.get` return: (u\'[{"params": [{"value": "1q2w3e","type": "password","id": "password"}]},{"params": [{"value": "1q2w3e`$%()","type": "password","id": "password"}]}]\', 200)',
    u'Function `ApiClient.post` return: (u\'{"asset": {"params": [{"value": "1q2w3e","type": "password","id": "password"}]}}\', 200)',
    u'Function `ApiClient.get` return: (u\'[{"params": [{"id": "password","type": "password","value": "1q2w3e"}]}]\', 200)',
    u'Function `ApiClient.get` return: (u\'[{"params": [{"id": "I\'m not deserializable JSON","type": "password"},]}]\', 200)',
    u'return: (u\'[{"params": [{"id": "I\'m JSON not matching against password patterns","type": "password"}]}]\', 200)',
    u'Function `ApiClient.post` return: (u\'{"asset": {"params": [{"id": "password","type": "password","value": "1q2w3e"}]},"activation_key": "Virtual Datacenter \\n\\nLink: \\nPassword: 1q2w3e","template": {"message": "Virtual Datacenter \\n\\nLink: \\nPassword: 1q2w3e"}}\', 200)',
    u'Function `FulfillmentAutomation.dispatch` return: [{"activation_key": "Virtual Datacenter \\n\\nLink: \\nPassword: 1q2w3e6y","asset": {"params": [{"value": "1q2w3e6y","type": "password","id": "password"}]},"template": {"message": "Virtual Datacenter \\n\\nLink: \\nPassword: 1q2w3e6y"}}]',
    u'Function `FulfillmentAutomation.approve` return: {"asset": {"params": [{"id": "password","type": "password","value": "1q2w3e"}]}}',
    u'Function `ApiClient.get` return: (u\'[{"params": [{"value": "1q2w3e","type": "password","id": "password"}]},{"params": [{"value": "1q2w3e5t","type": "password","id": "password"}]},{"params": [{"value": "1q2w3e6y","type": "password","id": "password"}]}]\', 200)',
]

log_passwords = ['1q2w3e', '1q2w3e`$%()', '1q2w3e5t', '1q2w3e6y']
