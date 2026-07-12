"""Parallel markdown parsing and hashing utilities for distill-vault."""
from __future__ import annotations

import hashlib
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, TimeoutError, as_completed
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import frontmatter

from .vault_semantics import extract_frontmatter_links, extract_wikilinks


class WorkerPool:
    """Worker pool for markdown parsing and hashing.

    Safety-first defaults:
    - ``auto`` prefers threads over forked processes to avoid intermittent
      multiprocessing crashes during routine CLI runs and tests.
    - explicit ``process`` mode can fall back to ``thread`` (or another chosen
      mode) if executor startup/execution fails.
    """

    VALID_MODES = {"auto", "process", "thread", "serial"}

    def __init__(
        self,
        workers: Optional[int] = None,
        timeout: float = 5.0,
        mode: str = "auto",
        fallback_mode: Optional[str] = "thread",
    ):
        cpu_count = os.cpu_count() or 1
        default_workers = min(cpu_count, 4)
        self.workers = max(1, workers or default_workers)
        self.timeout = timeout
        self.mode = (mode or "auto").strip()
        self.fallback_mode = fallback_mode.strip() if isinstance(fallback_mode, str) else fallback_mode
        self.failures: List[Dict[str, str]] = []
        self.last_mode: Optional[str] = None
        self.fallback_used = False
        self.fallback_reason: Optional[str] = None
        self._validate_modes()

    def parse_files(
        self,
        file_paths: Iterable[Path | str],
        vault_root: Path | str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[dict]:
        """Parse markdown files with the configured execution mode."""
        self._reset_operation_state()
        root = Path(vault_root)
        normalized = [Path(p) for p in file_paths]
        if not normalized:
            return []

        raw_results = self._run_operation(
            normalized,
            root,
            worker_fn=_parse_single_file,
            progress_callback=progress_callback,
        )

        objects: List[dict] = []
        for path, result in raw_results:
            rel_path = _safe_relative(path, root)
            if result.get("ok"):
                objects.append(result["object"])
            else:
                self.failures.append(
                    {
                        "path": rel_path,
                        "error": str(result.get("error", "unknown error")),
                    }
                )
        return objects

    def hash_files(
        self,
        file_paths: Iterable[Path | str],
        vault_root: Path | str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, str]:
        """Compute MD5 hashes using the configured execution mode."""
        self._reset_operation_state()
        root = Path(vault_root)
        normalized = [Path(p) for p in file_paths]
        if not normalized:
            return {}

        raw_results = self._run_operation(
            normalized,
            root,
            worker_fn=_hash_single_file,
            progress_callback=progress_callback,
        )

        hashes: Dict[str, str] = {}
        for path, result in raw_results:
            rel_path = _safe_relative(path, root)
            if result.get("ok"):
                hashes[str(result["path"])] = str(result["hash"])
            else:
                self.failures.append(
                    {
                        "path": rel_path,
                        "error": str(result.get("error", "unknown error")),
                    }
                )
        return hashes

    def _validate_modes(self):
        if self.mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported worker mode: {self.mode}")
        if self.fallback_mode is not None and self.fallback_mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported fallback worker mode: {self.fallback_mode}")

    def _reset_operation_state(self):
        self.failures = []
        self.last_mode = None
        self.fallback_used = False
        self.fallback_reason = None

    def _resolve_mode(self, mode: Optional[str] = None) -> str:
        resolved = mode or self.mode
        if resolved == "auto":
            return "serial" if self.workers <= 1 else "thread"
        return resolved

    def _resolve_fallback_mode(self, primary_mode: str) -> Optional[str]:
        if self.fallback_mode is None:
            return None
        fallback = self._resolve_mode(self.fallback_mode)
        if fallback == primary_mode:
            return None
        return fallback

    def _run_operation(
        self,
        normalized: List[Path],
        root: Path,
        worker_fn: Callable[[str, str], Dict[str, object]],
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> List[tuple[Path, Dict[str, object]]]:
        primary_mode = self._resolve_mode()
        try:
            results = self._execute_mode(primary_mode, normalized, root, worker_fn, progress_callback)
            self.last_mode = primary_mode
            return results
        except Exception as exc:
            fallback_mode = self._resolve_fallback_mode(primary_mode)
            if fallback_mode is None:
                raise
            self.failures = []
            self.fallback_used = True
            self.fallback_reason = str(exc)
            results = self._execute_mode(fallback_mode, normalized, root, worker_fn, progress_callback)
            self.last_mode = fallback_mode
            return results

    def _execute_mode(
        self,
        mode: str,
        normalized: List[Path],
        root: Path,
        worker_fn: Callable[[str, str], Dict[str, object]],
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> List[tuple[Path, Dict[str, object]]]:
        if mode == "serial":
            return self._run_serial(normalized, root, worker_fn, progress_callback)
        if mode == "thread":
            return self._run_executor(ThreadPoolExecutor, normalized, root, worker_fn, progress_callback, mode)
        if mode == "process":
            return self._run_executor(ProcessPoolExecutor, normalized, root, worker_fn, progress_callback, mode)
        raise ValueError(f"Unsupported worker mode: {mode}")

    def _run_serial(
        self,
        normalized: List[Path],
        root: Path,
        worker_fn: Callable[[str, str], Dict[str, object]],
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> List[tuple[Path, Dict[str, object]]]:
        results: List[tuple[Path, Dict[str, object]]] = []
        total = len(normalized)
        for completed, path in enumerate(normalized, start=1):
            rel_path = _safe_relative(path, root)
            result = worker_fn(str(path), str(root))
            results.append((path, result))
            if progress_callback:
                progress_callback(completed, total, rel_path)
        return results

    def _run_executor(
        self,
        executor_cls,
        normalized: List[Path],
        root: Path,
        worker_fn: Callable[[str, str], Dict[str, object]],
        progress_callback: Optional[Callable[[int, int, str], None]],
        mode: str,
    ) -> List[tuple[Path, Dict[str, object]]]:
        results: List[tuple[Path, Dict[str, object]]] = []
        total = len(normalized)
        completed = 0
        try:
            with executor_cls(max_workers=self.workers) as executor:
                future_map = {
                    executor.submit(worker_fn, str(path), str(root)): path
                    for path in normalized
                }
                for future in as_completed(future_map):
                    path = future_map[future]
                    completed += 1
                    rel_path = _safe_relative(path, root)
                    try:
                        result = future.result(timeout=self.timeout)
                    except TimeoutError:
                        self.failures.append(
                            {"path": rel_path, "error": f"timeout after {self.timeout}s"}
                        )
                        future.cancel()
                        result = None
                    except Exception as exc:
                        raise RuntimeError(f"{mode} worker failure for {rel_path}: {exc}") from exc
                    if result is not None:
                        results.append((path, result))
                    if progress_callback:
                        progress_callback(completed, total, rel_path)
        except Exception as exc:
            raise RuntimeError(f"{mode} worker pool failed: {exc}") from exc
        return results


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def _parse_single_file(path_str: str, root_str: str) -> Dict[str, object]:
    path = Path(path_str)
    root = Path(root_str)
    rel = _safe_relative(path, root)
    try:
        post = frontmatter.load(str(path))
        metadata = dict(post.metadata)
        content = post.content if hasattr(post, "content") else str(post)
        links = extract_wikilinks(content)
        links.extend(extract_frontmatter_links(metadata, include_plain_strings=True))

        obj = {
            "path": rel,
            "title": post.get("title", path.stem),
            "type": post.get("type", "unknown"),
            "status": post.get("status", "unknown"),
            "frontmatter": metadata,
            "content": content,
            "wikilinks": links,
        }
        return {"ok": True, "object": obj}
    except Exception as exc:
        return {"ok": False, "path": rel, "error": str(exc)}


def _hash_single_file(path_str: str, root_str: str) -> Dict[str, object]:
    path = Path(path_str)
    root = Path(root_str)
    rel = _safe_relative(path, root)
    try:
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        return {"ok": True, "path": rel, "hash": digest}
    except Exception as exc:
        return {"ok": False, "path": rel, "error": str(exc)}
