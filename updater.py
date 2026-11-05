"""Startup updater. Supports a local manifest or an explicitly configured HTTPS feed."""
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ALLOWED = {'app.py', 'targeting.py', 'requirements.txt', 'README.md'}
LIMIT = 8 * 1024 * 1024

def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,6}\.\d{1,6}\.\d{1,6}', value):
        raise ValueError('Invalid update version')
    return tuple(map(int, value.split('.')))

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def get_bytes(source, limit):
    if source.startswith('https://'):
        request = urllib.request.Request(source, headers={'User-Agent': 'HazmobSnap-Updater/1'})
        with urllib.request.urlopen(request, timeout=10) as response:
            if not response.geturl().startswith('https://'):
                raise ValueError('Update redirect must use HTTPS')
            data = response.read(limit + 1)
    else:
        if '://' in source:
            raise ValueError('Only local files or HTTPS are supported')
        with open(source, 'rb') as stream:
            data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Update exceeds the allowed size')
    return data

def current_release(base):
    fallback = base
    current = (base / 'version.txt').read_text(encoding='utf-8-sig').strip() if (base / 'version.txt').exists() else '1.0.0'
    version(current)
    if (base / 'active-release.json').exists():
        saved = read_json(base / 'active-release.json')['version']
        version(saved)
        candidate = base / '.releases' / saved
        if all((candidate / name).is_file() for name in ALLOWED):
            return candidate, saved
    return fallback, current

def check(base):
    base = Path(base).resolve()
    try:
        active, installed = current_release(base)
    except Exception:
        active, installed = base, '1.0.0'
    result = {'path': str(active), 'version': installed, 'status': 'Up to date.'}
    staging = None
    try:
        config = read_json(base / 'update-source.json')
        if not config.get('enabled', True):
            result['status'] = 'Update checks disabled.'
            return result
        source = config['manifest']
        manifest = json.loads(get_bytes(source, 16384).decode('utf-8-sig'))
        release = manifest['version']
        if version(release) <= version(installed):
            return result
        filename = manifest['package']
        if not re.fullmatch(r'[A-Za-z0-9._-]+\.zip', filename):
            raise ValueError('Invalid package filename')
        expected = manifest['sha256']
        if not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise ValueError('Invalid checksum')
        package_source = urllib.parse.urljoin(source, filename) if source.startswith('https://') else str(Path(source).parent / filename)
        if source.startswith('https://') and '/releases/latest/download/' in source:
            # Pin the ZIP to the manifest's release, even if latest changes mid-update.
            prefix = source.split('/releases/latest/download/', 1)[0]
            package_source = f'{prefix}/releases/download/v{release}/{filename}'
        data = get_bytes(package_source, LIMIT)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Package checksum mismatch')
        contents = {}
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if len(names) != len(ALLOWED) or set(names) != ALLOWED:
                raise ValueError('Unexpected or duplicate files in update')
            if sum(info.file_size for info in archive.infolist()) > LIMIT:
                raise ValueError('Expanded update exceeds size limit')
            for info in archive.infolist():
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError('Symlinks are not allowed')
                blob = archive.read(info)
                if info.filename.endswith('.py'):
                    compile(blob, info.filename, 'exec')
                contents[info.filename] = blob
        releases = base / '.releases'
        releases.mkdir(exist_ok=True)
        destination = releases / release
        if destination.exists():
            # Never overwrite a potentially running release.
            for name, blob in contents.items():
                if not (destination / name).is_file() or (destination / name).read_bytes() != blob:
                    raise ValueError('Existing release differs; publish a new version number')
        else:
            staging = Path(tempfile.mkdtemp(prefix='staging-', dir=releases))
            for name, blob in contents.items():
                (staging / name).write_bytes(blob)
            staging.rename(destination)
            staging = None
        state = {'version': release, 'previous': installed}
        temporary = base / 'active-release.json.tmp'
        temporary.write_text(json.dumps(state), encoding='utf-8')
        os.replace(temporary, base / 'active-release.json')
        result = {'path': str(destination), 'version': release, 'status': f'Updated automatically: {installed} -> {release}'}
    except Exception as exc:
        result['status'] = f'Update unavailable; keeping version {installed}. {exc}'
    finally:
        if staging and staging.exists():
            # Staging contains only the allowlisted files created above.
            for name in ALLOWED:
                path = staging / name
                if path.exists():
                    path.unlink()
            staging.rmdir()
    return result

if __name__ == '__main__':
    print(json.dumps(check(Path(__file__).resolve().parent)))
