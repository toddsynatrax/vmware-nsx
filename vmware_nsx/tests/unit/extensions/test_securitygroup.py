# Copyright (c) 2015 VMware, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import mock

from neutron.extensions import securitygroup as ext_sg
from neutron.tests.unit.extensions import test_securitygroup as test_ext_sg

from vmware_nsx.plugins.nsx_v3 import plugin as nsx_plugin
from vmware_nsx.tests.unit.nsx_v3 import test_plugin as test_nsxv3
from vmware_nsxlib.v3 import exceptions as nsxlib_exc
from vmware_nsxlib.v3 import nsx_constants as consts


# Pool of fake ns-groups uuids
NSG_IDS = ['11111111-1111-1111-1111-111111111111',
           '22222222-2222-2222-2222-222222222222',
           '33333333-3333-3333-3333-333333333333',
           '44444444-4444-4444-4444-444444444444',
           '55555555-5555-5555-5555-555555555555']


def _mock_create_and_list_nsgroups(test_method):
    nsgroups = []

    def _create_nsgroup_mock(name, desc, tags, membership_criteria=None):
        nsgroup = {'id': NSG_IDS[len(nsgroups)],
                   'display_name': name,
                   'description': desc,
                   'tags': tags}
        nsgroups.append(nsgroup)
        return nsgroup

    def wrap(*args, **kwargs):
        with mock.patch(
            'vmware_nsxlib.v3.security.NsxLibNsGroup.create'
        ) as create_nsgroup_mock:
            create_nsgroup_mock.side_effect = _create_nsgroup_mock
            with mock.patch(
                "vmware_nsxlib.v3.security.NsxLibNsGroup.list"
            ) as list_nsgroups_mock:
                list_nsgroups_mock.side_effect = lambda: nsgroups
                test_method(*args, **kwargs)
    return wrap


class TestSecurityGroups(test_nsxv3.NsxV3PluginTestCaseMixin,
                         test_ext_sg.TestSecurityGroups):
    pass


class TestSecurityGroupsNoDynamicCriteria(test_nsxv3.NsxV3PluginTestCaseMixin,
                                          test_ext_sg.TestSecurityGroups):

    def setUp(self):
        super(TestSecurityGroupsNoDynamicCriteria, self).setUp()
        mock_nsx_version = mock.patch.object(nsx_plugin.utils,
                                             'is_nsx_version_1_1_0',
                                             new=lambda v: False)
        mock_nsx_version.start()
        self._patchers.append(mock_nsx_version)

    @_mock_create_and_list_nsgroups
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.remove_member')
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.add_members')
    def test_create_port_with_multiple_security_groups(self,
                                                       add_member_mock,
                                                       remove_member_mock):
        super(TestSecurityGroupsNoDynamicCriteria,
              self).test_create_port_with_multiple_security_groups()

        # The first nsgroup is associated with the default secgroup, which is
        # not added to this port.
        calls = [mock.call(NSG_IDS[1],
                           consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY),
                 mock.call(NSG_IDS[2],
                           consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY)]
        add_member_mock.assert_has_calls(calls, any_order=True)

    @_mock_create_and_list_nsgroups
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.remove_member')
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.add_members')
    def test_update_port_with_multiple_security_groups(self,
                                                       add_member_mock,
                                                       remove_member_mock):
        super(TestSecurityGroupsNoDynamicCriteria,
              self).test_update_port_with_multiple_security_groups()

        calls = [mock.call(NSG_IDS[0],
                           consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY),
                 mock.call(NSG_IDS[1],
                           consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY),
                 mock.call(NSG_IDS[2],
                           consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY)]
        add_member_mock.assert_has_calls(calls, any_order=True)

        remove_member_mock.assert_called_with(
            NSG_IDS[0], consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY)

    @_mock_create_and_list_nsgroups
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.remove_member')
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.add_members')
    def test_update_port_remove_security_group_empty_list(self,
                                                          add_member_mock,
                                                          remove_member_mock):
        super(TestSecurityGroupsNoDynamicCriteria,
              self).test_update_port_remove_security_group_empty_list()

        add_member_mock.assert_called_with(
            NSG_IDS[1], consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY)
        remove_member_mock.assert_called_with(
            NSG_IDS[1], consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY)

    @_mock_create_and_list_nsgroups
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.add_members')
    def test_create_port_with_full_security_group(self, add_member_mock):

        def _add_member_mock(nsgroup, target_type, target_id):
            if nsgroup in NSG_IDS:
                raise nsxlib_exc.NSGroupIsFull(nsgroup_id=nsgroup)
        add_member_mock.side_effect = _add_member_mock

        with self.network() as net:
            with self.subnet(net):
                res = self._create_port(self.fmt, net['network']['id'])
                res_body = self.deserialize(self.fmt, res)

        self.assertEqual(500, res.status_int)
        self.assertEqual('SecurityGroupMaximumCapacityReached',
                         res_body['NeutronError']['type'])

    @_mock_create_and_list_nsgroups
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.remove_member')
    @mock.patch('vmware_nsxlib.v3.security.NsxLibNsGroup.add_members')
    def test_update_port_with_full_security_group(self,
                                                  add_member_mock,
                                                  remove_member_mock):
        def _add_member_mock(nsgroup, target_type, target_id):
            if nsgroup == NSG_IDS[2]:
                raise nsxlib_exc.NSGroupIsFull(nsgroup_id=nsgroup)
        add_member_mock.side_effect = _add_member_mock

        with self.port() as port:
            with self.security_group() as sg1:
                with self.security_group() as sg2:
                    data = {'port': {ext_sg.SECURITYGROUPS:
                                     [sg1['security_group']['id'],
                                      sg2['security_group']['id']]}}
                    req = self.new_update_request(
                        'ports', data, port['port']['id'])
                    res = req.get_response(self.api)
                    res_body = self.deserialize(self.fmt, res)

        self.assertEqual(500, res.status_int)
        self.assertEqual('SecurityGroupMaximumCapacityReached',
                         res_body['NeutronError']['type'])

        # Because the update has failed we excpect that the plugin will try to
        # revert any changes in the NSGroups - It is required to remove the
        # lport from any NSGroups which it was added to during that call.
        calls = [mock.call(NSG_IDS[1],
                           consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY),
                 mock.call(NSG_IDS[2],
                           consts.TARGET_TYPE_LOGICAL_PORT, mock.ANY)]
        remove_member_mock.assert_has_calls(calls, any_order=True)

    def test_create_security_group_rule_icmpv6_legacy_protocol_name(self):
        self.skipTest('not supported')
