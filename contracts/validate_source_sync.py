"""Compare source document JSON with development artifacts; no API calls."""
import argparse
import json
from pathlib import Path
import re


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root.parent / "docs" / "sources" / "04_API계약_스키마_예시JSON.md")
    args = parser.parse_args()
    document = args.source.read_text(encoding="utf-8")
    spec = json.loads((root / "openapi.json").read_text(encoding="utf-8"))
    index = json.loads((root / "example-index.json").read_text(encoding="utf-8"))
    blocks = re.findall(r"~~~json\s*\n(.*?)\n~~~", document, re.S)
    if not blocks or json.loads(blocks[0]).get("components", {}).get("schemas") != spec["components"]["schemas"]:
        raise ValueError("Source schemas differ from openapi.json")
    pairs = re.findall(r"### ([^\n]+\.json)\s*\n.*?~~~json\s*\n(.*?)\n~~~", document, re.S)
    names = ["examples/" + name for name, _ in pairs]
    if len(names) != len(set(names)) or set(names) != set(index):
        raise ValueError("Source example inventory differs from example-index.json")
    for name, body in pairs:
        if json.loads(body) != json.loads((root / "examples" / name).read_text(encoding="utf-8")):
            raise ValueError(f"Source example differs: {name}")
    print(f"PASS: source JSON matches {len(spec['components']['schemas'])} schemas and {len(pairs)} examples; prose and HTTP behavior not checked.")


if __name__ == "__main__":
    main()
