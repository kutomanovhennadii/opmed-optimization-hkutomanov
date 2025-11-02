from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from opmed.errors import DataError
from opmed.metrics.logger import (
    _atomic_write_text,
    _utc_now_hms,
    write_metrics,
    write_solver_log,
)

# --------------------------
# write_metrics
# --------------------------


def test_write_metrics_writes_json_and_overwrites(tmp_path):
    out_dir = tmp_path / "out"
    p1 = write_metrics({"a": 1, "b": "x"}, out_dir)
    assert p1.name == "metrics.json"
    text1 = p1.read_text(encoding="utf-8")
    obj1 = json.loads(text1)
    assert obj1 == {"a": 1, "b": "x"}

    # перезапись
    p2 = write_metrics({"a": 2, "c": True}, out_dir)
    assert p2 == p1
    text2 = p2.read_text(encoding="utf-8")
    obj2 = json.loads(text2)
    assert obj2 == {"a": 2, "c": True}


def test_write_metrics_rejects_non_dict(tmp_path):
    with pytest.raises(DataError) as ei:
        write_metrics(["not", "a", "dict"], tmp_path)
    assert "metrics must be a dict" in str(ei.value)


def test_write_metrics_non_serializable_raises(tmp_path):
    class Bad:
        pass

    with pytest.raises(DataError) as ei:
        write_metrics({"ok": 1, "bad": Bad()}, tmp_path)
    msg = str(ei.value)
    assert "metrics not JSON-serializable" in msg
    assert "metrics.write_metrics" in msg


# --------------------------
# _atomic_write_text
# --------------------------


def test_atomic_write_text_failure_raises_and_cleans_tmp(tmp_path, monkeypatch):
    """
    Форсируем ошибку os.replace, проверяем DataError и удаление временного файла.
    """
    target = tmp_path / "folder" / "file.txt"
    tmp_created = tmp_path / "folder" / "file.txt.tmp-for-test"

    # Подменяем mkstemp, чтобы контролировать имя tmp-файла
    def fake_mkstemp(prefix, dir):
        # создаём пустой tmp-файл заранее
        os.makedirs(dir, exist_ok=True)
        f = open(tmp_created, "w", encoding="utf-8")
        f.close()
        # возвращаем валидный файловый дескриптор на запись в тот же файл
        fd = os.open(tmp_created, os.O_RDWR)
        return fd, str(tmp_created)

    monkeypatch.setattr("tempfile.mkstemp", fake_mkstemp)

    # Подменяем os.replace, чтобы он падал
    def boom_replace(src, dst):
        raise OSError("nope")

    monkeypatch.setattr(os, "replace", boom_replace)

    with pytest.raises(DataError) as ei:
        _atomic_write_text(target, "payload", encoding="utf-8")

    msg = str(ei.value)
    assert "atomic write failed" in msg
    assert "metrics._atomic_write_text" in msg

    # tmp-файл должен быть удалён
    assert not tmp_created.exists()


# --------------------------
# write_solver_log
# --------------------------


def test_write_solver_log_full_info(tmp_path, monkeypatch):
    """
    Полный сценарий: есть cfg.solver с параметрами, версия OR-Tools,
    и solver.ResponseStats() возвращает текст.
    """
    # фиксируем время
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-01-01 12:34:56")

    # фиктивная версия ortools
    import opmed.metrics.logger as logger_mod

    monkeypatch.setattr(logger_mod.ortools, "__version__", "9.99.fake", raising=False)

    # cfg.solver с полями
    cfg = SimpleNamespace(
        solver=SimpleNamespace(
            num_workers=4,
            max_time_in_seconds=12.5,
            random_seed=777,
            search_branching="AUTOMATIC",
        )
    )

    # solver c ResponseStats
    class Solver:
        def ResponseStats(self):
            # многословный многострочный текст
            return "CpSolverStatus: OPTIMAL\nObjective: 42\nWall time: 0.12s"

    path = write_solver_log(Solver(), cfg, tmp_path / "logs")
    text = path.read_text(encoding="utf-8")

    # начальные строки
    assert "[2025-01-01 12:34:56] INFO Starting CP-SAT solver" in text
    assert "Parameters: workers=4, time_limit=12.5s, seed=777, search_branching=AUTOMATIC" in text
    assert "OR-Tools version: 9.99.fake" in text

    # snippet и полный текст статистики
    assert "ResponseStats snippet: CpSolverStatus: OPTIMAL" in text
    assert "CpSolverStatus: OPTIMAL" in text
    assert "Objective: 42" in text
    assert "Wall time: 0.12s" in text

    # заканчивается переводом строки
    assert text.endswith("\n")


def test_write_solver_log_no_responsestats(tmp_path, monkeypatch):
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-02-02 00:00:00")
    cfg = SimpleNamespace(solver=SimpleNamespace(num_workers=1))

    class Solver:
        pass

    path = write_solver_log(Solver(), cfg, tmp_path / "logs2")
    text = path.read_text(encoding="utf-8")
    assert "Solver finished (no ResponseStats available)" in text


def test_write_solver_log_responsestats_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-03-03 03:03:03")
    cfg = SimpleNamespace(solver=SimpleNamespace(num_workers=2))

    class Solver:
        def ResponseStats(self):
            raise RuntimeError("boom")

    path = write_solver_log(Solver(), cfg, tmp_path / "logs3")
    text = path.read_text(encoding="utf-8")
    assert "WARN Failed to read ResponseStats()" in text


def test_write_solver_log_params_block_robust(tmp_path, monkeypatch):
    """
    Если доступ к cfg.solver кидает исключение — лог всё равно пишется.
    """
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-04-04 04:04:04")

    class BadCfg:
        @property
        def solver(self):
            raise RuntimeError("no cfg.solver")

    class Solver:
        def ResponseStats(self):
            return "CpSolverStatus: FEASIBLE\nObjective: 1"

    path = write_solver_log(Solver(), BadCfg(), tmp_path / "logs4")
    text = path.read_text(encoding="utf-8")
    assert "Starting CP-SAT solver" in text
    # строки параметров может не быть (мы проглатываем исключение) — важно, что лог создан
    assert "Parameters:" not in text
    assert "CpSolverStatus: FEASIBLE" in text


def test_write_solver_log_version_block_robust(tmp_path, monkeypatch):
    """
    Если доступ к ortools.__version__ падает — лог пишется без версии.
    """
    monkeypatch.setattr("opmed.metrics.logger._utc_now_hms", lambda: "2025-05-05 05:05:05")
    import opmed.metrics.logger as logger_mod

    class BadOrtools:
        def __getattr__(self, name):
            raise RuntimeError("no version")

    monkeypatch.setattr(logger_mod, "ortools", BadOrtools())

    cfg = SimpleNamespace(solver=SimpleNamespace(num_workers=1))

    class Solver:
        pass

    path = write_solver_log(Solver(), cfg, tmp_path / "logs5")
    text = path.read_text(encoding="utf-8")
    assert "OR-Tools version:" not in text
    assert "Starting CP-SAT solver" in text


# --------------------------
# _utc_now_hms
# --------------------------


def test_utc_now_hms_format():
    s = _utc_now_hms()
    # Формат YYYY-MM-DD HH:MM:SS (19 символов)
    assert isinstance(s, str)
    assert len(s) == 19
    assert s[4] == "-" and s[7] == "-" and s[10] == " " and s[13] == ":" and s[16] == ":"
