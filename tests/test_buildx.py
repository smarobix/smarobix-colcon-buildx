# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import sys

import pytest

from colcon_buildx import docker
from colcon_buildx.config import merge_settings
from colcon_buildx.sdk import SdkBuilder
from colcon_buildx.toolchain import WRAPPER_NAME, wrapper_text, write_wrapper
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


def test_identical_wrapper_is_not_rewritten(tmp_path):
    # CMake re-configures every package when an included toolchain file's mtime
    # changes, so rewriting an unchanged wrapper turns each incremental build
    # into a full re-configure.
    path = write_wrapper(tmp_path / WRAPPER_NAME, '/i')
    os.utime(path, (0, 0))

    write_wrapper(path, '/i')
    assert path.stat().st_mtime == 0

    write_wrapper(path, '/other')
    assert path.stat().st_mtime != 0
    assert path.read_text() == wrapper_text('/other')


# --- docker backend -----------------------------------------------------------

OE_SDK_IMAGE = {'Config': {'Labels': {
    docker.LABEL_KIND: docker.KIND_OE_SDK,
    docker.LABEL_ENV_SETUP: '/opt/sdk/environment-setup-x:/opt/sdk/ros-sdk-env.sh',
    docker.LABEL_ROS_DISTRO: 'humble',
}}}


def _builder(image='img:jazzy'):
    return docker.DockerBuilder(
        image, 'linux/arm64', 'cross_build', 'cross_install', use_base_image=True)


def _script(cmd):
    """The build script of a docker run command; it travels as BUILDX_SCRIPT."""
    return next(a.split('=', 1)[1] for a in cmd if a.startswith('BUILDX_SCRIPT='))


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


def test_no_image_runs_under_emulation(workspace):
    # Every image colcon buildx runs is the host's own architecture: an SDK, a
    # dev container of the host's architecture, or a cross image it built.
    builder = _builder()
    (workspace / 'b').mkdir()
    for command in (builder._native_command, builder._oe_sdk_command, builder._cross_command):
        assert '--platform' not in command(workspace / 'b', workspace / 'i', [])


def test_native_image_sources_its_ros_setup(workspace):
    cmd = _builder()._native_command(workspace / 'b', workspace / 'i', [])
    assert _script(cmd).startswith('. /opt/ros/jazzy/setup.sh && colcon ')


def test_prepared_native_image_sources_its_env_script(workspace):
    builder = _builder()
    builder._apply_labels({'Config': {'Labels': {
        docker.LABEL_KIND: docker.KIND_YOCTO_NATIVE,
        docker.LABEL_ENV_SETUP: '/opt/buildx/env.sh'}}})
    script = _script(builder._native_command(workspace / 'b', workspace / 'i', []))
    assert script.startswith('. /opt/buildx/env.sh && colcon ')


def test_scripts_run_in_bash_if_present_else_sh(workspace):
    cmd = _builder()._native_command(workspace / 'b', workspace / 'i', [])
    assert cmd[-3:-1] == ['sh', '-c']
    assert 'command -v bash' in cmd[-1] and 'exec sh -c' in cmd[-1]
    assert cmd[cmd.index('--entrypoint') + 1] == ''


def test_cross_image_builds_with_its_toolchain_and_install_root(workspace):
    builder = _builder()
    builder._apply_labels({'Config': {'Labels': {
        docker.LABEL_KIND: docker.KIND_SYSROOT_CROSS,
        docker.LABEL_ENV_SETUP: '/opt/buildx/env.sh',
        docker.LABEL_TOOLCHAIN: '/opt/buildx/toolchain.cmake'}}})
    script = _script(builder._cross_command(workspace / 'b', workspace / 'i', []))
    assert script.startswith('set -e && . /opt/buildx/env.sh && ')
    assert 'export BUILDX_INSTALL_BASE=/workspace/cross_install' in script
    assert 'export CMAKE_TOOLCHAIN_FILE=/opt/buildx/toolchain.cmake' in script


def test_native_command_quotes_passthrough_args(workspace):
    cmd = _builder()._native_command(
        workspace / 'b', workspace / 'i', ['--packages-select', 'my pkg'])
    assert "'my pkg'" in _script(cmd)


