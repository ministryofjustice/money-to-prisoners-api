import json
from pathlib import Path
import shlex
import unittest

import yaml


class MigrationDeploymentTests(unittest.TestCase):
    def test_test_deploy_limits_only_the_migration_container(self):
        root = Path(__file__).resolve().parents[4]
        workflow = yaml.safe_load((root / '.github/workflows/build-test-push.yml').read_text())
        deploy = next(
            step
            for job in workflow['jobs'].values()
            for step in job.get('steps', [])
            if step.get('name') == 'Deploy to test'
        )
        self.assertNotIn('PGOPTIONS', deploy['env'])
        patch_line = next(
            line for line in deploy['run'].splitlines() if line.startswith('kubectl patch deployment api ')
        )
        args = shlex.split(patch_line)
        spec = json.loads(args[args.index('--patch') + 1])['spec']['template']['spec']
        for container in spec['containers'] + spec['initContainers']:
            with self.subTest(container=container['name']):
                if container['name'] == 'init':
                    self.assertEqual(container['env'], [{'name': 'PGOPTIONS', 'value': '-c lock_timeout=5s'}])
                else:
                    self.assertNotIn('env', container)
