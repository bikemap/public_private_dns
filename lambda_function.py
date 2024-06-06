import json
import logging
import socket

from typing import Iterator

import boto3

from botocore.config import Config

logger = logging.getLogger()
logger.setLevel("INFO")

boto_config = Config(region_name='eu-central-1')

event_client = boto3.client('events', config=boto_config)
route53_client = boto3.client('route53')


EVENT_NAME = ''
HOSTED_ZONE_ID = ''
DNS_MAPPING = {
    'public.example.com': 'private.example.com',
}


def update_target_input(target: dict[str, str], new_data: dict[str, dict[str, list[str]]]) -> None:
    input_data = json.dumps(new_data, separators=(',', ':'))
    targets = [{
        'Arn': target['Arn'],
        'Id': target['Id'],
        'Input': input_data
    }]

    logger.info(f'Updating input parameters to: {input_data}')

    event_client.put_targets(Rule=EVENT_NAME, Targets=targets)


def update_iteration(data: dict[str, dict[str, list[str]]]) -> None:
    targets = event_client.list_targets_by_rule(Rule=EVENT_NAME).get('Targets')

    if not targets:
        logger.error('No targets found')
        return

    if len(targets) > 1:
        logger.error(f'More than one target identified by rule {EVENT_NAME}')
        return

    update_target_input(targets[0], data)


def get_public_ip_mapping() -> dict[str, str]:
    public_ip_mapping = {}

    for public_dns in DNS_MAPPING:

        try:
            public_ips = socket.gethostbyname_ex(public_dns)[-1]
        except socket.gaierror as e:
            logger.error(e)
            logger.error(f'Could not resolve domain {public_dns}')

            continue

        if not public_ips:
            logger.error(f'Could not resolve domain {public_dns} as it does not resolve any ip addresses')
            continue

        public_ip_mapping.update({public_ip: public_dns for public_ip in public_ips})

    return public_ip_mapping


def get_address_mapping() -> dict[str, list[str]] | None:
    public_ip_mapping = get_public_ip_mapping()

    if not public_ip_mapping:
        logger.error('Could not resolve public dns')
        return

    ec2_client = boto3.client('ec2', config=boto_config)

    interfaces = ec2_client.describe_network_interfaces(
        Filters=[{'Name': 'association.public-ip', 'Values': list(public_ip_mapping)}]
    ).get('NetworkInterfaces')

    if not interfaces:
        public_ip_string = ', '.join([f'"{address}"' for address in public_ip_mapping])
        logger.error(f'Could not find any interfaces associated with public ips: {public_ip_string}')
        return

    address_mapping = {}

    for interface in interfaces:
        private_addresses = address_mapping.setdefault(public_ip_mapping[interface['Association']['PublicIp']], [])
        private_addresses.extend([address['PrivateIpAddress'] for address in interface['PrivateIpAddresses']])
        private_addresses.sort()

    return address_mapping


def parsed_address_mapping(mapping: dict[str, list[str]]) -> Iterator[tuple[str, tuple[str, ...]]]:
    for key, value in mapping.items():
        yield key, tuple(sorted(value))


def lambda_handler(event, context) -> None:
    logger.info(f'Received event with parameters: {json.dumps(event or {}, indent=2)}')
    old_address_mapping = event.get('old_address_mapping') or {}
    address_mapping = get_address_mapping()

    if not address_mapping:
        return

    dns_to_update = set(parsed_address_mapping(address_mapping)) - set(parsed_address_mapping(old_address_mapping))

    if not dns_to_update:
        logger.info(f'Private DNS entries are up to date!')
        return

    logger.info('Updating the following DNS entries')
    logger.info(dns_to_update)

    route53_client.change_resource_record_sets(
        HostedZoneId=HOSTED_ZONE_ID,
        ChangeBatch={
            'Changes': [
                {
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': DNS_MAPPING[public_dns],
                        'Type': 'A',
                        'TTL': 30,
                        'ResourceRecords': [{'Value': private_ip} for private_ip in private_ips],
                    }
                }
                for public_dns, private_ips in dns_to_update
            ]
        }
    )

    update_iteration({'old_address_mapping': address_mapping})