def test_sdk_image_runs_host_native_through_the_wrapper(workspace):
    builder = _builder()
    builder._apply_labels(OE_SDK_IMAGE)
    build = workspace / 'cross_build'
    build.mkdir()

    cmd = builder._oe_sdk_command(build, workspace / 'cross_install', [])

    assert '--platform' not in cmd
    script = _script(cmd)
    assert script.count('. /opt/sdk/') == 2
    assert f'export CMAKE_TOOLCHAIN_FILE=/workspace/cross_build/{WRAPPER_NAME}' in script
    assert '--cmake-args' not in script
    assert (build / WRAPPER_NAME).read_text() == wrapper_text('/workspace/cross_install')


def test_sdk_image_without_ros_sdk_env_fails_loudly(workspace):
    builder = _builder()
    builder._apply_labels(OE_SDK_IMAGE)
    (workspace / 'cross_build').mkdir()
    script = _script(builder._oe_sdk_command(
        workspace / 'cross_build', workspace / 'cross_install', []))
    assert '[ -z "$OE_CMAKE_TOOLCHAIN_FILE" ]' in script
    assert 'exit 1' in script
    assert '--toolchain' in script


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


# --- running as the invoking user ---------------------------------------------

@pytest.mark.skipif(not hasattr(os, 'getuid') or os.getuid() == 0,
                    reason='only a non-root caller is remapped')
@pytest.mark.parametrize('sdk_image', [False, True])
def test_containers_run_as_the_invoking_user(workspace, sdk_image):
    builder = _builder()
    if sdk_image:
        builder._apply_labels(OE_SDK_IMAGE)
    (workspace / 'cross_build').mkdir()
    command = builder._oe_sdk_command if sdk_image else builder._native_command
    cmd = command(workspace / 'cross_build', workspace / 'cross_install', [])
    assert cmd[cmd.index('--user') + 1] == f'{os.getuid()}:{os.getgid()}'
    assert 'HOME=/tmp' in cmd


@pytest.mark.parametrize('sdk_image', [False, True])
def test_colcon_logs_land_in_the_mounted_build_base(workspace, sdk_image):
    builder = _builder()
    if sdk_image:
        builder._apply_labels(OE_SDK_IMAGE)
    (workspace / 'cross_build').mkdir()
    command = builder._oe_sdk_command if sdk_image else builder._native_command
    script = _script(command(workspace / 'cross_build', workspace / 'cross_install', []))
    assert 'colcon --log-base /workspace/cross_build/log build' in script


def test_sdk_builds_use_ninja_only_when_available_and_unchosen(workspace):
    builder = _builder()
    builder._apply_labels(OE_SDK_IMAGE)
    (workspace / 'cross_build').mkdir()
    script = _script(builder._oe_sdk_command(
        workspace / 'cross_build', workspace / 'cross_install', []))
    assert ('if [ -z "${CMAKE_GENERATOR:-}" ] && command -v ninja >/dev/null; then '
            'export CMAKE_GENERATOR=Ninja; fi') in script


# --- --toolchain with the docker backend --------------------------------------

def test_toolchain_replaces_the_sdk_toolchain_in_a_cross_sdk_image(workspace):
    builder = docker.DockerBuilder(
        'img:jazzy', 'linux/arm64', 'cross_build', 'cross_install',
        use_base_image=True, toolchain='/opt/sdk/my-toolchain.cmake')
    builder._apply_labels(OE_SDK_IMAGE)
    build = workspace / 'cross_build'
    build.mkdir()

    script = _script(builder._oe_sdk_command(build, workspace / 'cross_install', []))

    assert (build / WRAPPER_NAME).read_text() == wrapper_text(
        '/workspace/cross_install', '/opt/sdk/my-toolchain.cmake')
    # The SDK need not export a toolchain file when the user named one.
    assert 'OE_CMAKE_TOOLCHAIN_FILE' not in script
    assert f'export CMAKE_TOOLCHAIN_FILE=/workspace/cross_build/{WRAPPER_NAME}' in script


