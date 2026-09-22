# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

import argparse
import re

import pytest

from colcon_buildx.config import CONFIG_NAMES
from colcon_buildx.verb.buildx import BuildxVerb, CONFIG_KEYS, DEFAULTS


@pytest.fixture
def parser(monkeypatch):
    # argparse wraps to the terminal width; pin it so the text is stable.
    monkeypatch.setenv('COLUMNS', '80')
    parser = argparse.ArgumentParser(prog='colcon buildx')
    BuildxVerb().add_arguments(parser=parser)
    return parser


@pytest.fixture
def help_text(parser):
    return parser.format_help()


def _option(parser, dest):
    return next(a for a in parser._actions if a.dest == dest)


def _group_of(parser, dest):
    return next(g.title for g in parser._action_groups
                if any(a.dest == dest for a in g._group_actions))


def test_every_config_key_is_an_option(parser):
    dests = {a.dest for a in parser._actions}
    assert CONFIG_KEYS <= dests


def test_every_config_key_is_spelled_like_its_flag(parser):
    for key in CONFIG_KEYS:
        assert '--' + key.replace('_', '-') in _option(parser, key).option_strings


@pytest.mark.parametrize('key', sorted(k for k, v in DEFAULTS.items() if isinstance(v, str)))
def test_help_shows_the_defaults_the_code_applies(parser, key):
    assert DEFAULTS[key] in _option(parser, key).help


def test_no_argparse_defaults_hide_the_config_file(parser):
    # merge_settings only fills options that are still None after parsing.
    args = parser.parse_args([])
    for key in CONFIG_KEYS:
        assert getattr(args, key) is None, key


def test_sdk_examples_use_the_oe_linux_script(help_text):
    assert 'poky' not in help_text
    assert 'environment-setup-cortexa72-cortexa53-oe-linux' in help_text


def test_install_deps_is_documented_per_method_with_the_dependency_options(parser):
    assert _group_of(parser, 'install_deps') == 'Dependency options'
    assert _group_of(parser, 'rosdep_args') == 'Dependency options'
    text = _option(parser, 'install_deps').help
    for method in ('--method docker', '--method sysroot', '--method sdk'):
        assert method in text


def test_toolchain_is_not_filed_under_one_method(parser):
    assert _group_of(parser, 'toolchain') not in {
        g.title for g in parser._action_groups if '--method' in (g.title or '')}


def test_epilog_explains_config_files_and_precedence(help_text):
    flat = ' '.join(help_text.split())
    for name in CONFIG_NAMES:
        assert name in flat
    assert 'holds src/' in flat
    assert 'command line > config file > built-in defaults' in flat


def test_option_names_are_not_split_at_hyphens(help_text):
    for line in help_text.splitlines():
        assert not re.search(r'\w-$', line.rstrip()), line
