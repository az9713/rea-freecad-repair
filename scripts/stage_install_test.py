"""Install only into this checkout's isolated portable user Mod folder."""
from pathlib import Path
import zipfile
ROOT = Path(__file__).resolve().parents[1]
target = ROOT / '.runtime/home/FreeCAD/Mod'
target.mkdir(parents=True, exist_ok=True)
candidate = ROOT / 'artifacts/TopoIntent-0.1.0-candidate.zip'
archive = candidate if candidate.exists() else ROOT / 'artifacts/TopoIntent-0.1.0-workbench.zip'
with zipfile.ZipFile(archive) as release:
    for name in release.namelist():
        if not (target / name).resolve().is_relative_to(target.resolve()):
            raise RuntimeError('ZIP member escapes isolated install root')
    release.extractall(target)
print('Staged release ZIP under .runtime/home/FreeCAD/Mod/TopoIntent')
