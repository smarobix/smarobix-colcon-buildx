# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""colcon shows warnings and printed output, but not logger.info, by default.

Guidance a user has to act on must therefore be printed or logged as a
warning or error. These tests check the places where it used to be lost.
"""

import argparse
import logging
import subprocess
import types

import pytest

from colcon_buildx import docker, sdk
from colcon_buildx.sdk import SdkBuilder
from colcon_buildx.verb.buildx import BuildxVerb


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    (root / 'src').mkdir()
    monkeypatch.chdir(root)
    return root


def _run_verb(argv):
    parser = argparse.ArgumentParser()
    verb = BuildxVerb()
    verb.add_arguments(parser=parser)
    return verb.main(context=types.SimpleNamespace(args=parser.parse_args(argv)))


def test_mixin_registration_commands_are_printed(workspace, capsys):
    SdkBuilder('/sdk/env', 'cross_build', 'cross_install').write_mixin(
        {'OE_CMAKE_TOOLCHAIN_FILE': '/sdk/tc.cmake'})
    out = capsys.readouterr().out
    assert f'colcon mixin add buildx file://{workspace}/.buildx/mixin/index.yaml' in out
    assert 'colcon mixin update buildx' in out


def test_use_base_image_hint_is_printed_with_a_synced_image(workspace, monkeypatch, capsys):
    base = 'ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy'

    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=f'{base}-synced-20260922\n')

    monkeypatch.setattr(docker.subprocess, 'run', run)
    builder = docker.DockerBuilder(base, 'linux/arm64', 'cross_build', 'cross_install')
    assert builder.image == f'{base}-synced-20260922'
    assert '--use-base-image' in capsys.readouterr().out


def test_non_linux_sdk_hint_is_an_error_with_a_real_image(monkeypatch, caplog):
    monkeypatch.setattr(sdk.sys, 'platform', 'darwin')
    with caplog.at_level(logging.WARNING):
        assert SdkBuilder('/sdk/env', 'b', 'i').check_host() is False
    assert 'ghcr.io/smarobix/smarobix-buildx-images:k26-oesdk-jazzy' in caplog.text


def test_install_deps_with_docker_warns_with_the_workflow(workspace, monkeypatch, caplog):
    monkeypatch.setattr(docker.DockerBuilder, 'detect_synced_image', lambda self: self.base_image)
    monkeypatch.setattr(docker.DockerBuilder, 'install_dependencies', lambda self, args: None)
    with caplog.at_level(logging.WARNING):
        assert _run_verb(['--docker-image', 'img:jazzy', '--install-deps']) == 1
    assert 'the board will NOT have them' in caplog.text
    assert 'colcon buildx --install-deps-on-device SSH_TARGET' in caplog.text


def test_config_file_in_use_is_printed(workspace, monkeypatch, capsys, caplog):
    (workspace / '.buildx.conf').write_text(
        'method = sdk\nsdk_env = /opt/sdk/env\ninstall_deps = true\n')
    monkeypatch.setattr(SdkBuilder, 'build', lambda self, extra_args=None: 0)
    with caplog.at_level(logging.WARNING):
        assert _run_verb([]) == 0
    assert f'Config file: {workspace / ".buildx.conf"}' in capsys.readouterr().out
    # --install-deps does nothing for an SDK build, and now says so.
    assert 'Ignoring --install-deps' in caplog.text
