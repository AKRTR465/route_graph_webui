from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import env_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EnvRegistryLocalTests(unittest.TestCase):
    def test_load_registered_env_names_uses_local_registry(self) -> None:
        names, path = env_registry.load_registered_env_names()

        self.assertIn("DowntownWest", names)
        self.assertEqual(PROJECT_ROOT / "registered_env_ids.json", Path(path))

    def test_extract_env_name_supports_plain_name_and_env_id(self) -> None:
        self.assertEqual("DowntownWest", env_registry.extract_env_name("DowntownWest"))
        self.assertEqual(
            "DowntownWest",
            env_registry.extract_env_name("UnrealTrack-DowntownWest-ContinuousColor-v0"),
        )

    def test_build_env_id_matches_existing_template(self) -> None:
        self.assertEqual(
            "UnrealTrack-DowntownWest-ContinuousColor-v0",
            env_registry.build_env_id("DowntownWest"),
        )

    def test_normalize_env_reference_returns_env_name_and_env_id(self) -> None:
        with mock.patch.object(env_registry, "is_gym_env_registered", return_value=True):
            env_name, env_id = env_registry.normalize_env_reference(
                "DowntownWest",
                {"DowntownWest"},
            )

        self.assertEqual("DowntownWest", env_name)
        self.assertEqual("UnrealTrack-DowntownWest-ContinuousColor-v0", env_id)

    def test_normalize_env_reference_rejects_unsupported_env(self) -> None:
        with self.assertRaisesRegex(ValueError, "not listed"):
            env_registry.normalize_env_reference("DowntownWest", {"OtherEnv"})

    def test_normalize_env_reference_rejects_unregistered_gym_env(self) -> None:
        with mock.patch.object(env_registry, "is_gym_env_registered", return_value=False):
            with self.assertRaisesRegex(ValueError, "not registered in Gym"):
                env_registry.normalize_env_reference("DowntownWest", {"DowntownWest"})
