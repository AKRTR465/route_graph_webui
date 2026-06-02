from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping


if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bootstrap_paths import inject_project_root as _inject_project_root
    from bootstrap_paths import resolve_project_path as _resolve_project_path
    from env_registry import (
        EnvRegistryError,
        build_env_id,
        extract_env_name,
        load_registered_env_names,
        normalize_env_reference,
    )
    from webui_common import (
        DATA_DIR,
        LEGACY_ROUTE_GARPH_DIR_ENV,
        LEGACY_ROUTE_GARPH_DIR_NAME,
        LEGACY_SPELLING_RETIREMENT_DATE,
        ROUTE_GRAPH_WEBUI_DIR,
        ensure_data_directories,
        resolve_data_path,
        resolve_route_path,
    )
else:
    from .bootstrap_paths import inject_project_root as _inject_project_root
    from .bootstrap_paths import resolve_project_path as _resolve_project_path
    from .env_registry import (
        EnvRegistryError,
        build_env_id,
        extract_env_name,
        load_registered_env_names,
        normalize_env_reference,
    )
    from .webui_common import (
        DATA_DIR,
        LEGACY_ROUTE_GARPH_DIR_ENV,
        LEGACY_ROUTE_GARPH_DIR_NAME,
        LEGACY_SPELLING_RETIREMENT_DATE,
        ROUTE_GRAPH_WEBUI_DIR,
        ensure_data_directories,
        resolve_data_path,
        resolve_route_path,
    )


PROJECT_ROOT = _inject_project_root(__file__)
# Legacy runtime alias retained until LEGACY_SPELLING_RETIREMENT_DATE.
ROUTE_GARPH_DIR = ROUTE_GRAPH_WEBUI_DIR
DEFAULT_RESET_LOCATION = (150.0, -100.0, 200.0)
DEFAULT_RESET_ROTATION = (0.0, 90.0, 0.0)
DEFAULT_MOVE_SPEED = 0.3
DEFAULT_YAW_SPEED = 1.0
DEFAULT_STATUS_INTERVAL = 0.4


@dataclass(frozen=True, slots=True)
class SceneFlags:
    env_name: str
    env_id: str
    ue4: bool
    use_cam_0: bool
    camera_id: int


@dataclass(slots=True)
class RuntimeArgs:
    seed: int = 0
    time_dilation: int = 10
    early_done: int = -1
    monitor: bool = False
    enable_physics: bool = True
    reset_location: tuple[float, float, float] = DEFAULT_RESET_LOCATION
    reset_rotation: tuple[float, float, float] = DEFAULT_RESET_ROTATION

    @classmethod
    def from_source(cls, source: Any | None = None) -> "RuntimeArgs":
        if source is None:
            return cls()
        if isinstance(source, cls):
            return source

        def _get(name: str, default: Any) -> Any:
            if isinstance(source, Mapping):
                return source.get(name, default)
            return getattr(source, name, default)

        return cls(
            seed=int(_get("seed", 0)),
            time_dilation=int(_get("time_dilation", 10)),
            early_done=int(_get("early_done", -1)),
            monitor=bool(_get("monitor", False)),
            enable_physics=bool(_get("enable_physics", True)),
            reset_location=tuple(float(v) for v in _get("reset_location", DEFAULT_RESET_LOCATION)),
            reset_rotation=tuple(float(v) for v in _get("reset_rotation", DEFAULT_RESET_ROTATION)),
        )


@dataclass(slots=True)
class RouteGraphRuntime:
    env: Any
    scene_flags: SceneFlags
    drone_id: Any


def resolve_project_path(path_value: str | Path | None) -> Path | None:
    resolved = _resolve_project_path(path_value)
    return Path(resolved) if resolved else None


def load_supported_env_names(registry_path: str | Path | None = None) -> tuple[set[str], str]:
    names, path = load_registered_env_names(registry_path)
    return set(names), path


def normalize_supported_env(
    env_reference: str,
    supported_env_names: Iterable[str] | None = None,
) -> tuple[str, str]:
    if supported_env_names is None:
        supported_env_names, _ = load_supported_env_names()
    return normalize_env_reference(env_reference, set(supported_env_names))


def _require_env_config():
    import env_config

    return env_config


