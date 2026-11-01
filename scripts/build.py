"""Build an allowlisted, installable workbench ZIP; verify public source hashes."""
import hashlib
import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--candidate', action='store_true', help='Build a staging ZIP before installed-GUI verification; not a verified release')
candidate = parser.parse_args().candidate
ARTIFACTS = ROOT / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)
FILES = ['Init.py', 'InitGui.py', 'package.xml', 'LICENSE', 'NOTICE.md', 'README.md']
FILES += [str(p.relative_to(ROOT)).replace('\\', '/') for p in sorted((ROOT / 'topointent').glob('*.py'))]
manifest = json.loads((ROOT / 'investigation/public-source/manifest.json').read_text())
for item in manifest['files']:
    path = ROOT / item['path'].replace('\\', '/')
    if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise RuntimeError('Public source hash mismatch: ' + item['path'])
results_path = ARTIFACTS / 'integration-results.json'
if not results_path.exists():
    raise RuntimeError('Run real FreeCAD integration before packaging this verified release')
results = json.loads(results_path.read_text())
if results['passed'] != results['total'] or results['total'] < 7:
    raise RuntimeError('Native integration is incomplete or failing')
for name, digest in results.get('tested_files', {}).items():
    if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError('Native report is stale for ' + name)
if not results.get('tested_files'):
    raise RuntimeError('Native report must fingerprint the code that it tested')
gui_path = ARTIFACTS / 'gui-results.json'
gui = json.loads(gui_path.read_text()) if gui_path.exists() else {'passed': 0, 'errors': ['Not tested']}
if not candidate and (gui['errors'] or gui['passed'] < 7):
    raise RuntimeError('Native GUI smoke is incomplete or failing')
for name, digest in gui.get('tested_files', {}).items():
    if not candidate and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError('GUI report is stale for ' + name)
archive = ARTIFACTS / ('TopoIntent-0.1.0-candidate.zip' if candidate else 'TopoIntent-0.1.0-workbench.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
    for name in FILES:
        package.write(ROOT / name, 'TopoIntent/' + name)
    for name in ['box-counterfactual.FCStd', 'renumber-before-review.FCStd',
                 'renumber-after-repair.FCStd', 'ambiguous-split-refused.FCStd']:
        package.write(ARTIFACTS / name, 'TopoIntent/examples/' + name)
    package.write(results_path, 'TopoIntent/verification/integration-results.json')
    if not candidate:
        package.write(gui_path, 'TopoIntent/verification/gui-results.json')
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(ARTIFACTS / (archive.name + '.sha256')).write_text(digest + '  ' + archive.name + '\n')
if not candidate:
    website_report = dict(results, gui=gui)
    (ROOT / 'docs/evidence.json').write_text(json.dumps(website_report, indent=2) + '\n')
print(archive.name, archive.stat().st_size, 'bytes', digest)
