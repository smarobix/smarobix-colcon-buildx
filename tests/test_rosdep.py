# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

import subprocess

import pytest

from colcon_buildx import rosdep_manager

IMAGE = 'ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy'


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path.resolve()
    pkg = root / 'src' / 'my_pkg'
    pkg.mkdir(parents=True)
    (pkg / 'package.xml').write_text(
        '<package format="3"><name>my_pkg</name><depend>rclcpp</depend></package>')
    return root


@pytest.fixture
def commands(monkeypatch):
    recorded = []

    def run(cmd, **kwargs):
        recorded.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

    monkeypatch.setattr(rosdep_manager.subprocess, 'run', run)
    return recorded


def _running_the_script(commands):
    return [cmd for cmd in commands if 'rosdep install --from-paths src' in ' '.join(cmd)]


def test_install_script_runs_exactly_once(workspace, commands):
    rosdep_manager.install_deps_docker(IMAGE, workspace, 'linux/arm64')

    runs = _running_the_script(commands)
    assert len(runs) == 1
    assert runs[0][:2] == ['docker', 'run']
    assert not any(cmd[:2] in (['docker', 'exec'], ['docker', 'start']) for cmd in commands)


def test_the_container_that_ran_the_script_is_committed_and_removed(workspace, commands):
    new_tag = rosdep_manager.install_deps_docker(IMAGE, workspace, 'linux/arm/v7')

    run = _running_the_script(commands)[0]
    name = run[run.index('--name') + 1]
    assert run[run.index('--platform') + 1] == 'linux/arm/v7'
    assert ['docker', 'commit', name, new_tag] in commands
    assert ['docker', 'rm', '-f', name] == commands[-1]


def test_package_lists_are_fetched_before_rosdep_installs(workspace, commands):
    rosdep_manager.install_deps_docker(IMAGE, workspace, 'linux/arm64')
    script = _running_the_script(commands)[0][-1]
    assert script.index('apt-get update') < script.index('rosdep install --from-paths')


def test_a_failed_install_is_reported_and_cleaned_up(workspace, monkeypatch):
    recorded = []

    def run(cmd, **kwargs):
        recorded.append(cmd)
        failed = cmd[:2] == ['docker', 'run']
        return subprocess.CompletedProcess(cmd, 1 if failed else 0, stdout='', stderr='E: boom')

    monkeypatch.setattr(rosdep_manager.subprocess, 'run', run)
    with pytest.raises(RuntimeError):
        rosdep_manager.install_deps_docker(IMAGE, workspace, 'linux/arm64')
    assert not any(cmd[:2] == ['docker', 'commit'] for cmd in recorded)
    assert recorded[-1][:3] == ['docker', 'rm', '-f']
