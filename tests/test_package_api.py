import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from backend.package_api import FILES, api_requirements, build


class ApiPackageTests(unittest.TestCase):
    def test_zip_excludes_secrets_models_and_function(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in FILES:
                path = root / 'backend' / name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('fixture')
            (root / 'requirements.txt').write_text('psycopg2-binary\nfastapi\nPyJWT\npwdlib[argon2]\nuvicorn\nxgboost\nazure-functions\n')
            (root / '.env.local').write_text('secret')
            (root / 'backend/function_app.py').write_text('not an API dependency')
            with ZipFile(build(root)) as archive:
                self.assertEqual(set(archive.namelist()), {'requirements.txt', *(f'backend/{name}' for name in FILES)})
                requirements = archive.read('requirements.txt').decode()
                self.assertNotIn('xgboost',requirements)
                self.assertNotIn('azure-functions',requirements)
                self.assertIn('pwdlib[argon2]',requirements)

    def test_missing_dependency_fails(self):
        with self.assertRaises(ValueError):
            api_requirements('fastapi\n')
