from __future__ import annotations

import json
from pathlib import Path


REGISTRY_FILENAME = "registered_env_ids.json"
REGISTRY_PATH = Path(__file__).resolve().parent / REGISTRY_FILENAME
ENV_NAME_KEY = "env_names"
LEGACY_ENV_ID_KEY = "env_ids"
ENV_ID_TEMPLATE = "UnrealTrack-{env_name}-ContinuousColor-v0"


class EnvRegistryError(ValueError):
    """Raised when the supported env registry file is invalid."""


def _require_gym():
    try:
        import gym
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The `gym` package is required to validate env_ids in route_graph_webui."
        ) from exc

    try:
        import gym_unrealcv  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The `gym_unrealcv` package must be importable before validating env_ids."
        ) from exc
    return gym


def build_env_id(env_name: str) -> str:
    return ENV_ID_TEMPLATE.format(env_name=env_name)


def extract_env_name(env_reference: str) -> str:
    if not isinstance(env_reference, str):
        raise ValueError("environment reference must be a string")

    env_reference = env_reference.strip()
    if not env_reference:
        raise ValueError("environment reference must not be empty")

    if "-" not in env_reference:
        return env_reference

    parts = env_reference.split("-")
    if len(parts) < 4 or not parts[0].startswith("Unreal"):
        raise ValueError(f"invalid environment reference: {env_reference}")

    env_name = parts[1].strip()
    if not env_name:
        raise ValueError(f"invalid environment reference: {env_reference}")
    return env_name


def load_registered_env_names(registry_path: str | Path | None = None) -> tuple[list[str], str]:
    path = Path(registry_path).resolve() if registry_path else REGISTRY_PATH

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise EnvRegistryError(f"Environment registry file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EnvRegistryError(f"Environment registry file is not valid JSON: {path}") from exc

    if not isinstance(data, dict):
        raise EnvRegistryError(f"Environment registry must be a JSON object: {path}")

    if ENV_NAME_KEY in data:
        raw_env_names = data.get(ENV_NAME_KEY)
    elif LEGACY_ENV_ID_KEY in data:
        raw_env_names = data.get(LEGACY_ENV_ID_KEY)
    else:
        raise EnvRegistryError(f"Environment registry must contain `{ENV_NAME_KEY}` in {path}")

    if not isinstance(raw_env_names, list):
        raise EnvRegistryError(f"`{ENV_NAME_KEY}` must be a JSON array in {path}")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_value in enumerate(raw_env_names):
        if not isinstance(raw_value, str):
            raise EnvRegistryError(f"`{ENV_NAME_KEY}[{index}]` must be a string in {path}")

        try:
            env_name = extract_env_name(raw_value)
        except ValueError as exc:
            raise EnvRegistryError(
                f"`{ENV_NAME_KEY}[{index}]` is invalid in {path}: {exc}"
            ) from exc

        if env_name in seen:
            raise EnvRegistryError(f"Duplicate env_name `{env_name}` found in {path}")

        seen.add(env_name)
        normalized.append(env_name)

    return normalized, str(path)


def normalize_env_reference(
    env_reference: str,
    supported_env_names: set[str] | list[str] | tuple[str, ...],
) -> tuple[str, str]:
    env_name = extract_env_name(env_reference)
    if env_name not in supported_env_names:
        raise ValueError(f"environment `{env_name}` is not listed in registered_env_ids.json")

    env_id = build_env_id(env_name)
    if not is_gym_env_registered(env_id):
        raise ValueError(f"env_id `{env_id}` is not registered in Gym")

    return env_name, env_id


def is_gym_env_registered(env_id: str) -> bool:
    gym = _require_gym()
    try:
        gym.spec(env_id)
        return True
    except Exception:
        return False


__all__ = [
    "ENV_ID_TEMPLATE",
    "ENV_NAME_KEY",
    "EnvRegistryError",
    "LEGACY_ENV_ID_KEY",
    "REGISTRY_FILENAME",
    "REGISTRY_PATH",
    "build_env_id",
    "extract_env_name",
    "is_gym_env_registered",
    "load_registered_env_names",
    "normalize_env_reference",
]
