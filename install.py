import sys
from os import environ, stat, chmod
from os.path import dirname, realpath
from os import remove
from shutil import copyfile
from pathlib import Path
import subprocess


def app_dir() -> str:
    """Get app dir."""
    return environ.get('APP_DIR', dirname(realpath(__file__)))


def windows():
    """Prepare windows install."""
    dot_binary = Path(app_dir()) / 'dot.bat'
    dot_binary = dot_binary.as_posix()

    if Path(dot_binary).exists():
        remove(dot_binary)

    file_commands = [
        f'@echo off',
        f'set APP_DIR={app_dir()}',
        r'set VENV=%APP_DIR%venv',
        r'call %VENV%\Scripts\activate & python -u "%APP_DIR%dot.py" %*',
    ]

    with open(dot_binary, 'w') as dot_file:
        for line in file_commands:
            dot_file.write(f'{line}\n')
        dot_file.close()


def make_executable(path):
    """CHMOD -x for unix like."""
    mode = stat(path).st_mode
    mode |= (mode & 0o444) >> 2
    chmod(path, mode)


def linux():
    """Prepare linux install."""
    dot_binary = Path.home() / '.local' / 'bin' / 'dot'
    dot_binary = dot_binary.as_posix()

    if Path(dot_binary).exists():
        remove(dot_binary)

    file_commands = [
        '#!/bin/bash',
        'args=("$@")',
        f'APP_DIR="{app_dir()}"',
        'ENV_DIR=$APP_DIR/.venv',
        'CMD_FILE=$APP_DIR/dot.py',
        'function command {',
        '\t export APP_DIR=$APP_DIR && \\',
        '\t export DOT_CONF=$DOT_CONF && \\',
        '\t source $ENV_DIR/bin/activate && \\',
        '\t python -u $CMD_FILE ${args[0]} ${args[1]} ${args[2]};',
        '}',
        'function dot() {',
        '\tcommand',
        '}',
        'dot',
    ]

    with open(dot_binary, 'w') as dot_file:
        for line in file_commands:
            dot_file.write(f'{line}\n')
        dot_file.close()
    make_executable(dot_binary)


def install() -> None:
    """Prepare system."""
    if 'win' in str(sys.platform):
        windows()
    else:
        linux()

    conf_path = Path(app_dir()) / 'config.yml'
    if not Path(conf_path).exists():
        copyfile(Path(app_dir()) / 'config.example.yml', conf_path)


install()