def test_toolchain_is_ignored_with_a_warning_by_a_native_image(workspace, caplog):
    builder = docker.DockerBuilder(
        'img:jazzy', 'linux/arm64', 'cross_build', 'cross_install',
        use_base_image=True, toolchain='/opt/sdk/my-toolchain.cmake')
    with caplog.at_level('WARNING'):
        cmd = builder._native_command(workspace / 'b', workspace / 'i', [])
    assert 'my-toolchain' not in ' '.join(cmd)
    assert 'Ignoring --toolchain' in caplog.text


# --- synced images and cross SDK images ---------------------------------------

def test_synced_image_must_come_from_the_same_repository(workspace, monkeypatch):
    base = 'ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy'
    listing = 'docker.io/someone/mirror:k26-jazzy-synced-20260922\n'

    def run(cmd, **kwargs):
        return docker.subprocess.CompletedProcess(cmd, 0, stdout=listing)

    monkeypatch.setattr(docker.subprocess, 'run', run)
    builder = docker.DockerBuilder(base, 'linux/arm64', 'cross_build', 'cross_install')
    assert builder.image == base


def test_install_deps_leaves_a_cross_sdk_image_alone(workspace, monkeypatch):
    from colcon_buildx import rosdep_manager

    monkeypatch.setattr(docker.DockerBuilder, '_inspect', lambda self, image=None: OE_SDK_IMAGE)
    monkeypatch.setattr(rosdep_manager, 'install_deps_docker',
                        lambda *a, **k: pytest.fail('ran rosdep in a cross SDK image'))
    builder = _builder()
    assert builder.install_dependencies() == builder.image


# --- docker_platform and multi-platform board images ---------------------------

class FakeDocker:
    """
    Docker on an *host* computer with one board image, `multi:tag`.

    The registry has the image's *variants*; locally there is the host's
    variant only, until a `docker pull --platform` fetches another.
    """

    def __init__(self, host='arm64', variants=('linux/arm64', 'linux/arm/v7'), labels=None,
                 old_api=False):
        self.host = host
        self.variants = set(variants)
        self.local = {f'linux/{host}'} & self.variants
        self.labels = labels or {}
        self.commands = []
        self.crossed = None
        # Docker before API 1.49 has no `image inspect --platform`, and its tag
        # is whichever variant was pulled last.
        self.old_api = old_api
        self.current = f'linux/{host}'

    def inspect(self, image, platform=None):
        if image.startswith('colcon-buildx:cross-'):
            return {'Architecture': self.host, 'Config': {'Labels': {
                docker.LABEL_KIND: docker.KIND_SYSROOT_CROSS,
                docker.LABEL_ENV_SETUP: '/opt/buildx/env.sh',
                docker.LABEL_TOOLCHAIN: '/opt/buildx/toolchain.cmake',
                docker.LABEL_TARGET_PLATFORM: self.crossed}}}
        if platform and self.old_api:
            return None
        platform = platform or (self.current if self.old_api else f'linux/{self.host}')
        if platform not in self.local:
            return None
        arch = platform.split('/')[1]
        return {'Id': f'sha256:{arch}', 'Architecture': arch,
                'Variant': platform.split('/')[2] if platform.count('/') == 2 else '',
                'Config': {'Labels': dict(self.labels)}}

    def derive_cross(self, image, inspected):
        self.crossed = docker.images.image_platform(inspected)
        return 'colcon-buildx:cross-test'

    def run(self, cmd, **kwargs):
        self.commands.append(cmd)
        if cmd[:3] == ['docker', 'pull', '--platform']:
            if cmd[3] not in self.variants:
                return docker.subprocess.CompletedProcess(cmd, 1)
            self.local.add(cmd[3])
            self.current = cmd[3]
        return docker.subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

    def builds(self):
        """The image of every `docker run` that built."""
        return [cmd[-4] for cmd in self.commands if cmd[:2] == ['docker', 'run']]


@pytest.fixture
def fake_docker(monkeypatch):
    def install(**kwargs):
        fake = FakeDocker(**kwargs)
        monkeypatch.setattr(docker.images, 'inspect', fake.inspect)
        monkeypatch.setattr(docker.images, 'host_arch', lambda: fake.host)
        monkeypatch.setattr(docker.images, 'derive_cross', fake.derive_cross)
        monkeypatch.setattr(docker.subprocess, 'run', fake.run)
        return fake
    return install


