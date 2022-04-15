# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import json
from datetime import datetime, timedelta

import dateutil.parser

responses = {}
with open('tests/data/json/response_traffic.json') as json_file:
    data = json.load(json_file)
    responses['response_traffic'] = data

aggregated_responses = ['response_memory', 'response_volume_size', 'response_volume_snapshot_size',
                        'response_ip_floating', 'response_coe_cluster', 'response_instance_vcpus',
                        'response_loadbalancer']
for response in aggregated_responses:
    with open('tests/data/json/' + response + '.json') as json_file:
        data = json.load(json_file)
        measures = []
        for m in data.get('measures').get('aggregated'):
            measures.append([dateutil.parser.parse(m[0]), m[1], m[2]])
        data['measures']['aggregated'] = measures
        responses[response] = data

GNOCCHI_MOCK_DATA = {
    'aggregates.fetch': {
        (): {
            (('resource_type', 'instance'),
             ('operations', '(aggregate sum (metric memory mean))'),):
                 responses['response_memory'],
            (('resource_type', 'volume'),
             ('operations', '(aggregate sum (metric volume.size mean))'),):
                 responses['response_volume_size'],
            (('resource_type', 'volume'),
             ('operations', '(aggregate sum (metric volume.snapshot.size mean))'),):
                 responses['response_volume_snapshot_size'],
            (('resource_type', 'network'),
             ('operations', '(aggregate count (metric ip.floating mean))'),):
                 responses['response_ip_floating'],
            (('resource_type', 'loadbalancer'),
             ('operations', '(aggregate count (metric network.services.lb.loadbalancer mean))'),):
                 responses['response_loadbalancer'],
            (('resource_type', 'coe_cluster'),
             ('operations', '(aggregate count (metric magnum.cluster mean))'),):
                 responses['response_coe_cluster'],
            (('resource_type', 'instance'),
             ('operations', '(aggregate sum (metric vcpus mean))')):
                 responses['response_instance_vcpus'],
            (('resource_type', 'generic'),
             ('operations', '(metric network.outgoing.bytes mean)'),
             ('search', 'id=11111111-1111-1111-1111-111111111113'),):
                 responses['response_traffic'],
        },
    },
}

GNOCCHI_TESTS_DATA = {
    'images_list': [
        {'os_type': 'other', 'id': '11111111-1111-1111-1111-111111111111'},
        {'os_type': 'linux', 'id': '11111111-1111-1111-1111-111111111112'},
        {'os_type': 'windows', 'id': '11111111-1111-1111-1111-111111111113'}
    ],
    'single_vm': [
        {"display_name": "vm1", "id": "11111111-1111-1111-1111-111111111111",
         "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T17:06:26+00:00",
         "deleted_at": None}
    ],
    'instance_network_interface': [{'id': '11111111-1111-1111-1111-111111111113'}],
    'windows_vms': [
        {"display_name": "vm1",
         "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T17:06:26+00:00",
         "deleted_at": None},
        {"display_name": "vm2",
         "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T01:26:26+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d') + "T03:36:26+00:00"},
        {"display_name": "vm3",
         "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T02:57:26+00:00",
         "deleted_at": None},
        {"display_name": "vm4",
         "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T22:57:26+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T19:01:26+00:00"},
        {"display_name": "vm5",
         "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T09:32:26+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T14:59:26+00:00"},
        {"display_name": "vm6",
         "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T11:12:26+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d') + "T04:01:26+00:00"},
        {"display_name": "vm7",
         "created_at": (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d') + "T05:12:26+00:00",
         "deleted_at": None},
        {"display_name": "vm8",
         "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T23:50:26+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T23:59:26+00:00"},
        {"display_name": "vm9",
         "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T23:50:26+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T23:59:00+00:00"},
        {"display_name": "vm10",
         "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T21:59:58+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T23:59:59+00:00"},
        {"display_name": "vm11",
         "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T00:00:00+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d') + "T00:00:00+00:00"},
        {"display_name": "vm12",
         "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T20:50:00+00:00",
         "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T22:51:00+00:00"}
    ]
}

__all__ = [
    'GNOCCHI_MOCK_DATA',
    'GNOCCHI_TESTS_DATA'
]
