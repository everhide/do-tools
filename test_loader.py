from piny import PydanticValidator, StrictMatcher, YamlLoader

from dot import ConfigModel


def load_config() -> None:
    return YamlLoader(
        path='config.yml',
        matcher=StrictMatcher,
        validator=PydanticValidator,
        schema=ConfigModel,
    ).load()



config = load_config()
print(config)
