"""Build a minimal Azure Function artifact from the root requirements.txt."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
APP_FILES = (
    "function_app.py", "host.json", "telemetry.py", "repository.py", ".funcignore", "__init__.py",
    "database.py", "ingestion.py", "services/__init__.py", "services/readings.py",
    "services/alerts.py", "services/audit.py", "api/__init__.py", "api/main.py",
    "api/routes.py", "api/auth.py", "api/schemas.py",
    "prediction_job.py", "services/predictions.py",
    "services/accounts.py",
    "certs/azure-postgresql-roots.pem",
)
MODEL_FILES = ('selected_horizon_model.json', 'experiment_metadata.json')


def backend_requirements(text):
    selected = []
    section = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# [") and stripped.endswith("]"):
            section = stripped[3:-1]
        elif section == "backend" and stripped and not stripped.startswith("#"):
            if stripped.startswith("-"):
                raise ValueError("Backend dependencies must be package specifications, not pip options")
            selected.append(stripped)
    if not selected:
        raise ValueError("Missing or empty # [backend] section in requirements.txt")
    return "# Generated from root requirements.txt; do not edit this build artifact.\n" + "\n".join(selected) + "\n"


def build(root=ROOT):
    root = Path(root).resolve()
    backend = root / "backend"
    target = root / ".runtime" / "function-app"
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError("Deployment directory must stay inside this repository")
    requirements = backend_requirements((root / "requirements.txt").read_text(encoding="utf-8"))
    for name in APP_FILES:
        if not (backend / name).is_file():
            raise FileNotFoundError(f"Missing backend/{name}; prepare certificates before packaging")
    for name in MODEL_FILES:
        if not (root / 'experiments/results' / name).is_file():
            raise FileNotFoundError(f'Missing model artifact: {name}')
    # Refuse unexpected files rather than accidentally deploying secrets or
    # deleting local work from an existing staging directory.
    def deployed(name):
        return name if name in ('function_app.py', 'host.json', '.funcignore') or name.startswith('certs/') else 'backend/' + name
    expected = {*(deployed(name) for name in APP_FILES), "requirements.txt",
                *(f'backend/models/{name}' for name in MODEL_FILES)}
    # Known files from the previous flat artifact can be safely removed after validation.
    legacy = {'telemetry.py', 'repository.py'}
    if target.exists():
        for path in target.rglob("*"):
            if path.is_symlink() or (path.is_file() and path.relative_to(target).as_posix() not in expected | legacy):
                raise ValueError(f"Unexpected staging file: {path}. Move it out before rebuilding.")
    target.mkdir(parents=True, exist_ok=True)
    for name in APP_FILES:
        destination = target / deployed(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backend / name, destination)
    for name in legacy:
        (target / name).unlink(missing_ok=True)
    (target / 'backend/models').mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        shutil.copyfile(root / 'experiments/results' / name, target / 'backend/models' / name)
    (target / "requirements.txt").write_text(requirements, encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build())
