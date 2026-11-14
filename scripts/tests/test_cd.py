"""Offline deployment policy checks; no Git, SSH, or Docker execution."""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class ContinuousDeploymentTests(unittest.TestCase):
    def workflow(self):
        path = ROOT / ".github/workflows/cd.yml"
        self.assertTrue(path.is_file(), "manual CD workflow missing")
        # BaseLoader keeps YAML 1.1's 'on' key as a string.
        return yaml.load(path.read_text(), Loader=yaml.BaseLoader)

    def test_manual_main_only_with_production_approval(self):
        workflow = self.workflow()
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(workflow["concurrency"], {
            "group": "deploy-production", "cancel-in-progress": "false",
        })
        deploy = workflow["jobs"]["deploy"]
        self.assertEqual(deploy["environment"], "production")
        self.assertIn("github.ref == 'refs/heads/main'", deploy["if"])

    def test_actions_pinned_to_existing_ci_shas(self):
        workflow = self.workflow()
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        actions = [step for step in workflow["jobs"]["deploy"]["steps"] if "uses" in step]
        self.assertTrue(actions)
        for step in actions:
            self.assertRegex(step["uses"], r"^[\w/-]+@[0-9a-f]{40}$")
            self.assertIn(step["uses"], ci)
            if step["uses"].startswith("actions/checkout@"):
                self.assertEqual(step["with"]["fetch-depth"], "0")
                self.assertEqual(step["with"]["persist-credentials"], "false")

    def test_forced_command_never_executes_original_command(self):
        path = ROOT / "scripts/ci-deploy.sh"
        self.assertTrue(path.is_file(), "forced-command receiver missing")
        script = path.read_text()
        self.assertIn("set -euo pipefail", script)
        references = [line.strip() for line in script.splitlines()
                      if re.search(r"\$(?:SSH_ORIGINAL_COMMAND|\{SSH_ORIGINAL_COMMAND)", line)]
        self.assertTrue(references)
        self.assertTrue(all(line.startswith('if [[ -n "${SSH_ORIGINAL_COMMAND:-}" ]]')
                            for line in references), references)
        self.assertNotRegex(script, r"\b(eval|bash -c|sh -c|source)\b")


if __name__ == "__main__":
    unittest.main()
