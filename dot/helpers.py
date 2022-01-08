import os
import sys
import yaml

from base64 import b64decode
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Type, Optional
from time import sleep
from pathlib import Path
from subprocess import Popen, PIPE, STDOUT
import shlex

from humanize import naturaltime as verbose_time

from pydantic import BaseModel
from piny import PydanticValidator, StrictMatcher, YamlLoader

import psycopg

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.theme import Theme
from rich.status import Status as RS
from rich.panel import Panel
from rich import box

from kubernetes.client.api import CoreV1Api
from kubernetes.config import load_kube_config
from kubernetes.config.config_exception import ConfigException


HANG = 'IDpkb2c6IFtkaW0gc3RlZWxfYmx1ZTFdIFBhbmluIGJsZXNzIHlvdSwgYnllIQ=='


class DBModel(BaseModel):
    """DB Model."""

    host: str
    name: str
    user: str
    password: str
    port: int


class EnvModel(BaseModel):
    """Env model."""

    k8s: str
    pull: Dict[str, DBModel]


class ConfigModel(BaseModel):
    """Config model."""

    pg_local: DBModel
    stage: EnvModel
    prod: EnvModel


class DotError(Exception):
    """Dot error."""


@dataclass
class AppInfo:

    # Pacific Standard Time (UTC−08:00)
    diff: timedelta

    alias: str
    deployed: str
    restart_count: int
    pod_ips: List[str]
    host_ip: str

    exec: str = ''
    instances: int = 1
    on_rebuild: bool = False


class Env(Enum):
    """Environments."""

    STAGE = 'stage'
    PROD = 'prod'


class Color(Enum):
    """Color enum."""

    LGREY = 'grey70'
    DGREY = 'grey15'
    BORDER = 'bright_black'

    CRITICAL = 'bold blink white on red3'

    DEF = 'grey69'
    ACTIVE = 'white'

    STAGE = 'green4'
    PROD = 'red1'

    @staticmethod
    def env_color(env: str) -> str:
        """Get env color."""
        envs = {
            Env.STAGE.value: Color.STAGE.value,
            Env.PROD.value: Color.PROD.value,
        }
        return envs[env]


TERM_ENV = {
    'light_gray': Color.LGREY.value,
    'dark_gray': Color.DGREY.value,
    'critical': Color.CRITICAL.value,
    'border': Color.BORDER.value,
    'repr.number': 'cyan',
}

TERM_STAGE = {
    'repr.str': 'bold honeydew2',
}
TERM_STAGE.update(TERM_ENV)

TERM_PROD = {
    'repr.str': 'bold light_salmon1',
}
TERM_PROD.update(TERM_ENV)


PG_ERRORS = (
    psycopg.errors.DatabaseError,
    psycopg.errors.OperationalError,
    psycopg.errors.InterfaceError,
)


class Error(Enum):
    """Error enum."""

    CRITICAL = 'Terminated: {0}'

    CFG_NOT_LOADED = 'Config not loaded: {0}'

    DB_PULL_EMPTY = 'Pull configuration not found'
    DB_PULL_NOT_FOUND = 'Not found pull configuration, try: {0}'
    DB_REMOTE_CFG_FOUND = 'Postgres remote config not found: {0}'
    DB_LOCAL_CFG_LOAD = 'Postgres local config not loaded: {0}'
    DB_PG = 'Postgres error: {0}'
    DB_PREPARE_LOCAL = 'Prepare local database: {0}'
    DB_UNKNOWN = 'Unknown pulling error: {0}'

    K8_ENV_NOT_FOUND = 'K8S yaml file not found'
    K8_ENV_CONF_LOAD = 'K8S load config file: {0}'

    @staticmethod
    def found(alias: str, variants: List) -> None:
        """Found error."""
        return create_panel(
            lb='NOT FOUND',
            lb_style='bold grey3 on yellow',
            ctn='The {0} is not found, try: {1}'.format(
                f'[red1 bold]{alias}[/red1 bold]',
                f'[yellow]{variants}[/yellow]',
            ),
            ctn_style='white',
            style='',
        )

    @staticmethod
    def error(err: Enum, details: List[str] = None) -> Panel:
        """Error panel."""
        _msg = str(err.value)
        _msg = _msg if not details else _msg.format(*details)
        return create_panel(
            lb='ERROR',
            lb_style=Color.CRITICAL.value,
            ctn=_msg,
            ctn_style='white',
            style='red3 on black',
        )


