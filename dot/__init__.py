from dot.helpers import *


class Cmd(Executor):
    """Cmd class."""

    def check_db_alias(self, alias: str) -> None:
        """Check alias."""
        try:
            env_pulls = self.config.pull[Env(self.env)].keys()
        except Exception as _alias_err:
            self._error(Error.error(Error.ENV_INVALID, [Env]))
            sys.exit(1)

        if alias not in env_pulls:
            self._error(Error.found(alias, [_pull for _pull in env_pulls]))
            sys.exit(1)

    def pull(self, alias: str) -> None:
        """Pull remote database to local postgres."""
        try:
            self._pull(alias=alias)
        except PG_ERRORS as _pg_error:
            self._error(Error.error(Error.DB_PG, [_pg_error]))
        except (DotError, Exception) as _error:
            self._error(Error.error(Error.DB_UNKNOWN, [_error]))
        finally:
            self._clean_temporary(alias)

    def tail_log(self, app: str, hours=24) -> None:
        """Tail app log."""
        self._show_app_log(name=app)

    def show_config(self, app: str) -> None:
        """Show app config as dict."""
        self._show_app_config(name=app)

    def show_info(self) -> None:
        """Show summary info."""
        self._show_apps()
