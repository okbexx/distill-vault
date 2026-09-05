"""Cross-project Agent commit guidance and literal attachment paths."""
from pathlib import Path
import shlex
import subprocess
import sys

import pytest
import yaml

from distill.commit import DistillCommit
from distill.routing import capture_progress_update, route_plan
from distill.source_record import record_source


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault's space"
    root.mkdir()
    (root / 'knowledge/project').mkdir(parents=True)
    (root / 'distill.yaml').write_text(yaml.safe_dump({
        'vault': {'knowledge_dirs': ['knowledge', 'inbox']},
        'capture': {'source_dir': 'inbox'},
    }))
    for args in [('init',), ('config', 'user.name', 'Test'),
                 ('config', 'user.email', 'test@example.invalid')]:
        subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
    monkeypatch.setenv('PYTHONPATH', str(Path(__file__).resolve().parents[1]))
    return root


def run_recommendation(command, cwd):
    argv = shlex.split(command)
    assert argv[0] == 'distill'
    return subprocess.run([sys.executable, '-m', 'distill.cli', *argv[1:]],
                          cwd=cwd, text=True, capture_output=True, timeout=45)


def committed_names(root):
    raw = subprocess.check_output(['git', 'diff-tree', '--root', '--no-commit-id', '--name-only', '-r', '-z', 'HEAD'], cwd=root)
    return set(raw.decode().strip('\0').split('\0'))


def test_raw_recommendation_works_from_other_project(vault, tmp_path):
    other = tmp_path / 'other'; other.mkdir()
    attachment = tmp_path / '[草稿].txt'; attachment.write_text('exact attachment')
    result = record_source(vault, 'An unclassified future thought', attachments=[str(attachment)])
    p = run_recommendation(result['recommended_commit_command'], other)
    assert p.returncode == 0, p.stdout + p.stderr
    assert committed_names(vault) == set(result['touched_paths'])
    assert not list(other.iterdir())


def test_project_plan_and_apply_recommendations_bind_vault_and_quote(vault, tmp_path):
    other = tmp_path / 'unrelated'; other.mkdir()
    title = "Project's $(not-a-command)"
    project = vault / "knowledge/project/Project's notes.md"
    project.write_text('---\n' + yaml.safe_dump({'id': 'project-test', 'type': 'project',
        'title': title, 'status': 'active', 'summary': 'Long-term purpose', 'sources': []}) + '---\n# Project\n')
    intent = 'completed one isolated verification'
    plan = route_plan(vault, intent, project_hint=title)
    result = capture_progress_update(vault, intent, project_hint=title)
    assert result.recommended_commit_command == plan['recommended_commit_command']
    p = run_recommendation(result.recommended_commit_command, other)
    assert p.returncode == 0, p.stdout + p.stderr
    assert committed_names(vault) == set(result.touched_paths)
    assert not list(other.iterdir())


@pytest.mark.parametrize('name', ['[草稿].txt', 'draft[1].txt', "notes [draft]'s.txt"])
def test_literal_bracket_filename_is_committable_without_expansion(vault, name):
    (vault / 'inbox').mkdir()
    selected = 'inbox/' + name
    (vault / selected).write_text('only selected')
    (vault / 'inbox/draft1.txt').write_text('must not be selected by bracket expression')
    p = DistillCommit(vault).commit('literal selected', paths=[selected], skip_run=True)
    assert p['success'], p
    assert committed_names(vault) == {selected}


def test_bracket_directory_deletion_still_rejected(vault):
    folder = vault / 'knowledge/[draft]'; folder.mkdir()
    target = 'knowledge/[draft]/target.md'; (vault / target).write_text('target')
    assert DistillCommit(vault).commit('seed', paths=[target], skip_run=True)['success']
    (vault / target).unlink()
    result = DistillCommit(vault).commit('unsafe deletion', paths=[target], skip_run=True)
    assert not result['success']
    assert 'delet' in result['error'].lower()
