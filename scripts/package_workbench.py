#!/usr/bin/env python3
"""Package public sample vault + built plugin, never the user's real vault."""
from pathlib import Path
import argparse
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(destination):
    sample = ROOT / 'examples/personal-workbench'
    plugin = ROOT / 'integrations/obsidian-workbench'
    required = ['manifest.json', 'main.js', 'styles.css']
    missing = [name for name in required if not (plugin / name).is_file()]
    if missing:
        raise RuntimeError('Build plugin first; missing: ' + ', '.join(missing))
    import json
    plugin_id = json.loads((plugin / 'manifest.json').read_text())['id']
    if not plugin_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in plugin_id):
        raise ValueError('Invalid plugin id')
    out = Path(destination).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(sample.rglob('*')):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(sample)
            if any(part in {'.git', '.distill', 'node_modules', '__pycache__'} for part in rel.parts):
                continue
            z.write(path, str(Path('Distill-Workbench') / rel))
        for name in required:
            z.write(plugin / name, f'Distill-Workbench/.obsidian/plugins/{plugin_id}/{name}')
        z.write(ROOT / 'docs/personal-workbench.md', 'Distill-Workbench/使用边界.md')
        z.write(ROOT / 'docs/workbench-acceptance.md', 'Distill-Workbench/验收与迁移.md')
        z.write(plugin / 'README.md', 'Distill-Workbench/插件说明.md')
    with zipfile.ZipFile(out) as z:
        if z.testzip() is not None:
            raise RuntimeError('Archive verification failed')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    print(package(parser.parse_args().destination))
