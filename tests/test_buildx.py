import argparse
import sys

import pytest

from colcon_buildx import docker
from colcon_buildx.config import merge_settings
from colcon_buildx.sdk import SdkBuilder
from colcon_buildx.toolchain import WRAPPER_NAME, wrapper_text
from colcon_buildx.verb.buildx import BuildxVerb, CONFIG_KEYS, DEFAULTS


@pytest.fixture
def parser():
    parser = argparse.ArgumentParser()
    BuildxVerb().add_arguments(parser=parser)
    return parser


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    # Resolved: on macOS the temp dir is reached through a /var -> /private/var
    # symlink, and the builders locate the workspace from the resolved cwd.
    root = tmp_path.resolve()
    (root / 'src').mkdir()
    monkeypatch.chdir(root)
    return root


# --- config precedence --------------------------------------------------------

@pytest.mark.parametrize('key, value', [
    ('method', 'sysroot'),
    ('docker_platform', 'linux/arm/v7'),
    ('build_base', 'foo'),
    ('deploy', True),
    ('docker_image', 'x:tag'),
])
def test_config_file_value_applies_when_flag_not_given(parser, key, value):
    args = parser.parse_args([])
    merge_settings(args, {key: value}, DEFAULTS, CONFIG_KEYS)
    assert getattr(args, key) == value


def test_command_line_beats_config_file(parser):
    args = parser.parse_args(['--docker-platform', 'linux/arm64'])
    merge_settings(args, {'docker_platform': 'linux/arm/v7'}, DEFAULTS, CONFIG_KEYS)
    assert args.docker_platform == 'linux/arm64'


def test_defaults_fill_whatever_is_left(parser):
    args = parser.parse_args([])
    merge_settings(args, None, DEFAULTS, CONFIG_KEYS)
    for key, value in DEFAULTS.items():
        assert getattr(args, key) == value


def test_unknown_config_key_is_reported(parser):
    args = parser.parse_args([])
    unknown = merge_settings(args, {'docker_platfrom': 'x'}, DEFAULTS, CONFIG_KEYS)
    assert unknown == ['docker_platfrom']


# --- toolchain wrapper --------------------------------------------------------

def test_wrapper_includes_sdk_toolchain_from_environment_by_default():
    assert 'include("$ENV{OE_CMAKE_TOOLCHAIN_FILE}")' in wrapper_text('/i')


def test_wrapper_adds_install_prefix_to_normalized_find_roots():
    text = wrapper_text('/i')
    assert 'REALPATH' in text
    assert 'set(CMAKE_FIND_ROOT_PATH ${_buildx_roots} "/i")' in text


def test_wrapper_hands_ament_prefixes_to_cmake():
    assert 'string(REPLACE ":" ";" _buildx_ament "$ENV{AMENT_PREFIX_PATH}")' \
        in wrapper_text('/i')


# --- docker backend -----------------------------------------------------------

OE_SDK_IMAGE = {'Config': {'Labels': {
    docker.LABEL_KIND: docker.KIND_OE_SDK,
    docker.LABEL_ENV_SETUP: '/opt/sdk/environment-setup-x:/opt/sdk/ros-sdk-env.sh',
    docker.LABEL_ROS_DISTRO: 'humble',
}}}


def _builder(image='img:jazzy'):
    return docker.DockerBuilder(
        image, 'linux/arm64', 'cross_build', 'cross_install', use_base_image=True)


def test_image_without_labels_is_ros_apt(workspace):
    builder = _builder()
    builder._apply_labels({'Config': {'Labels': None}})
    assert builder.kind == docker.KIND_ROS_APT


def test_labels_select_oe_sdk_and_distro(workspace):
    builder = _builder()
    builder._apply_labels(OE_SDK_IMAGE)
    assert builder.kind == docker.KIND_OE_SDK
    assert builder.env_setup == [
        '/opt/sdk/environment-setup-x', '/opt/sdk/ros-sdk-env.sh']
    assert builder.detect_ros_distro() == 'humble'


def test_native_image_runs_as_target_platform(workspace):
    cmd = _builder()._native_command(workspace / 'b', workspace / 'i', [])
    assert cmd[cmd.index('--platform') + 1] == 'linux/arm64'


def test_native_command_quotes_passthrough_args(workspace):
    cmd = _builder()._native_command(
        workspace / 'b', workspace / 'i', ['--packages-select', 'my pkg'])
    assert "'my pkg'" in cmd[-1]


def test_sdk_image_runs_host_native_through_the_wrapper(workspace):
    builder = _builder()
    builder._apply_labels(OE_SDK_IMAGE)
    build = workspace / 'cross_build'
    build.mkdir()

    cmd = builder._oe_sdk_command(build, workspace / 'cross_install', [])

    assert '--platform' not in cmd
    script = cmd[-1]
    assert script.count('. /opt/sdk/') == 2
    assert f'export CMAKE_TOOLCHAIN_FILE=/workspace/cross_build/{WRAPPER_NAME}' in script
    assert '--cmake-args' not in script
    assert (build / WRAPPER_NAME).read_text() == wrapper_text('/workspace/cross_install')


def test_sdk_image_without_ros_sdk_env_fails_loudly(workspace):
    builder = _builder()
    builder._apply_labels(OE_SDK_IMAGE)
    (workspace / 'cross_build').mkdir()
    script = builder._oe_sdk_command(
        workspace / 'cross_build', workspace / 'cross_install', [])[-1]
    assert '[ -z "$OE_CMAKE_TOOLCHAIN_FILE" ]' in script
    assert 'exit 1' in script
    assert 'nativesdk-ros-sdk-env' in script


# --- sdk backend --------------------------------------------------------------

def test_sdk_wrapper_is_written_into_the_build_base(workspace):
    builder = SdkBuilder('/sdk/env', 'cross_build', 'cross_install')
    wrapper = builder.write_toolchain_wrapper('/sdk/tc.cmake')
    assert wrapper == workspace / 'cross_build' / WRAPPER_NAME
    assert wrapper.read_text() == wrapper_text(workspace / 'cross_install', '/sdk/tc.cmake')
    assert not (workspace / 'install').exists()


def test_sdk_mixin_points_at_the_wrapper(workspace):
    builder = SdkBuilder('/sdk/env', 'cross_build', 'cross_install')
    builder.write_mixin({
        'OE_CMAKE_TOOLCHAIN_FILE': '/sdk/tc.cmake',
        'PYTHON_SOABI': 'cpython-312-aarch64-linux-gnu',
    })
    mixin = (workspace / '.buildx' / 'mixin' / 'buildx.mixin').read_text()
    assert f'-DCMAKE_TOOLCHAIN_FILE={workspace / "cross_build" / WRAPPER_NAME}' in mixin
    assert '-DPYTHON_SOABI=cpython-312-aarch64-linux-gnu' in mixin


@pytest.mark.skipif(sys.platform.startswith('linux'), reason='the guard only fires off Linux')
def test_sdk_method_refuses_non_linux_hosts(workspace):
    assert SdkBuilder('/sdk/env', 'b', 'i').check_host() is False
