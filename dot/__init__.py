from dot.helpers import *


class Cmd(Executor):
    """Cmd class."""

    def check_db_alias(self, alias: str) -> None:
        """Check alias."""
        try:
            pull: Dict = self.config[self.env]['pull']
        except (AttributeError, KeyError, TypeError, NameError):
            self._error(Error.error(Error.DB_PULL_EMPTY))
            sys.exit(1)

        available = [_db for _db in pull.keys()]
        if alias not in available:
            self._error(Error.found(alias, available))
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

        _text = Msg.pull_info(self.env, alias, f'local/{dba(self.env, alias)}')
        self.console.print(Msg.info(_text, self.env))

    def tail_log(self, app: str, hours=24) -> None:
        """Tail app log."""
        self._show_app_log(name=app)

    def show_config(self, app: str) -> None:
        """Show app config as dict."""
        self._show_app_config(name=app)

    def show_info(self) -> None:
        """Show summary info."""
        self._show_apps()