def _require_gym_modules():
    import gym
    from gym_unrealcv.envs.wrappers import augmentation, configUE, early_done, monitor, time_dilation

    return SimpleNamespace(
        gym=gym,
        augmentation=augmentation,
        configUE=configUE,
        early_done=early_done,
        monitor=monitor,
        time_dilation=time_dilation,
    )


def configure_scene_flags(env_reference: str) -> SceneFlags:
    env_config = _require_env_config()
    env_name = extract_env_name(env_reference)
    env_id = env_reference if "-" in env_reference else build_env_id(env_name)
    use_cam_0 = False

    if env_name in env_config.UE4_Sence:
        ue4 = True
        if env_name == "DowntownWest":
            use_cam_0 = True
    elif env_name in env_config.UE5_Sence:
        ue4 = False
    else:
        raise ValueError(f"Invalid environment map: {env_name}")

    if use_cam_0:
        camera_id = 0
    elif ue4:
        camera_id = 1
    else:
        camera_id = 2

    return SceneFlags(
        env_name=env_name,
        env_id=env_id,
        ue4=ue4,
        use_cam_0=use_cam_0,
        camera_id=camera_id,
    )


def build_route_graph_env(
    env_reference: str,
    args: RuntimeArgs | Mapping[str, Any] | Any | None = None,
    supported_env_names: Iterable[str] | None = None,
) -> RouteGraphRuntime:
    runtime_args = RuntimeArgs.from_source(args)
    modules = _require_gym_modules()
    _, validated_env_id = normalize_supported_env(env_reference, supported_env_names)
    scene_flags = configure_scene_flags(validated_env_id)

    env = None
    try:
        env = modules.gym.make(validated_env_id)
        if runtime_args.time_dilation > 0:
            env = modules.time_dilation.TimeDilationWrapper(env, runtime_args.time_dilation)
        if runtime_args.early_done > 0:
            env = modules.early_done.EarlyDoneWrapper(env, runtime_args.early_done)
        if runtime_args.monitor:
            env = modules.monitor.DisplayWrapper(env)

        env.unwrapped.agents_category = ["drone"]
        env = modules.configUE.ConfigUEWrapper(env, resolution=(640, 480))
        env = modules.augmentation.RandomPopulationWrapper(env, 2, 2, random_target=False)

        if hasattr(env, "seed"):
            env.seed(int(runtime_args.seed))

        env.reset()
        drone_id = env.unwrapped.player_list[0]
        env.unwrapped.unrealcv.set_viewport(drone_id)
        env.unwrapped.unrealcv.set_phy(drone_id, 1 if runtime_args.enable_physics else 0)

        runtime = RouteGraphRuntime(env=env, scene_flags=scene_flags, drone_id=drone_id)
        set_default_pose(
            runtime,
            location=runtime_args.reset_location,
            rotation=runtime_args.reset_rotation,
            enable_physics=runtime_args.enable_physics,
        )
        return runtime
    except Exception:
        close_env(env)
        raise


def close_env(runtime_or_env: RouteGraphRuntime | Any | None) -> None:
    env = runtime_or_env.env if isinstance(runtime_or_env, RouteGraphRuntime) else runtime_or_env
    if env is None:
        return
    try:
        env.close()
    except Exception as exc:
        print(f">>> Warning: failed to close environment cleanly: {exc}")


def set_default_pose(
    runtime: RouteGraphRuntime,
    location: Iterable[float] = DEFAULT_RESET_LOCATION,
    rotation: Iterable[float] = DEFAULT_RESET_ROTATION,
    enable_physics: bool | None = None,
) -> None:
    env = runtime.env
    location_list = [float(v) for v in location]
    rotation_list = [float(v) for v in rotation]
    if enable_physics is not None:
        env.unwrapped.unrealcv.set_phy(runtime.drone_id, 1 if enable_physics else 0)
    env.unwrapped.unrealcv.set_obj_location(runtime.drone_id, location_list)
    env.unwrapped.unrealcv.set_obj_rotation(runtime.drone_id, rotation_list)


def get_current_pose(runtime: RouteGraphRuntime) -> tuple[list[float], list[float]]:
    location = runtime.env.unwrapped.unrealcv.get_obj_location(runtime.drone_id)
    rotation = runtime.env.unwrapped.unrealcv.get_obj_rotation(runtime.drone_id)
    return [float(v) for v in location], [float(v) for v in rotation]


