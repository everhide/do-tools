from fire import Fire

from dot import Cmd


class Interface:
    """DOT Commands tool for PortalBilet on Digital Ocean."""

    def show(self, env: str = 'stage'):
        """Show summary info."""
        with Cmd(env=env) as cmd:
            cmd.show_info()

    def pull(self, db: str, env: str = 'stage'):
        """Pull from remote db to local."""
        with Cmd(env=env) as cmd:
            cmd.check_db_alias(alias=db)
            cmd.pull(alias=db)

    def log(self, app, env: str = 'stage'):
        """Log from app container."""
        with Cmd(env=env) as cmd:
            cmd.tail_log(app=app)

    def config(self, app, env: str = 'stage'):
        """Config from app container."""
        with Cmd(env=env) as cmd:
            cmd.show_config(app=app)


if __name__ == '__main__':
    Fire(Interface)
