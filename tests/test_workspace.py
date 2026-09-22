# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

import logging

import pytest

from colcon_buildx import docker
from colcon_buildx.sdk import SdkBuilder
from colcon_buildx.sysroot import SysrootBuilder
from colcon_buildx.verb import buildx
from colcon_buildx.workspace import (
    MAX_LEVELS, find_workspace_root, resolve_workspace_root, search_path,
)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path.resolve() / 'ws'
    (root / 'src' / 'pkg' / 'include').mkdir(parents=True)
    return root


@pytest.fixture
def nowhere(tmp_path, monkeypatch):
    # Deeper than the search goes, so nothing above tmp_path can match.
    deep = tmp_path.resolve().joinpath(*['d'] * (MAX_LEVELS + 1))
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    return deep


def test_root_is_found_from_a_package_directory(workspace, monkeypatch):
    monkeypatch.chdir(workspace / 'src' / 'pkg' / 'include')
    assert find_workspace_root() == workspace


def test_search_stops_at_the_workspace_root(workspace):
    start = workspace / 'src' / 'pkg'
    assert list(search_path(start)) == [start, workspace / 'src', workspace]


def test_search_is_bounded(nowhere):
    assert len(list(search_path())) == MAX_LEVELS
    assert find_workspace_root() is None


def test_resolve_prefers_an_explicit_root(workspace, nowhere):
    assert resolve_workspace_root(workspace) == workspace
    assert resolve_workspace_root() == nowhere


def test_verb_warns_when_it_falls_back_to_the_current_directory(nowhere, caplog):
    with caplog.at_level(logging.WARNING):
        assert buildx._workspace_root() == nowhere
    assert 'No workspace root found' in caplog.text
    assert 'src/' in caplog.text


def test_verb_is_quiet_inside_a_workspace(workspace, monkeypatch, caplog):
    monkeypatch.chdir(workspace / 'src' / 'pkg')
    with caplog.at_level(logging.WARNING):
        assert buildx._workspace_root() == workspace
    assert caplog.text == ''


def test_builders_use_the_root_they_are_given(workspace, nowhere):
    assert docker.DockerBuilder(
        'img:jazzy', 'linux/arm64', 'b', 'i', use_base_image=True,
        workspace_root=workspace).workspace_root == workspace
    assert SdkBuilder('/sdk/env', 'b', 'i', workspace_root=workspace).workspace_root == workspace
    assert SysrootBuilder(
        'my-board', '~/mnt/board-sysroot', 'tc.cmake', 'b', 'i',
        workspace_root=workspace).workspace_root == workspace
