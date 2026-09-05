#!/usr/bin/env python3
"""Read-only migration inventory. Never copies content or secret values."""
import argparse
import json
from pathlib import Path


def preview(vault):
    root = Path(vault).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('vault must be a directory')
    groups = {}
    for name, relative in [('projects', '知识/项目'), ('sources', '知识/来源'),
                           ('concepts', '知识/概念'), ('daily_outputs', '输出/日志')]:
        folder = root / relative
        paths = sorted(str(p.relative_to(root)) for p in folder.glob('*.md')
                       if p.is_file() and not p.is_symlink())
        groups[name] = {'count': len(paths), 'paths': paths}
    return {
        'mode': 'preview_only',
        'writes': [],
        'groups': groups,
        'actions': [
            'Keep original sources and attachments unchanged.',
            'Add an unclassified inbox without requiring project assignment.',
            'Review project instructions individually; do not rewrite history in bulk.',
            'Create access metadata only; do not extract secrets automatically.',
            'Review legacy schema and agent rules before enabling free-form capture.',
            'Change daily automation only after a separate operational rollout.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vault')
    args = parser.parse_args()
    print(json.dumps(preview(args.vault), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