def _multi_builder(platform):
    return docker.DockerBuilder(
        'multi:tag', platform, 'cross_build', 'cross_install', use_base_image=True)


def test_docker_platform_picks_the_boards_variant_of_a_multi_platform_image(
        workspace, fake_docker):
    # Docker pulls and runs the host's variant by default; building in it would
    # make arm64 binaries for an armhf board.
    fake = fake_docker()
    assert _multi_builder('linux/arm/v7').build([]) == 0
    assert ['docker', 'pull', '--platform', 'linux/arm/v7', 'multi:tag'] in fake.commands
    assert fake.crossed == 'linux/arm/v7'
    assert fake.builds() == ['colcon-buildx:cross-test']


def test_docker_platform_of_the_hosts_architecture_builds_in_the_image(workspace, fake_docker):
    fake = fake_docker(host='amd64', variants=('linux/amd64', 'linux/arm64'))
    assert _multi_builder('linux/arm64').build([]) == 0
    assert fake.crossed == 'linux/arm64'

    fake = fake_docker()
    assert _multi_builder('linux/arm64').build([]) == 0
    assert fake.crossed is None and fake.builds() == ['multi:tag']


def test_without_docker_platform_the_image_is_used_as_it_is(workspace, fake_docker):
    fake = fake_docker()
    assert _multi_builder(None).build([]) == 0
    assert fake.crossed is None and fake.builds() == ['multi:tag']
    assert not any(cmd[:2] == ['docker', 'pull'] for cmd in fake.commands)


def test_docker_platform_works_on_a_docker_without_inspect_platform(workspace, fake_docker):
    fake = fake_docker(old_api=True)
    assert _multi_builder('linux/arm/v7').build([]) == 0
    assert fake.crossed == 'linux/arm/v7'


def test_a_host_build_from_an_unknown_image_says_how_to_build_for_a_board(
        workspace, fake_docker, capsys):
    # The official ROS images carry OCI labels, but none of colcon buildx's.
    fake_docker(host='amd64', variants=('linux/amd64', 'linux/arm64'),
                labels={'org.opencontainers.image.version': '24.04'})
    assert _multi_builder(None).build([]) == 0
    assert 'set docker_platform' in capsys.readouterr().out


def test_an_image_without_the_platforms_variant_is_refused(workspace, fake_docker):
    fake = fake_docker(variants=('linux/arm64',))
    assert _multi_builder('linux/arm/v7').build([]) == 1
    assert fake.builds() == []


def test_an_sdk_image_ignores_docker_platform(workspace, fake_docker, monkeypatch):
    fake = fake_docker(labels=dict(OE_SDK_IMAGE['Config']['Labels']))
    monkeypatch.setattr(docker.images, 'prepare', lambda image, inspected, kind: image)
    assert _multi_builder('linux/arm/v7').build([]) == 0
    assert not any(cmd[:2] == ['docker', 'pull'] for cmd in fake.commands)


def test_install_deps_runs_the_hosts_image_without_a_platform(workspace, fake_docker):
    # The README's one supported case: an image of the host's architecture.
    fake = fake_docker(host='amd64', variants=('linux/amd64', 'linux/arm64'))
    pkg = workspace / 'src' / 'p'
    pkg.mkdir()
    (pkg / 'package.xml').write_text(
        '<package format="3"><name>p</name><depend>rclcpp</depend></package>')
    assert _multi_builder(None).install_dependencies()
    runs = [cmd for cmd in fake.commands if cmd[:2] == ['docker', 'run']]
    assert len(runs) == 1 and '--platform' not in runs[0]


def test_install_deps_refuses_a_board_of_another_architecture(workspace, fake_docker):
    # With docker_platform naming another architecture, the build uses that
    # variant; installing into the host's variant would install into the wrong one.
    fake = fake_docker(host='amd64', variants=('linux/amd64', 'linux/arm64'))
    assert _multi_builder('linux/arm64').install_dependencies() is None
    assert not any(cmd[:2] == ['docker', 'run'] for cmd in fake.commands)
