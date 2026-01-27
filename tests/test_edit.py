"""Tests for pergit.edit module."""

import unittest
from unittest import mock

from pergit.edit import (
    LocalChanges,
    check_file_status,
    find_common_ancestor,
    get_local_git_changes,
    include_changes_in_changelist,
    edit_command,
)
from tests.helpers import make_run_result


class TestCheckFileStatus(unittest.TestCase):
    @mock.patch('pergit.edit.run')
    def test_file_not_opened(self, mock_run):
        mock_run.return_value = make_run_result(stdout=[
            "//depot/foo.txt - file(s) not opened on this client."
        ])
        result = check_file_status('foo.txt', '/ws')
        self.assertIsNone(result)

    @mock.patch('pergit.edit.run')
    def test_file_in_default_changelist(self, mock_run):
        mock_run.return_value = make_run_result(stdout=[
            "//depot/foo.txt#1 - edit default change (text) by user@ws"
        ])
        result = check_file_status('foo.txt', '/ws')
        self.assertEqual(result, 'default')

    @mock.patch('pergit.edit.run')
    def test_file_in_numbered_changelist(self, mock_run):
        mock_run.return_value = make_run_result(stdout=[
            "//depot/foo.txt#1 - edit change 12345 (text) by user@ws"
        ])
        result = check_file_status('foo.txt', '/ws')
        self.assertEqual(result, '12345')

    @mock.patch('pergit.edit.run')
    def test_empty_output(self, mock_run):
        mock_run.return_value = make_run_result(stdout=[])
        result = check_file_status('foo.txt', '/ws')
        self.assertIsNone(result)


class TestFindCommonAncestor(unittest.TestCase):
    @mock.patch('pergit.edit.run')
    def test_finds_ancestor(self, mock_run):
        mock_run.return_value = make_run_result(stdout=['abc123def456'])
        rc, ancestor = find_common_ancestor('main', 'HEAD', '/ws')
        self.assertEqual(rc, 0)
        self.assertEqual(ancestor, 'abc123def456')

    @mock.patch('pergit.edit.run')
    def test_failure(self, mock_run):
        mock_run.return_value = make_run_result(returncode=1)
        rc, ancestor = find_common_ancestor('main', 'HEAD', '/ws')
        self.assertEqual(rc, 1)
        self.assertIsNone(ancestor)

    @mock.patch('pergit.edit.run')
    def test_no_output(self, mock_run):
        mock_run.return_value = make_run_result(stdout=[])
        rc, ancestor = find_common_ancestor('main', 'HEAD', '/ws')
        self.assertEqual(rc, 1)
        self.assertIsNone(ancestor)


class TestGetLocalGitChanges(unittest.TestCase):
    @mock.patch('pergit.edit.run')
    def test_parses_all_change_types(self, mock_run):
        mock_run.side_effect = [
            # git merge-base
            make_run_result(stdout=['abc123']),
            # git diff --name-status
            make_run_result(stdout=[
                'M\tmodified.txt',
                'A\tadded.txt',
                'D\tdeleted.txt',
                'R100\told_name.txt\tnew_name.txt',
            ]),
        ]
        rc, changes = get_local_git_changes('main', '/ws')
        self.assertEqual(rc, 0)
        self.assertEqual(changes.mods, ['modified.txt'])
        self.assertEqual(changes.adds, ['added.txt'])
        self.assertEqual(changes.dels, ['deleted.txt'])
        self.assertEqual(changes.moves, [('old_name.txt', 'new_name.txt')])

    @mock.patch('pergit.edit.run')
    def test_merge_base_failure(self, mock_run):
        mock_run.return_value = make_run_result(returncode=1)
        rc, changes = get_local_git_changes('main', '/ws')
        self.assertNotEqual(rc, 0)
        self.assertIsNone(changes)

    @mock.patch('pergit.edit.run')
    def test_unknown_status(self, mock_run):
        mock_run.side_effect = [
            make_run_result(stdout=['abc123']),
            make_run_result(stdout=['X\tunknown.txt']),
        ]
        rc, changes = get_local_git_changes('main', '/ws')
        self.assertNotEqual(rc, 0)
        self.assertIsNone(changes)


