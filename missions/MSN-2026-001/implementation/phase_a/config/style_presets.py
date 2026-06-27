from pathlib import Path

import yaml


def load_presets() -> dict:
    path = Path(__file__).parent / "style_presets.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("styles", {})
