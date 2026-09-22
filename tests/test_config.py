# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

import argparse
import re
from pathlib import Path

import pytest

from colcon_buildx.config import (
    find_config_file, load_config, load_conf_config, load_yaml_config,
    merge_settings,
)
from colcon_buildx.verb.buildx import BuildxVerb, CONFIG_KEYS, DEFAULTS

EXAMPLES = Path(__file__).resolve().parent.parent / 'examples'

# A commented-out setting in an example, as opposed to a descriptive comment:
# "# key = value" in the .conf file, "# key: value" in the YAML one.
COMMENTED_SETTING = {
    '.conf': re.compile(r'^# ?([a-z_]+ = .*)$'),
    '.yml': re.compile(r'^# ?([a-z_]+: .*)$'),
}


@pytest.fixture
def parser():
    parser = argparse.ArgumentParser()
    BuildxVerb().add_arguments(parser=parser)
    return parser


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path.resolve() / 'ws'
    (root / 'src' / 'pkg').mkdir(parents=True)
    monkeypatch.chdir(root)
    return root


# --- .conf format -------------------------------------------------------------

def test_conf_parses_comments_quotes_and_booleans(tmp_path):
    path = tmp_path / '.buildx.conf'
    path.write_text(
        '# a comment\n'
        '\n'
        'docker_image = "ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy"\n'
        "rosdep_args = '--ignore-src -y -r'\n"
        'deploy = true\n'
        'no_mount = no\n'
        'deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/\n'
    )
    assert load_conf_config(path) == {
        'docker_image': 'ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy',
        'rosdep_args': '--ignore-src -y -r',
        'deploy': True,
        'no_mount': False,
        'deploy_target': 'ubuntu@10.42.0.3:~/ros2_ws/install/',
    }


# --- YAML format --------------------------------------------------------------

def test_yaml_parses_native_types(tmp_path):
    path = tmp_path / '.buildx.yml'
    path.write_text('docker_platform: linux/arm/v7\ndeploy: true\n')
    assert load_yaml_config(path) == {'docker_platform': 'linux/arm/v7', 'deploy': True}


def test_empty_yaml_is_an_empty_config(tmp_path):
    path = tmp_path / '.buildx.yml'
    path.write_text('# nothing set\n')
    assert load_yaml_config(path) == {}


def test_yaml_that_is_not_a_mapping_is_rejected(tmp_path):
    path = tmp_path / '.buildx.yml'
    path.write_text('- method\n- docker\n')
    assert load_config(path) is None


@pytest.mark.parametrize('name, text', [
    ('.buildx.conf', 'docker-platform = linux/arm/v7\nsdk-env = /opt/sdk/env\n'),
    ('.buildx.yml', 'docker-platform: linux/arm/v7\nsdk-env: /opt/sdk/env\n'),
])
def test_hyphenated_keys_become_underscores_in_both_formats(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    assert load_config(path) == {'docker_platform': 'linux/arm/v7', 'sdk_env': '/opt/sdk/env'}


# --- finding the file ---------------------------------------------------------

def test_config_is_found_from_a_subdirectory_of_the_workspace(workspace, monkeypatch):
    (workspace / '.buildx.yml').write_text('method: sdk\n')
    monkeypatch.chdir(workspace / 'src' / 'pkg')
    assert find_config_file() == workspace / '.buildx.yml'


def test_conf_wins_over_yaml_in_the_same_directory(workspace):
    (workspace / '.buildx.yml').write_text('method: sdk\n')
    (workspace / '.buildx.conf').write_text('method = sysroot\n')
    assert find_config_file() == workspace / '.buildx.conf'


def test_nearest_config_wins(workspace, monkeypatch):
    (workspace / '.buildx.conf').write_text('method = sysroot\n')
    (workspace / 'src' / 'pkg' / '.buildx.yaml').write_text('method: sdk\n')
    monkeypatch.chdir(workspace / 'src' / 'pkg')
    assert find_config_file() == workspace / 'src' / 'pkg' / '.buildx.yaml'


def test_search_stops_at_the_workspace_root(workspace):
    (workspace.parent / '.buildx.conf').write_text('method = sysroot\n')
    assert find_config_file() is None


def test_explicit_config_path_is_used_as_given(workspace, tmp_path):
    other = tmp_path / 'elsewhere.yml'
    other.write_text('method: sdk\n')
    (workspace / '.buildx.conf').write_text('method = sysroot\n')
    assert find_config_file(str(other)) == other


def test_missing_explicit_config_path_finds_nothing(workspace):
    (workspace / '.buildx.conf').write_text('method = sysroot\n')
    assert find_config_file(str(workspace / 'missing.conf')) is None


# --- precedence, end to end ---------------------------------------------------

@pytest.mark.parametrize('name, text', [
    ('.buildx.conf', 'docker_platform = linux/arm/v7\nbuild_base = file_build\n'),
    ('.buildx.yml', 'docker_platform: linux/arm/v7\nbuild_base: file_build\n'),
])
def test_command_line_beats_file_beats_defaults(workspace, parser, name, text):
    (workspace / name).write_text(text)
    args = parser.parse_args(['--docker-platform', 'linux/arm64'])

    assert merge_settings(args, load_config(), DEFAULTS, CONFIG_KEYS) == []

    assert args.docker_platform == 'linux/arm64'           # command line
    assert args.build_base == 'file_build'                 # config file
    assert args.install_base == DEFAULTS['install_base']   # default


# --- the shipped examples -----------------------------------------------------

EXAMPLE_NAMES = ['buildx.conf', 'buildx.yml']


def _uncomment_settings(path, tmp_path):
    """Copy an example with every commented-out setting switched on."""
    pattern = COMMENTED_SETTING[path.suffix]
    lines = []
    for line in path.read_text().splitlines():
        match = pattern.match(line)
        lines.append(match.group(1) if match else line)
    copy = tmp_path / path.name
    copy.write_text('\n'.join(lines) + '\n')
    return copy


@pytest.mark.parametrize('name', EXAMPLE_NAMES)
def test_example_sets_a_working_docker_build(parser, name):
    config = load_config(EXAMPLES / name)
    assert config == {
        'method': 'docker',
        'docker_image': 'ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy',
        'docker_platform': 'linux/arm64',
    }
    args = parser.parse_args([])
    assert merge_settings(args, config, DEFAULTS, CONFIG_KEYS) == []


@pytest.mark.parametrize('name', EXAMPLE_NAMES)
def test_example_mentions_every_config_key(parser, name, tmp_path):
    config = load_config(_uncomment_settings(EXAMPLES / name, tmp_path))
    assert set(config) == CONFIG_KEYS
    args = parser.parse_args([])
    assert merge_settings(args, config, DEFAULTS, CONFIG_KEYS) == []


def test_commented_defaults_in_the_examples_match_the_code(tmp_path):
    config = load_config(_uncomment_settings(EXAMPLES / 'buildx.conf', tmp_path))
    for key, value in DEFAULTS.items():
        if key != 'method':  # set to docker, then shown with its alternatives
            assert config[key] == value, key


def test_both_examples_say_the_same(tmp_path):
    conf_dir = tmp_path / 'conf'
    yml_dir = tmp_path / 'yml'
    conf_dir.mkdir()
    yml_dir.mkdir()
    conf = load_config(_uncomment_settings(EXAMPLES / 'buildx.conf', conf_dir))
    yml = load_config(_uncomment_settings(EXAMPLES / 'buildx.yml', yml_dir))
    assert conf == yml
