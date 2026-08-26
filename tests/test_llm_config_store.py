"""Applying + persisting LLM config, including the API key (Vision §32, §40).

The key is write-only from the surface: staged into the process env and upserted into
.env, without clobbering unrelated lines. No network, no leakage.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.infrastructure import llm_config_store


class TestStage:
    def test_it_sets_only_non_empty_values(self) -> None:
        env: dict[str, str] = {}
        updates = llm_config_store.stage("groq", "llama-3.3-70b", None, "gsk_secret", environ=env)
        assert env["JARVIS_LLM_PROVIDER"] == "groq"
        assert env["JARVIS_LLM_MODEL"] == "llama-3.3-70b"
        assert env["JARVIS_LLM_API_KEY"] == "gsk_secret"
        assert "JARVIS_LLM_BASE_URL" not in env  # empty base_url left untouched
        assert updates["JARVIS_LLM_API_KEY"] == "gsk_secret"


class TestPersist:
    def test_it_creates_the_env_file_with_the_key(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        updates = {"JARVIS_LLM_PROVIDER": "groq", "JARVIS_LLM_API_KEY": "gsk_secret"}
        written = llm_config_store.persist(updates, env_path=path)
        assert written == path
        text = path.read_text(encoding="utf-8")
        assert "JARVIS_LLM_PROVIDER=groq" in text
        assert "JARVIS_LLM_API_KEY=gsk_secret" in text

    def test_it_updates_in_place_and_keeps_other_lines(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text(
            "# my env\nOTHER=keep-me\nJARVIS_LLM_API_KEY=old\n", encoding="utf-8"
        )
        llm_config_store.persist({"JARVIS_LLM_API_KEY": "new"}, env_path=path)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert "# my env" in lines
        assert "OTHER=keep-me" in lines
        assert "JARVIS_LLM_API_KEY=new" in lines
        assert "JARVIS_LLM_API_KEY=old" not in lines
        # the key appears exactly once — updated in place, not duplicated
        assert sum(1 for line in lines if line.startswith("JARVIS_LLM_API_KEY=")) == 1

    def test_the_env_file_path_can_come_from_the_environment(self, tmp_path: Path) -> None:
        path = tmp_path / "secrets.env"
        written = llm_config_store.persist(
            {"JARVIS_LLM_API_KEY": "k"},
            environ={"JARVIS_ENV_FILE": str(path)},
        )
        assert written == path
        assert path.exists()


class TestLoadEnvFile:
    def test_it_loads_saved_values_into_the_environment(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text(
            "# saved by the panel\nJARVIS_LLM_PROVIDER=groq\nJARVIS_LLM_MODEL=llama-3.3-70b\n"
            "JARVIS_LLM_API_KEY=gsk_secret\n",
            encoding="utf-8",
        )
        env: dict[str, str] = {}
        llm_config_store.load_env_file(env_path=path, environ=env)
        assert env["JARVIS_LLM_PROVIDER"] == "groq"
        assert env["JARVIS_LLM_MODEL"] == "llama-3.3-70b"
        assert env["JARVIS_LLM_API_KEY"] == "gsk_secret"

    def test_a_real_environment_variable_wins_over_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("JARVIS_LLM_PROVIDER=groq\n", encoding="utf-8")
        env = {"JARVIS_LLM_PROVIDER": "ollama"}
        llm_config_store.load_env_file(env_path=path, environ=env)
        assert env["JARVIS_LLM_PROVIDER"] == "ollama"  # explicit env is not overridden

    def test_a_missing_file_is_a_no_op(self, tmp_path: Path) -> None:
        env: dict[str, str] = {}
        llm_config_store.load_env_file(env_path=tmp_path / "nope.env", environ=env)
        assert env == {}