class Exec:
    """CMD Linux enum."""

    @staticmethod
    def cmd_log() -> str:
        """Get log command."""
        app = 'kubectl'
        cmd = '--kubeconfig="{0}" -n {1} logs -f deployment/{2}'
        extra = '--all-containers=true --since=24h'
        return f'{app} {cmd} {extra}'

    @staticmethod
    def cmd_config() -> str:
        """Get config command."""
        app = 'kubectl'
        cmd = '--kubeconfig="{0}" -n {1} exec {2} -c {3} -- {4}'
        return f'{app} {cmd}'

    @staticmethod
    def cmd_dump() -> str:
        """Get dump command."""
        app = 'pg_dump'
        cmd = '-v -U {0} -h {1} -p {2} --dbname {3} -Fc -f {4}'
        return f'{app} {cmd}'

    @staticmethod
    def cmd_restore() -> str:
        """Get restore command."""
        app = 'pg_restore'
        cmd = '-v -U {0} -h {1} --clean --no-acl --no-owner --dbname {2} {3}'
        return f'{app} {cmd}'

    @staticmethod
    def _process(command: str, **kwargs):
        """Build subproc command."""
        if not kwargs.get('stdout'):
            kwargs['stdout'] = PIPE
        if not kwargs.get('stderr'):
            kwargs['stderr'] = STDOUT
        return Popen(shlex.split(command), **kwargs)

    @staticmethod
    def process_dump(cfg: Dict, path: str) -> Type[Popen]:
        """POpen dump process."""
        cmd = Exec.cmd_dump()
        return Exec._process(
            cmd.format(cfg['user'], cfg['host'], cfg['port'], cfg['name'], path),
            **{'env': {'PGPASSWORD': cfg['password']}},
        )

    @staticmethod
    def capture_dump(proc: Popen, env: str, ref: RS) -> None:
        """Capture dump."""
        _opts = {'header': Msg.DOWNLOAD.value, 'env': env, 'rem': 'pg_dump:'}
        for outline in iter(proc.stdout.readline, b''):
            buff = str(outline.decode())
            if 'error:' in buff:
                raise DotError('Check pull connection params')
            _opts.update({'text': buff})
            Status.pull_update(ref, _opts)

    @staticmethod
    def process_restore(cfg: Dict, alias, path: str) -> Type[Popen]:
        """POpen restore process."""
        cmd = Exec.cmd_restore()
        return Exec._process(cmd.format(cfg['user'], cfg['host'], alias, path))

    @staticmethod
    def capture_restore(proc: Popen, env: str, ref: RS) -> None:
        """Capture restore."""
        _opts = {'header': Msg.RESTORE.value, 'env': env, 'rem': 'pg_restore:'}
        for outline in iter(proc.stdout.readline, b''):
            _opts.update({'text': str(outline.decode())})
            Status.pull_update(ref, _opts)

    @staticmethod
    def process_config(
        name: str,
        info: AppInfo,
        env: str,
        k8s: str,
    ) -> Type[Popen]:
        """POpen config process."""
        cmd = Exec.cmd_config()
        return Exec._process(
            cmd.format(k8s, env, info.alias, name, 'cat ./config.yml'),
        )

    @staticmethod
    def process_log(
        name: str,
        env: str,
        k8s: str,
        hours: int = 24,
    ) -> Type[Popen]:
        """POpen log process."""
        cmd = Exec.cmd_log()
        zz = cmd.format(k8s, env, name, hours)
        return Exec._process(cmd.format(k8s, env, name, hours))


class Status(Enum):
    """Status enum."""

    @staticmethod
    def pull_update(ref: RS, fields: Dict) -> None:
        """Status pull update."""
        ref.update(status=Status.pull_status(**fields))

    @staticmethod
    def pull_status(
        env: str,
        header: str,
        text: str = None,
        rem: str = None,
    ) -> str:
        """Term pulling progress status text."""
        _active, _text = Color.env_color(env), None
        head = f'[bold {_active}]{header}[/ bold {_active}]'
        if text:
            _text = text.replace(rem, '') if rem else text
            if len(_text) > 100:
                _text = f'{_text[:95]} ... '
        body = '[dim white] {0}'.format(_text) if text else ''
        return '{0}{1}'.format(head, body)

    @staticmethod
    def pull_loader() -> Dict:
        """Status loader params."""
        return {
            'status': None,
            'spinner': 'dots',
            'spinner_style': 'white bold',
        }


