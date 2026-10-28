import tempfile
import unittest
from pathlib import Path

from backend.package import APP_FILES, MODEL_FILES, backend_requirements, build


class PackageTests(unittest.TestCase):
    def test_only_backend_dependencies_from_single_source(self):
        result = backend_requirements("""# [edge]
paho-mqtt==1.6.1
# [backend]
# Backend comment
azure-functions>=1.21,<2
psycopg2-binary>=2.9.10,<3
# [research]
xgboost>=3.0,<4
""")
        self.assertIn("azure-functions", result)
        self.assertIn("psycopg2-binary", result)
        self.assertNotIn("paho-mqtt", result)
        self.assertNotIn("xgboost", result)

    def test_missing_section_fails_instead_of_empty_deploy(self):
        with self.assertRaises(ValueError):
            backend_requirements("numpy\n")

    def test_artifact_excludes_secrets_and_refuses_unexpected_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'experiments/results').mkdir(parents=True)
            for name in MODEL_FILES:
                (root / 'experiments/results' / name).write_text('{}')
            for name in APP_FILES:
                path = root / "backend" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            (root / "requirements.txt").write_text("# [backend]\nazure-functions\n")
            (root / "backend/local.settings.json").write_text("private-settings")
            (root / ".env.local").write_text("private-credentials")
            target = build(root)
            self.assertEqual(build(root), target)
            self.assertFalse((target / "local.settings.json").exists())
            self.assertFalse((target / ".env.local").exists())
            extra = target / "private.txt"
            extra.write_text("do not delete")
            with self.assertRaises(ValueError):
                build(root)
            self.assertEqual(extra.read_text(), "do not delete")
