# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

import argparse
import subprocess
import types

import pytest

from colcon_buildx import deployment
from colcon_buildx.sdk import SdkBuilder
from colcon_buildx.sysroot import SysrootBuilder
from colcon_buildx.verb.buildx import BuildxVerb

TARGET = 'ubuntu@10.42.0.3:~/ros2_ws/install/'


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    (root / 'src' / 'my_pkg').mkdir(parents=True)
    (root / 'cross_install').mkdir()
    # Run from below the workspace root, as a user in a package directory does.
    monkeypatch.chdir(root / 'src' / 'my_pkg')
    return root


@pytest.fixture
def commands(monkeypatch):
    recorded = []

    def run(cmd, **kwargs):
        recorded.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, 'run', run)
    return recorded


def test_install_base_is_found_under_the_workspace_root(workspace, commands):
    assert deployment.deploy('cross_install', TARGET, workspace) == 0
    cmd, _ = commands[0]
    assert cmd[0] == 'rsync'
    assert cmd[-2:] == [f'{workspace}/cross_install/', TARGET]


def test_an_absolute_install_base_is_used_as_is(workspace, tmp_path, commands):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    assert deployment.deploy(str(elsewhere), TARGET, workspace) == 0
    assert commands[0][0][-2] == f'{elsewhere}/'


def test_missing_install_directory_fails_without_rsync(workspace, commands):
    assert deployment.deploy('not_built', TARGET, workspace) == 1
    assert commands == []


def test_deploy_without_a_target_fails_before_building(workspace, monkeypatch):
    built = []
    monkeypatch.setattr(SdkBuilder, 'build', lambda self, extra_args=None: built.append(1) or 0)

    parser = argparse.ArgumentParser()
    verb = BuildxVerb()
    verb.add_arguments(parser=parser)
    args = parser.parse_args(['--method', 'sdk', '--sdk-env', '/opt/sdk/env', '--deploy'])

    assert verb.main(context=types.SimpleNamespace(args=args)) == 1
    assert built == []


def test_sysroot_runs_colcon_from_the_workspace_root(workspace, commands, monkeypatch):
    toolchain = workspace / 'toolchain.cmake'
    toolchain.write_text('')
    builder = SysrootBuilder(
        'my-board', '~/mnt/board-sysroot', str(toolchain), 'cross_build', 'cross_install',
        no_mount=True, workspace_root=workspace)
    monkeypatch.setattr(builder, 'mount_sysroot', lambda: True)

    assert builder.build() == 0
    cmd, kwargs = commands[-1]
    assert cmd[:2] == ['colcon', 'build']
    assert kwargs['cwd'] == workspace
