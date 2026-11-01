"""Acquire an official portable FreeCAD into this project, never into installed apps."""
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
VERSION = '1.1.4'
NAME = 'FreeCAD_1.1.4-Windows-x86_64-py311.7z'
BASE = f'https://github.com/FreeCAD/FreeCAD/releases/download/{VERSION}/'


def acquire():
    RUNTIME.mkdir(exist_ok=True)
    archive = RUNTIME / NAME
    checksum = urllib.request.urlopen(BASE + NAME + '-SHA256.txt', timeout=60).read().decode()
    expected = checksum.strip().split()[0].lower()
    if not archive.exists():
        with urllib.request.urlopen(BASE + NAME, timeout=120) as source, archive.open('wb') as dest:
            while chunk := source.read(4 * 1024 * 1024):
                dest.write(chunk)
        print('Downloaded', archive.name, flush=True)
    digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    if digest != expected:
        raise RuntimeError('Official archive SHA256 mismatch; remove archive and retry')
    output = RUNTIME / 'freecad'
    output.mkdir(exist_ok=True)
    if not (RUNTIME / 'portable-manifest.json').exists():
        # The official archive uses BCJ2, unsupported by py7zr. Pin the small
        # standalone public-domain upstream extractor instead of installing 7-Zip.
        extractor = RUNTIME / '7zr.exe'
        extractor_url = 'https://github.com/ip7z/7zip/releases/download/26.04/7zr.exe'
        extractor_sha = '256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282'
        if not extractor.exists():
            extractor.write_bytes(urllib.request.urlopen(extractor_url, timeout=60).read())
        if hashlib.sha256(extractor.read_bytes()).hexdigest() != extractor_sha:
            raise RuntimeError('Pinned 7zr extractor SHA256 mismatch')
        subprocess.run([str(extractor), 'x', '-y', '-o' + str(output), str(archive)], check=True)
    manifest = {'version': VERSION, 'archive': NAME, 'url': BASE + NAME, 'sha256': digest,
                'command': [str(p.relative_to(ROOT)) for p in output.rglob('FreeCADCmd.exe')]}
    (RUNTIME / 'portable-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest), flush=True)


if __name__ == '__main__':
    acquire()