class Msg(Enum):
    """Msg enum."""

    PULL = 'PULLING DATABASE'
    DOWNLOAD = 'DOWNLOAD'
    RESTORE = 'RESTORE'

    @staticmethod
    def info(text: str, env: str) -> Panel:
        """Info panel."""
        _active, _dim = Color.env_color(env), 'white'
        env_style = f'{_dim} on {_active} bold'
        info_style = f'bold {Color.DGREY.value} on {Color.LGREY.value}'
        panel_style = f'{Color.BORDER.value} on black'
        label = '[{0}] {1} [/{0}][{2}] INFO [/{2}] '.format(
            env_style,
            env.upper(),
            info_style,
        )
        return Panel(f'{label} {text}', style=panel_style, box=box.HEAVY)

    @staticmethod
    def pull_info(env: str, alias: str, local_conf: str) -> str:
        """Pull info text."""
        return '[{0}]Database {1} was pulled to local:[/{0}] {2}'.format(
            'white',
            f'[bold]{alias}[/bold]',
            f'[yellow]{dba(env, alias)}[yellow]',
        )

    @staticmethod
    def hang() -> str:
        """Hang."""
        return b64decode(HANG).decode().rjust(1)


def create_panel(
    lb: str,
    ctn: str,
    lb_style: str = None,
    ctn_style: str = None,
    style: str = None,
) -> Panel:
    """Create panel."""
    _lb = lb if not lb_style else '[{1}] {0} [/{1}]'.format(lb, lb_style)
    _cnt = ctn if not ctn_style else '[{1}]{0}[/{1}]'.format(ctn, ctn_style)
    _style = style if style else ''
    return Panel(f'{_lb} {_cnt}', style=_style, box=box.HEAVY)


def dba(env: str, alias: str) -> str:
    """Return dba."""
    return f'{env}_{alias}'


def dba_file(workdir: str, real_db_name: str) -> str:
    """Real db path."""
    _cache_dir = Path(workdir) / '.cache'
    if not Path(_cache_dir).exists():
        os.makedirs(_cache_dir)
    path = _cache_dir / f'{real_db_name}.tar.gz'
    return path.as_posix()


def fn_alias(alias: str, opts) -> str:
    """Return aliased name."""
    fmt_alias = '[active]{0}[dim]{1}'
    fmt_no_alias = '[active]{0}[dim]({1})'
    if alias not in opts.alias:
        return fmt_no_alias.format(alias, opts.alias)
    return fmt_alias.format(alias, opts.alias.replace(alias, ''))


def fn_exec_args(opts) -> str:
    """Return exec args."""
    return f'[gray][dim]{str(opts.exec[:30] + "..." if opts.exec else "-")}'


def fn_deployed(opts) -> str:
    """Get dimmed app deployed."""
    if opts.on_rebuild:
        return '[{0}]REBUILDING[/{0}]'.format('blink red1 bold')
    if opts.diff.days > 1:
        return f'[grey53]{opts.deployed}'
    elif opts.diff.seconds > 60 * 60:
        return f'[grey85]{opts.deployed}'
    elif opts.diff.seconds <= 60:
        return f'[blink yellow]{opts.deployed}'
    else:
        return f'[grey85]{opts.deployed}'


def fn_shards(opts) -> str:
    """Get shards info."""
    return f'[dim][grey66]{opts.instances}'


def fn_spiner_style(env: str) -> str:
    """Get spiner style."""
    active = 'bright_green' if env == 'stage' else 'bright_red'
    return f'{active} bold'


def _fmt_runargs(container, pod) -> Optional[str]:
    """Get container run args."""
    for spec in pod.spec.containers:
        if spec.name == container.name:
            if not spec.args:
                return None
            return ' '.join(list(spec.args))


def k8s_apps(k8s: CoreV1Api, env: str) -> Dict[str, AppInfo]:
    """Get k8s apps."""
    _apps: Dict = {}
    _tznow = datetime.now(timezone(timedelta(hours=-8.0)))
    _pods = k8s.list_namespaced_pod(env, limit=150)
    _rebuilds = []

    for _pod in _pods.items:

        if not _pod.status.container_statuses:
            continue

        for _cont in _pod.status.container_statuses:
            if not _cont.name:
                continue

            _name = _cont.name
            _run_state = _cont.state.running

            if not _cont.ready or not getattr(_run_state, 'started_at', False):
                _rebuilds.append(_name)
                continue

            _diff = _tznow - _run_state.started_at

            if _name not in _apps.keys():
                _apps[_name] = AppInfo(
                    alias=_pod.metadata.name,
                    deployed=verbose_time(value=_diff),
                    pod_ips=[_pod.status.pod_ip],
                    host_ip=_pod.status.host_ip,
                    restart_count=_cont.restart_count,
                    exec=_fmt_runargs(_cont, _pod),
                    instances=1,
                    diff=_diff,
                    on_rebuild=True if _name in _rebuilds else False,
                )
                continue

            if _diff < _apps[_name].diff:
                _apps[_name].alias = _pod.metadata.name
                _apps[_name].deployed = verbose_time(value=_diff)
                _apps[_name].restart_count = _cont.restart_count
                _apps[_name].pod_ips.append(_pod.status.pod_ip)
                _apps[_name].host_ip = _pod.status.host_ip
                _apps[_name].instances += 1
                _apps[_name].exec = _fmt_runargs(_cont, _pod)
                _apps[_name].diff = _diff
                _apps[_name].on_rebuild = True if _name in _rebuilds else False

    return _apps