def format_pose(runtime: RouteGraphRuntime) -> str:
    location, rotation = get_current_pose(runtime)
    return (
        f"xyz=({location[0]:.3f}, {location[1]:.3f}, {location[2]:.3f}) "
        f"rpy=({rotation[0]:.3f}, {rotation[1]:.3f}, {rotation[2]:.3f})"
    )


def make_dual_agent_action(action: Iterable[float]) -> list[list[float]]:
    primary = [float(v) for v in action]
    return [primary, [0.0, 0.0, 0.0, 0.0]]


def step_runtime(runtime: RouteGraphRuntime, action: Iterable[float] | None = None) -> Any:
    if action is None:
        action = [0.0, 0.0, 0.0, 0.0]
    return runtime.env.step(make_dual_agent_action(action))


class KeyboardController:
    """Stateful keyboard tracker with flight-action helpers."""

    DEFAULT_KEYS = (
        "t",
        "g",
        "f",
        "h",
        "i",
        "k",
        "j",
        "l",
        "o",
        "q",
        "s",
        "p",
        "[",
    )

    def __init__(
        self,
        tracked_keys: Iterable[str] | None = None,
        move_speed: float = DEFAULT_MOVE_SPEED,
        yaw_speed: float = DEFAULT_YAW_SPEED,
    ) -> None:
        self.move_speed = float(move_speed)
        self.yaw_speed = float(yaw_speed)
        keys = set(self.DEFAULT_KEYS)
        if tracked_keys:
            keys.update(str(key).lower() for key in tracked_keys)
        self.state = {key: False for key in keys}
        self._listener = None

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ModuleNotFoundError as exc:
            raise RuntimeError("The `pynput` package is required for keyboard input.") from exc

        def on_press(key: Any) -> None:
            key_name = self._normalize_key(key)
            if key_name in self.state:
                self.state[key_name] = True

        def on_release(key: Any) -> None:
            key_name = self._normalize_key(key)
            if key_name in self.state:
                self.state[key_name] = False

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is None:
            return
        try:
            self._listener.stop()
        except Exception:
            pass
        self._listener = None

    def _normalize_key(self, key: Any) -> str | None:
        try:
            if key.char:
                return str(key.char).lower()
        except AttributeError:
            return None
        return None

    def is_pressed(self, key_name: str) -> bool:
        return bool(self.state.get(key_name.lower(), False))

    def consume(self, key_name: str) -> bool:
        normalized = key_name.lower()
        current = bool(self.state.get(normalized, False))
        self.state[normalized] = False
        return current

    def flight_action(self) -> list[float]:
        action = [0.0, 0.0, 0.0, 0.0]
        if self.is_pressed("t"):
            action[0] += self.move_speed
        if self.is_pressed("g"):
            action[0] -= self.move_speed
        if self.is_pressed("f"):
            action[1] -= self.move_speed * 1.3
        if self.is_pressed("h"):
            action[1] += self.move_speed * 1.3
        if self.is_pressed("i"):
            action[2] += self.move_speed
        if self.is_pressed("k"):
            action[2] -= self.move_speed
        if self.is_pressed("j"):
            action[3] -= self.yaw_speed
        if self.is_pressed("l"):
            action[3] += self.yaw_speed
        return action


def timestamp_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


inject_project_root = _inject_project_root


__all__ = [
    "DATA_DIR",
    "DEFAULT_RESET_LOCATION",
    "DEFAULT_RESET_ROTATION",
    "DEFAULT_STATUS_INTERVAL",
    "EnvRegistryError",
    "KeyboardController",
    "LEGACY_ROUTE_GARPH_DIR_ENV",
    "LEGACY_ROUTE_GARPH_DIR_NAME",
    "LEGACY_SPELLING_RETIREMENT_DATE",
    "PROJECT_ROOT",
    "ROUTE_GARPH_DIR",
    "RouteGraphRuntime",
    "RuntimeArgs",
    "SceneFlags",
    "build_route_graph_env",
    "close_env",
    "configure_scene_flags",
    "ensure_data_directories",
    "extract_env_name",
    "format_pose",
    "get_current_pose",
    "inject_project_root",
    "load_registered_env_names",
    "load_supported_env_names",
    "make_dual_agent_action",
    "normalize_env_reference",
    "normalize_supported_env",
    "resolve_data_path",
    "resolve_project_path",
    "resolve_route_path",
    "set_default_pose",
    "step_runtime",
    "timestamp_now",
]
