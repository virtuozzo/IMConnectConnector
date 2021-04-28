# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from datetime import datetime, timedelta

windows_vms = [
    {"display_name": "vm1",
     "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T17:06:26+00:00",
     "deleted_at": None},
    {"display_name": "vm2",
     "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T01:26:26+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=3)).strftime(
         '%Y-%m-%d') + "T03:36:26+00:00"},
    {"display_name": "vm3",
     "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T02:57:26+00:00",
     "deleted_at": None},
    {"display_name": "vm4",
     "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T22:57:26+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime(
         '%Y-%m-%d') + "T19:01:26+00:00"},
    {"display_name": "vm5",
     "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T09:32:26+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime(
         '%Y-%m-%d') + "T14:59:26+00:00"},
    {"display_name": "vm6",
     "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T11:12:26+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=3)).strftime(
         '%Y-%m-%d') + "T04:01:26+00:00"},
    {"display_name": "vm7",
     "created_at": (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d') + "T05:12:26+00:00",
     "deleted_at": None},
    {"display_name": "vm8",
     "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T23:50:26+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=5)).strftime(
         '%Y-%m-%d') + "T23:59:26+00:00"},
    {"display_name": "vm9",
     "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T23:50:26+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime(
         '%Y-%m-%d') + "T23:59:00+00:00"},
    {"display_name": "vm10",
     "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T21:59:58+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime(
         '%Y-%m-%d') + "T23:59:59+00:00"},
    {"display_name": "vm11",
     "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T00:00:00+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=3)).strftime(
         '%Y-%m-%d') + "T00:00:00+00:00"},
    {"display_name": "vm12",
     "created_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T20:50:00+00:00",
     "deleted_at": (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d') + "T22:51:00+00:00"}
]

images_list = [
    {'os_type': 'other', 'id': '11111111-1111-1111-1111-111111111111'},
    {'os_type': 'linux', 'id': '11111111-1111-1111-1111-111111111112'},
    {'os_type': 'windows', 'id': '11111111-1111-1111-1111-111111111113'}
]
