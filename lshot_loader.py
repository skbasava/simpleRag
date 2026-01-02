import yaml
from pathlib import Path

def load_kshot_examples(
    path: str | Path,
    max_examples: int | None = None,
) -> list[dict]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    shots = data.get("kshots", [])
    if max_examples is not None:
        shots = shots[:max_examples]
    return shots