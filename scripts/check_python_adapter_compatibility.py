from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SDK_SOURCE = ROOT / "packages" / "python-sdk" / "src"
MANIFEST = ROOT / "packages" / "python-sdk" / "compatibility" / "upstream.json"
STARTER = ROOT / "examples" / "oss-trading-adapters"
VALID_LEVELS = {"continuous_upstream", "contract_fixture", "source_contract"}
REQUIRED_NATIVE_STARTERS = {
    "hummingbot": STARTER / "hummingbot_example.py",
    "openbb": STARTER / "openbb_provider" / "openbb_norynta" / "provider.py",
    "lumibot": STARTER / "lumibot_example.py",
    "nautilustrader": STARTER / "nautilustrader_example.py",
    "vnpy": STARTER / "vnpy_example.py",
    "lean": STARTER / "lean" / "NoryntaQuote.py",
}

sys.path.insert(0, str(SDK_SOURCE))

from norynta import FRAMEWORK_ADAPTERS  # noqa: E402


def main() -> int:
    payload: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frameworks = payload.get("frameworks")
    errors: list[str] = []
    if not isinstance(frameworks, dict):
        errors.append("manifest.frameworks must be an object")
        frameworks = {}

    local = set(FRAMEWORK_ADAPTERS)
    recorded = set(frameworks)
    if missing := sorted(local - recorded):
        errors.append(f"manifest is missing adapters: {', '.join(missing)}")
    if extra := sorted(recorded - local):
        errors.append(f"manifest has unknown adapters: {', '.join(extra)}")

    continuous = 0
    for name, raw in frameworks.items():
        if not isinstance(raw, dict):
            errors.append(f"{name} metadata must be an object")
            continue
        repository = str(raw.get("officialRepository") or "")
        if not repository.startswith("https://github.com/"):
            errors.append(f"{name} must identify its official GitHub repository")
        verification = raw.get("verification")
        if verification not in VALID_LEVELS:
            errors.append(f"{name} has unsupported verification level: {verification}")
        if verification == "continuous_upstream":
            continuous += 1
            if not str(raw.get("package") or "").strip():
                errors.append(f"{name} continuous check requires package")
            if raw.get("extra") != name:
                errors.append(f"{name} continuous check requires matching SDK extra")
            if not str(raw.get("minimumVersion") or "").strip():
                errors.append(f"{name} continuous check requires minimumVersion")
        elif not str(raw.get("note") or "").strip():
            errors.append(f"{name} non-continuous verification requires an honest note")

    if continuous < 3:
        errors.append("at least three lightweight adapters must run continuous upstream checks")
    if not STARTER.is_dir():
        errors.append("cloneable OSS adapter starter directory is missing")
    for name, path in REQUIRED_NATIVE_STARTERS.items():
        if not path.is_file():
            errors.append(f"{name} native starter is missing: {path.relative_to(ROOT)}")

    result = {
        "ok": not errors,
        "adapterCount": len(local),
        "continuousUpstreamCount": continuous,
        "nativeStarterCount": sum(path.is_file() for path in REQUIRED_NATIVE_STARTERS.values()),
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
