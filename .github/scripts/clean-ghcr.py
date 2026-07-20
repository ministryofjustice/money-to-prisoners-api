#!/usr/bin/env python
"""
Delete this repository's branch images from GHCR once their pull request closes

Branch builds are tagged `[branch].[commit]` and are never deployed after the pull request
ends, but GHCR - unlike ECR - has no lifecycle policy, so nothing removes them otherwise.

Runs on the github runner with the repository's own GITHUB_TOKEN: a package can only be
administered by a token from the repository it is linked to.
"""
import json
import logging
import os
import sys
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

API_ROOT = 'https://api.github.com'


def clean_ghcr():
    organisation, package = os.environ['GITHUB_REPOSITORY'].split('/', 1)
    branch = get_pull_request_branch()
    prefix = f'{branch}.'

    versions = list_versions(organisation, package)
    logger.info(f'{package} has {len(versions)} version(s)')

    deletable = []
    for version_id, tags in versions:
        if not tags:
            # untagged versions are usually a superseded build or an attestation, but a
            # multi-arch child manifest is also untagged, so leave them to the base cleanup
            continue
        # every tag must belong to this branch: a digest also tagged `latest` is in use
        if all(tag.startswith(prefix) for tag in tags):
            deletable.append((version_id, tags))

    if not deletable:
        logger.info(f'No images tagged {prefix}*')
        return

    logger.info(f'Deleting {len(deletable)} image(s) tagged {prefix}*')
    for version_id, tags in deletable:
        logger.info(f'  {", ".join(tags)}')
        delete_version(organisation, package, version_id)


def get_pull_request_branch():
    """
    Branch of the closed pull request, named as the build tagged it

    NB: The build lowercases the branch before using it as a tag, so a branch like
    `IR-1234-something` is published as `ir-1234-something.[commit]` and only matches if
    lowercased here too.
    """
    with open(os.environ['GITHUB_EVENT_PATH']) as f:
        event_data = json.load(f)
    pull_request = event_data['pull_request']
    head_branch = pull_request.get('head', {}).get('ref')
    assert head_branch, 'Cannot determine branch'
    default_branch = pull_request.get('repository', {}).get('default_branch')
    protected_branches = {'main', default_branch}
    assert head_branch not in protected_branches, f'Branch {head_branch} is protected'
    return head_branch.lower()


def github_api(path, method='GET'):
    request = urllib.request.Request(f'{API_ROOT}{path}', method=method)
    request.add_header('Authorization', f'Bearer {os.environ["GITHUB_TOKEN"]}')
    request.add_header('Accept', 'application/vnd.github+json')
    request.add_header('X-GitHub-Api-Version', '2022-11-28')
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body.strip() else None


def list_versions(organisation, package):
    """
    Every version of the package, newest first, as (id, tags) pairs
    """
    versions, page = [], 1
    while True:
        body = github_api(
            f'/orgs/{organisation}/packages/container/{package}/versions?per_page=100&page={page}'
        )
        if not body:
            break
        versions.extend(
            (version['id'], version.get('metadata', {}).get('container', {}).get('tags') or [])
            for version in body
        )
        if len(body) < 100:
            break
        page += 1
    return versions


def delete_version(organisation, package, version_id):
    try:
        github_api(
            f'/orgs/{organisation}/packages/container/{package}/versions/{version_id}',
            method='DELETE',
        )
    except urllib.error.HTTPError as e:
        # github refuses to delete public package versions past a download threshold
        logger.warning(f'Could not delete version {version_id}: HTTP {e.code} {e.reason}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        clean_ghcr()
    except AssertionError as e:
        logger.error(str(e))
        sys.exit(1)
