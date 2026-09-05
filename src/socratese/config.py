"""User config: read/write the TOML file listing indexed vaults.

Location: platformdirs.user_config_dir() (per decisions log).
Format: TOML, [[vaults]] table with name/path/last_indexed.
"""
from __future__ import annotations

import tomllib
from pathlib import Path
import platformdirs
import tomli_w


from socratese.vault.models import Vault

APP_NAME = 'socratese'
def get_config_path() -> Path:
    config_dir = Path(platformdirs.user_config_dir(APP_NAME))
    return config_dir / "config.toml"

def load_vaults() -> list[Vault]:
    config_path = get_config_path()
    if not config_path.exists():
        return []

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    return [Vault.from_toml_dict(entry) for entry in data.get("vaults", [])]

def save_vaults(vaults: list[Vault]) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"vaults": [v.to_toml_dict() for v in vaults]}

    with path.open("wb") as f:
        tomli_w.dump(data,f)