def apps_table(env: str, apps: Dict[str, AppInfo]) -> Table:
    """Make a new table."""
    table = Table(
        show_header=True,
        header_style='bold wheat4',
        border_style='grey69',
        style='black',
        box=box.MINIMAL_HEAVY_HEAD,
        expand=True,
    )

    _active, _dim = Color.env_color(env), 'white'
    env_style = f'{_dim} on {_active} bold'

    table.add_column(
        f'[{env_style}] {env.upper()} [/{env_style}] ' + 'app[dim]-alias[/dim]',
        width=50,
        style='grey84',
    )

    table.add_column('[grey]spec args', style='grey53')
    table.add_column('[grey]shards', width=5, justify='center')
    table.add_column('[deployed]deployed', width=18, justify='center')

    for app, opts in apps.items():
        table.add_row(
            fn_alias(app, opts),
            fn_exec_args(opts),
            fn_shards(opts),
            fn_deployed(opts),
        )

    return table


def k8s_apps_info(k8s: CoreV1Api, console: Console, env: str) -> None:
    """K8S apps info."""
    _apps: Dict[str, AppInfo] = k8s_apps(k8s=k8s, env=env)
    with Live(
        renderable=apps_table(env=env, apps=_apps),
        console=console,
        refresh_per_second=1,
    ) as live:
        try:
            while True:
                live.update(apps_table(env=env, apps=_apps))
                sleep(1)
                _apps = k8s_apps(k8s=k8s, env=env)
        except KeyboardInterrupt:
            pass


