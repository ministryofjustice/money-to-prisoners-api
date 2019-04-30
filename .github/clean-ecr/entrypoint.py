#!/usr/bin/env python
import configparser
import json
import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


def clean_ecr():
    app = get_app_name()
    branch = get_pull_request_branch()
    prefix = f'{app}.{branch}.'
    digests = aws_ecr([
        'describe-images',
        '--repository-name', 'prisoner-money/money-to-prisoners',
        '--query', f"imageDetails[?contains(map(&starts_with(@, '{prefix}'), @.imageTags), `true`)].imageDigest",
    ])
    if digests:
        logger.info(f'Deleting {len(digests)} image(s) tagged {prefix}*')
        aws_ecr([
            'batch-delete-image',
            '--repository-name', 'prisoner-money/money-to-prisoners',
            '--image-ids', *[f'imageDigest={digest}' for digest in digests]
        ])
    else:
        logger.info(f'No images tagged {prefix}*')


def get_app_name():
    config_parser = configparser.ConfigParser()
    assert config_parser.read('setup.cfg'), 'Cannot load app settings file'
    return config_parser['mtp']['app'].replace('_', '-')


def get_pull_request_branch():
    event_path = os.environ['GITHUB_EVENT_PATH']
    with open(event_path) as f:
        event_data = json.load(f)
    pull_request = event_data['pull_request']
    head_branch = pull_request.get('head', {}).get('ref')
    assert head_branch, 'Cannot determine branch'
    default_branch = pull_request.get('repository', {}).get('default_branch')
    protected_branches = {'master', default_branch}
    assert head_branch not in protected_branches, f'Branch {head_branch} is protected'
    return head_branch


def aws_ecr(args):
    process = subprocess.run(['aws', 'ecr'] + args, stdout=subprocess.PIPE, check=True)
    return json.loads(process.stdout)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        clean_ecr()
    except AssertionError as e:
        logger.error(str(e))
        sys.exit(1)
