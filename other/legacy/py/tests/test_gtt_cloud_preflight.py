import copy
import unittest

from deploy.gttgames.aws.cloud_preflight import Aws, inspect


class CloudPreflightTests(unittest.TestCase):
    def setUp(self):
        self.environment = {'account_id': '123456789012', 'region': 'us-east-1', 'instance_id': 'i-fixture',
            'vpc_id': 'vpc-fixture', 'instance_security_group_id': 'sg-fixture',
            'alb_subnets': ['subnet-a', 'subnet-d'], 'domain_name': 'gttgames.com'}
        self.data = {
            ('sts', 'get-caller-identity'): {'Account': '123456789012'},
            ('ec2', 'describe-instances'): {'Reservations': [{'Instances': [{'InstanceId': 'i-fixture',
                'VpcId': 'vpc-fixture', 'SubnetId': 'subnet-d', 'State': {'Name': 'running'},
                'Placement': {'AvailabilityZone': 'us-east-1d'}, 'SecurityGroups': [{'GroupId': 'sg-fixture'}],
                'BlockDeviceMappings': [{'Ebs': {'VolumeId': 'vol-fixture'}}]}]}]},
            ('ec2', 'describe-subnets'): {'Subnets': [{'SubnetId': 'subnet-' + zone, 'VpcId': 'vpc-fixture',
                'AvailabilityZone': 'us-east-1' + zone, 'CidrBlock': '172.31.' + str(index * 16) + '.0/20',
                'AvailableIpAddressCount': 100, 'State': 'available'} for index, zone in enumerate(('a', 'd'))]},
            ('ec2', 'describe-route-tables'): {'RouteTables': [{'RouteTableId': 'rtb-fixture',
                'Associations': [{'Main': True}], 'Routes': [
                    {'DestinationCidrBlock': '172.31.0.0/16', 'GatewayId': 'local', 'State': 'active'},
                    {'DestinationCidrBlock': '0.0.0.0/0', 'GatewayId': 'igw-fixture', 'State': 'active'}]}]},
            ('ec2', 'describe-internet-gateways'): {'InternetGateways': [{'InternetGatewayId': 'igw-fixture'}]},
            ('ec2', 'describe-managed-prefix-lists'): {'PrefixLists': [{'PrefixListId': 'pl-fixture'}]},
            ('ec2', 'describe-volumes'): {'Volumes': [{'VolumeId': 'vol-fixture', 'VolumeType': 'gp3', 'Size': 100, 'Encrypted': True}]},
            ('ec2', 'describe-security-groups'): {'SecurityGroups': [{'GroupId': 'sg-fixture'}]},
            ('ec2', 'describe-network-acls'): {'NetworkAcls': [{'NetworkAclId': 'acl-fixture',
                'Associations': [{'SubnetId': 'subnet-a'}, {'SubnetId': 'subnet-d'}], 'Entries': [
                    {'Egress': flag, 'RuleNumber': 100, 'RuleAction': 'allow', 'Protocol': '-1', 'CidrBlock': '0.0.0.0/0'} for flag in (False, True)]}]},
            ('acm', 'describe-certificate'): {'Certificate': {'Status': 'ISSUED', 'DomainName': 'gttgames.com',
                'SubjectAlternativeNames': ['gttgames.com', '*.gttgames.com']}}}

    def aws(self, service, action, *arguments):
        return copy.deepcopy(self.data[(service, action)])

    def test_valid_existing_instance_and_public_subnets_export_parameters(self):
        arn = 'arn:aws:acm:us-east-1:123456789012:certificate/11111111-1111-4111-8111-111111111111'
        result = inspect(self.aws, self.environment, arn)
        self.assertEqual(result['status'], 'passed')
        self.assertTrue(result['read_only'])
        values = {row['ParameterKey']: row['ParameterValue'] for row in result['foundation_parameters']}
        self.assertEqual(values['InstanceId'], 'i-fixture')
        self.assertEqual(values['CloudFrontPrefixListId'], 'pl-fixture')
        self.assertEqual(values['CertificateArn'], arn)

    def test_wrong_account_stops_before_reading_other_resources(self):
        self.data[('sts', 'get-caller-identity')]['Account'] = '999999999999'
        with self.assertRaisesRegex(ValueError, 'account differs'):
            inspect(self.aws, self.environment)

    def test_missing_public_default_route_is_rejected(self):
        self.data[('ec2', 'describe-route-tables')]['RouteTables'][0]['Routes'][1]['GatewayId'] = 'nat-fixture'
        with self.assertRaisesRegex(ValueError, 'default route'):
            inspect(self.aws, self.environment)

    def test_insufficient_ip_capacity_is_rejected(self):
        self.data[('ec2', 'describe-subnets')]['Subnets'][0]['AvailableIpAddressCount'] = 7
        with self.assertRaisesRegex(ValueError, 'free-IP'):
            inspect(self.aws, self.environment)

    def test_unencrypted_volume_requires_review_without_modifying_it(self):
        self.data[('ec2', 'describe-volumes')]['Volumes'][0]['Encrypted'] = False
        result = inspect(self.aws, self.environment)
        self.assertEqual(result['status'], 'review_required')
        self.assertFalse(result['volumes'][0]['Encrypted'])

    def test_mutation_is_rejected_before_starting_aws_cli(self):
        with self.assertRaisesRegex(ValueError, 'Read-only'):
            Aws('us-east-1')('ec2', 'modify-instance-attribute')


if __name__ == '__main__':
    unittest.main()