class Executor:
    """Base command executor class."""

    def __init__(self, env: str):
        """Init."""
        self.env: str = env
        self.term_envs = {'stage': TERM_STAGE, 'prod': TERM_PROD}
        self.console: Console = self._init_console()
        self.config: Dict = self._load_config()

    def __enter__(self):
        """On enter."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """On exit."""
        if exc_type is KeyboardInterrupt:
            return self._hang()
        return exc_type is None

    @property
    def app_dir(self) -> str:
        """Get app dir."""
        return Path(
            os.path.dirname(os.path.realpath(__file__)),
        ).parent.as_posix()

    @property
    def k8s_path(self) -> str:
        """Get k8s path."""
        try:
            _k8s_path = self.config[self.env]['k8s']
        except (AttributeError, ValueError, TypeError):
            self._error(Error.error(Error.K8_ENV_NOT_FOUND))
            sys.exit(1)
        if not Path(_k8s_path).exists():
            self._error(Error.error(Error.K8_ENV_NOT_FOUND))
        return _k8s_path

    @property
    def k8s_client(self) -> CoreV1Api:
        """Get k8s client."""
        try:
            load_kube_config(config_file=self.k8s_path)
        except ConfigException as _conf_err:
            self._error(Error.error(Error.K8_ENV_CONF_LOAD, [_conf_err]))
        return CoreV1Api()

    @property
    def pg_local(self) -> Dict:
        """PG local config."""
        try:
            return self.config['pg_local']
        except Exception as _err:
            self._error(Error.error(Error.DB_LOCAL_CFG_LOAD, [_err]))

    def _pg_remote(self, alias: str) ->  Dict[str, Dict]:
        """PG remote config."""
        try:
            return self.config[self.env]['pull'][alias]
        except Exception:
            self._error(Error.error(Error.DB_REMOTE_CFG_FOUND))
            sys.exit(1)

    def _init_console(self) -> Console:
        """Init console."""
        console = Console(stderr=True)
        envs = [_env for _env in self.term_envs.keys()]
        if self.env not in envs:
            self._error(Error.found(self.env, envs))
            sys.exit(1)

        theme = Theme(self.term_envs[self.env])
        console.use_theme(theme)
        return  console

    def _error(self, err_content):
        """Critical error."""
        self.console.print(err_content)
        sys.exit(1)

    def _hang(self):
        """Hang on."""
        self.console.print(Msg.hang())
        return True

    def _load_config(self) -> Dict:
        """Load dot config."""
        try:
            return YamlLoader(
                path=Path(self.app_dir).absolute() / 'config.yml',
                matcher=StrictMatcher,
                validator=PydanticValidator,
                schema=ConfigModel,
            ).load()
        except Exception as _cfg_err:
            self._error(Error.error(Error.CFG_NOT_LOADED, [_cfg_err]))
            sys.exit(1)

    # [ Postgres ] ------------------------------------------------------------

    def _pull(self, alias: str) -> None:
        """Pull database from remote to local."""
        _dba = dba(self.env, alias)
        _file = dba_file(self.app_dir, _dba)
        self._clean_temporary(_file)
        with self.console.status(**Status.pull_loader()) as status:
            self._create_and_drop_exist(_dba)
            self._dump(alias, _file, status)
            self._restore(alias, _dba, status)

    def _clean_temporary(self, real_dump_path: str) -> None:
        """Clean temporary."""
        if Path(real_dump_path).exists():
            os.remove(real_dump_path)

    def _pg_connection(self) -> psycopg.Connection:
        """Get local psycopg connection."""
        return psycopg.connect(
            dbname=self.pg_local.get('name'),
            user=self.pg_local.get('user'),
            password=self.pg_local.get('password'),
            host=self.pg_local.get('host'),
            autocommit=True,
        )

    def _create_and_drop_exist(self, real_name: str) -> None:
        """Create database and drop if exist."""
        with self._pg_connection() as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute("CREATE DATABASE %s;" % real_name)
                except psycopg.errors.DuplicateDatabase:
                    cursor.execute(
                        "DROP DATABASE %s WITH (FORCE);" % real_name)
                    cursor.execute("CREATE DATABASE %s;" % real_name)
                except Exception as _err:
                    self._error(Error.error(Error.DB_PREPARE_LOCAL, [_err]))

    def _dump(self, alias: str, real_path: str, ref) -> None:
        """Dump database."""
        _proc: Popen = Exec.process_dump(
            cfg=self._pg_remote(alias),
            path=real_path,
        )

        try:
            Exec.capture_dump(_proc, self.env, ref)
        except Exception as _err:
            self._error(Error.error(Error.DB_UNKNOWN, [_err]))
        finally:
            _proc.wait(3)

    def _restore(self, alias: str, real_alias: str, ref) -> None:
        """Restore database."""
        _proc: Popen = Exec.process_restore(
            cfg=self.pg_local,
            alias=real_alias,
            path=dba_file(self.app_dir, real_alias),
        )

        try:
            Exec.capture_restore(_proc, self.env, ref)
        finally:
            _proc.wait(3)

    # [ K8S ] -----------------------------------------------------------------

    def _show_apps(self) -> Dict[str, Dict]:
        """Show apps."""
        k8s_apps_info(k8s=self.k8s_client, console=self.console, env=self.env)

    def _check_app_name(self, name: str, available: List) -> None:
        """Check app name."""
        _available_names = [_app for _app in available]
        if name not in _available_names:
            self._error(Error.found(name, _available_names))

    def _show_app_config(self, name: str) -> None:
        """Show app config."""
        _apps: Dict[str, AppInfo] = k8s_apps(k8s=self.k8s_client, env=self.env)
        self._check_app_name(name, _apps.keys())

        _info: AppInfo = _apps[name]
        _proc = Exec.process_config(
            name=name,
            info=_info,
            env=self.env,
            k8s=self.k8s_path,
        )

        with _proc.stdout as stdin:
            buff = yaml.safe_load(
                ''.join([_bf.decode() for _bf in iter(stdin.readline, b'')]),
            )
            self.console.print(buff, style=Color.DEF.value)

    def _show_app_log(self, name: str) -> None:
        """Show app log."""
        _apps: Dict[str, AppInfo] = k8s_apps(k8s=self.k8s_client, env=self.env)
        self._check_app_name(name, _apps.keys())
        _info: AppInfo = _apps[name]
        _proc = Exec.process_log(name=name, env=self.env, k8s=self.k8s_path)

        try:
            with _proc.stdout:
                for _line in iter(_proc.stdout.readline, b''):
                    self.console.print(_line.decode())
        finally:
            exitcode = _proc.wait()
