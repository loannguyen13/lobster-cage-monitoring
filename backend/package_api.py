"""Build a secret-free ZIP for App Service from the single root requirements.txt."""
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    '__init__.py', 'database.py', 'api/__init__.py', 'api/main.py', 'api/auth.py',
    'api/routes.py', 'api/schemas.py', 'services/__init__.py', 'services/accounts.py',
    'services/audit.py', 'certs/azure-postgresql-roots.pem',
)
PACKAGES = {'psycopg2-binary','fastapi','pyjwt','pwdlib','uvicorn'}


def api_requirements(content):
    selected = {}
    for line in content.splitlines():
        line = line.strip()
        match = re.match(r'^([a-zA-Z0-9_-]+)',line)
        if match and match[1].lower() in PACKAGES:
            name = match[1].lower()
            if name in selected:
                raise ValueError(f'Duplicate API dependency: {name}')
            selected[name] = line
    if selected.keys() != PACKAGES:
        raise ValueError('Missing API dependencies in root requirements.txt')
    return '# Generated from root requirements.txt; do not edit.\n' + '\n'.join(selected.values()) + '\n'


def build(root=ROOT):
    root = Path(root).resolve()
    target = root / '.runtime' / 'dashboard-api.zip'
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError('Artifact must stay inside repository')
    requirements = api_requirements((root / 'requirements.txt').read_text(encoding='utf-8'))
    for name in FILES:
        if not (root / 'backend' / name).is_file():
            raise FileNotFoundError(name)
    target.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(root / 'backend' / name, 'backend/' + name)
        archive.writestr('requirements.txt',requirements)
    return target


if __name__ == '__main__':
    print(build())