class TestIncludeChangesInChangelist(unittest.TestCase):
    @mock.patch('pergit.edit.check_file_status')
    @mock.patch('pergit.edit.run')
    def test_adds_files(self, mock_run, mock_check):
        mock_run.return_value = make_run_result()
        changes = LocalChanges()
        changes.adds = ['new_file.txt']
        rc = include_changes_in_changelist(changes, '100', '/ws')
        self.assertEqual(rc, 0)
        mock_run.assert_called_with(
            ['p4', 'add', '-c', '100', 'new_file.txt'],
            cwd='/ws', dry_run=False,
        )

    @mock.patch('pergit.edit.check_file_status', return_value=None)
    @mock.patch('pergit.edit.run')
    def test_edits_unchecked_out_file(self, mock_run, mock_check):
        mock_run.return_value = make_run_result()
        changes = LocalChanges()
        changes.mods = ['mod.txt']
        rc = include_changes_in_changelist(changes, '100', '/ws')
        self.assertEqual(rc, 0)
        mock_run.assert_called_with(
            ['p4', 'edit', '-c', '100', 'mod.txt'],
            cwd='/ws', dry_run=False,
        )

    @mock.patch('pergit.edit.check_file_status', return_value='200')
    @mock.patch('pergit.edit.run')
    def test_reopens_file_in_different_changelist(self, mock_run, mock_check):
        mock_run.return_value = make_run_result()
        changes = LocalChanges()
        changes.mods = ['mod.txt']
        rc = include_changes_in_changelist(changes, '100', '/ws')
        self.assertEqual(rc, 0)
        mock_run.assert_called_with(
            ['p4', 'reopen', '-c', '100', 'mod.txt'],
            cwd='/ws', dry_run=False,
        )

    @mock.patch('pergit.edit.check_file_status', return_value='100')
    @mock.patch('pergit.edit.run')
    def test_skips_file_already_in_correct_changelist(self, mock_run, mock_check):
        mock_run.return_value = make_run_result()
        changes = LocalChanges()
        changes.mods = ['mod.txt']
        rc = include_changes_in_changelist(changes, '100', '/ws')
        self.assertEqual(rc, 0)
        mock_run.assert_not_called()

    @mock.patch('pergit.edit.check_file_status')
    @mock.patch('pergit.edit.run')
    def test_deletes_files(self, mock_run, mock_check):
        mock_run.return_value = make_run_result()
        changes = LocalChanges()
        changes.dels = ['old.txt']
        rc = include_changes_in_changelist(changes, '100', '/ws')
        self.assertEqual(rc, 0)
        mock_run.assert_called_with(
            ['p4', 'delete', '-c', '100', 'old.txt'],
            cwd='/ws', dry_run=False,
        )

    @mock.patch('pergit.edit.check_file_status')
    @mock.patch('pergit.edit.run')
    def test_moves_files(self, mock_run, mock_check):
        mock_run.return_value = make_run_result()
        changes = LocalChanges()
        changes.moves = [('old.txt', 'new.txt')]
        rc = include_changes_in_changelist(changes, '100', '/ws')
        self.assertEqual(rc, 0)
        calls = mock_run.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0][0], [
                         'p4', 'delete', '-c', '100', 'old.txt'])
        self.assertEqual(calls[1][0][0], ['p4', 'add', '-c', '100', 'new.txt'])

    @mock.patch('pergit.edit.check_file_status')
    @mock.patch('pergit.edit.run')
    def test_dry_run(self, mock_run, mock_check):
        mock_run.return_value = make_run_result()
        changes = LocalChanges()
        changes.adds = ['new.txt']
        rc = include_changes_in_changelist(changes, '100', '/ws', dry_run=True)
        self.assertEqual(rc, 0)
        mock_run.assert_called_with(
            ['p4', 'add', '-c', '100', 'new.txt'],
            cwd='/ws', dry_run=True,
        )


class TestEditCommand(unittest.TestCase):
    @mock.patch('pergit.edit.ensure_workspace', return_value='/ws')
    @mock.patch('pergit.edit.run')
    def test_success(self, mock_run, _mock_ws):
        mock_run.side_effect = [
            make_run_result(stdout=['abc123']),
            make_run_result(stdout=['A\tnew.txt']),
            make_run_result(),
        ]
        args = mock.Mock(changelist='100', base_branch='HEAD~1', dry_run=False)
        rc = edit_command(args)
        self.assertEqual(rc, 0)


if __name__ == '__main__':
    unittest.main()
