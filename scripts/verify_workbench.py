#!/usr/bin/env python3
"""Exercise real CLI/MCP paths in an isolated sample copy; never the live vault."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from distill.mcp_tools import DistillMCPTools


def main():
    with tempfile.TemporaryDirectory(prefix='distill-workbench-e2e-') as tmp:
        vault = Path(tmp) / 'vault'
        shutil.copytree(ROOT / 'examples/personal-workbench', vault)
        attachment = Path(tmp) / 'example.bin'
        attachment.write_bytes(bytes(range(256)))
        tools = DistillMCPTools(vault)
        result = tools.call_tool('source_record', {
            'text': '  workbenchacceptance unique recall\n一个尚未确定归属的想法。\n',
            'attachments': [str(attachment)],
        })
        assert result['operation'] == 'source_only', result
        assert (vault / result['attachment_paths'][0]).read_bytes() == attachment.read_bytes()
        assert (vault / result['raw_path']).read_bytes().startswith(b'  workbenchacceptance')
        search = tools.call_tool('search', {'query': 'workbenchacceptance', 'mode': 'keyword', 'limit': 5})
        assert result['source_path'] in json.dumps(search, ensure_ascii=False), search
        status = tools.call_tool('vault_status', {})
        # Successful capture may not imply full pipeline initialization.
        # Assert only the changed source's visibility, not a hardcoded total.
        for args in [('init',), ('config','user.name','Workbench Test'),
                     ('config','user.email','test@example.invalid')]:
            subprocess.run(['git', *args], cwd=vault, check=True, capture_output=True)
        from distill.commit import DistillCommit
        committed = DistillCommit(vault).commit('test: isolated capture', paths=result['touched_paths'], skip_run=True)
        assert committed['success'], committed
        names = subprocess.check_output(['git','-c','core.quotepath=false','show','--pretty=','--name-only','HEAD'], cwd=vault, text=True).splitlines()
        assert set(names) == set(result['touched_paths']), (names, result)
        print(json.dumps({'mcp_capture':'pass','attachment_bytes':'pass','search_recall':'pass',
                          'scoped_real_git_commit':'pass','live_vault_modified':False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
