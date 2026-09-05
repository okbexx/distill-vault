"""Read-only production audit; all writes occur in synthetic temp vaults."""
import argparse
import asyncio
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config-from', type=Path, default=ROOT / 'examples/personal-workbench')
parser.add_argument('--output', type=Path)
args = parser.parse_args()
CONFIG_SOURCE = args.config_from.resolve()


def make_vault(root):
    root.mkdir()
    shutil.copy2(CONFIG_SOURCE / 'distill.yaml', root / 'distill.yaml')
    schema = root / '系统/规范/object.schema.json'
    schema.parent.mkdir(parents=True)
    source_schema = CONFIG_SOURCE / '系统/规范/object.schema.json'
    if source_schema.exists():
        shutil.copy2(source_schema, schema)
    for args in [('init',), ('config', 'user.name', 'Isolated Test'),
                 ('config', 'user.email', 'isolated@example.invalid')]:
        subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
    return root


def cli(root, *args):
    return subprocess.run([sys.executable, '-m', 'distill.cli', '-v', str(root), *args],
                          cwd=root, capture_output=True, text=True, timeout=45)


def commit_record(root, result):
    args = ['commit', 'audit: synthetic record', '--skip-run']
    for p in result['touched_paths']:
        args += ['--paths', p]
    return cli(root, *args)


def errors(root, paths):
    args = ['lint', '--format', 'json']
    for p in paths:
        args += ['--paths', p]
    p = cli(root, *args)
    return [dict(rule=i.get('rule'), file=i.get('file'))
            for i in json.loads(p.stdout)['issues'] if i['severity'] == 'error']


async def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='agent-flow-audit-') as tmp:
        base = Path(tmp)
        vault = make_vault(base / 'vault')
        other = make_vault(base / 'other-project')
        parameters = StdioServerParameters(command=sys.executable,
            args=['-m', 'distill.mcp_server', '--vault', str(vault)])
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                async def call(name, args):
                    response = await session.call_tool(name, args)
                    assert not response.isError, name
                    return json.loads(''.join(getattr(x, 'text', '') for x in response.content))

                attachment = base / 'chosen.txt'
                attachment.write_text('synthetic attachment, not user data')
                record = await call('source_record', {'text': '独立审计词FlowRecall 保存尚未分类的想法。', 'attachments': [str(attachment)]})
                recalled = await call('search', {'query': '独立审计词FlowRecall', 'mode': 'keyword', 'limit': 5})
                saved_bytes = (vault / record['attachment_paths'][0]).read_bytes() == attachment.read_bytes()
                committed = commit_record(vault, record)
                rows.append({'scenario': 'real_mcp_stdio_save_search_commit', 'passed': saved_bytes and record['source_path'] in json.dumps(recalled, ensure_ascii=False) and committed.returncode == 0})

                cross = await call('source_record', {'text': 'CrossProject 新建记录用于跨目录提交审计'})
                command = shlex.split(cross['recommended_commit_command'])
                executed = subprocess.run([sys.executable, '-m', 'distill.cli', *command[1:]], cwd=other, capture_output=True, text=True, timeout=45)
                rows.append({'scenario': 'returned_commit_command_from_other_project', 'passed': executed.returncode == 0,
                             'command_has_vault_selector': '-v' in command or '--vault' in command,
                             'returncode': executed.returncode, 'diagnostic': (executed.stderr or executed.stdout)[-700:]})

                named = base / '[草稿].txt'
                named.write_text('synthetic bracket filename')
                br = await call('source_record', {'text': '用户明确选择的附件', 'attachments': [str(named)]})
                bc = commit_record(vault, br)
                rows.append({'scenario': 'attachment_with_brackets_save_then_commit', 'saved': True, 'passed': bc.returncode == 0,
                             'diagnostic': (bc.stderr or bc.stdout)[-700:]})

                note = vault / '收件箱/桌面直接新建.md'
                note.write_text('临时想法，之后再看看 [[尚未整理的概念]]。\n')
                issues = errors(vault, ['收件箱/桌面直接新建.md'])
                committed_note = commit_record(vault, {'touched_paths': ['收件箱/桌面直接新建.md']})
                rows.append({'scenario': 'plain_desktop_note_with_unresolved_raw_link',
                             'passed': not issues and committed_note.returncode == 0, 'errors': issues,
                             'commit_returncode': committed_note.returncode})

                md = base / '外部剪藏.md'
                md.write_text('原始剪藏内容 [[未落库的原始引用]]。\n')
                mr = await call('source_record', {'text': '保存外部文件，不要求整理内容', 'attachments': [str(md)]})
                issues = errors(vault, mr['touched_paths'])
                committed_md = commit_record(vault, mr)
                rows.append({'scenario': 'markdown_attachment_keeps_raw_semantics_at_commit', 'saved': True,
                             'passed': not issues and committed_md.returncode == 0, 'errors': issues,
                             'commit_returncode': committed_md.returncode})

    report = {'scope': 'synthetic temp vaults using selected config/schema; real MCP stdio; no source content copied',
              'natural_language_agent_routing_tested': False, 'production_vault_modified': False,
              'passed': sum(r['passed'] for r in rows), 'total': len(rows), 'cases': rows}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return all(row['passed'] for row in rows)


if __name__ == '__main__':
    sys.exit(0 if asyncio.run(main()) else 1)
