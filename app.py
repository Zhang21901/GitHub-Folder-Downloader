"""GitHub Folder Downloader - a small, dependency-free Windows desktop app."""

from __future__ import annotations

import concurrent.futures
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, W, X, filedialog, messagebox, ttk
import tkinter as tk
from urllib.parse import quote, unquote, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APP_NAME = "GitHub Folder Downloader"
API_USER_AGENT = "GitHub-Folder-Downloader"
NETWORK_ATTEMPTS = 3


class DirectDownloadError(RuntimeError):
    """The public GitHub API download path could not be completed."""


@dataclass(frozen=True)
class GitHubFolder:
    owner: str
    repository: str
    branch: str
    folder: str

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repository}.git"

    @property
    def tree_url(self) -> str:
        branch = quote(self.branch, safe="")
        return f"https://api.github.com/repos/{self.owner}/{self.repository}/git/trees/{branch}?recursive=1"

    @property
    def folder_name(self) -> str:
        return Path(self.folder).name


@dataclass(frozen=True)
class DownloadTask:
    task_id: int
    item: GitHubFolder
    parent: Path


def parse_github_folder_url(url: str) -> GitHubFolder:
    """Parse the usual GitHub directory URL, with a one-segment branch name."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise ValueError("请输入 GitHub 文件夹链接，例如 https://github.com/owner/repo/tree/main/folder")

    parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
    if len(parts) < 5 or parts[2] != "tree" or not all(parts):
        raise ValueError("链接应指向 GitHub 的文件夹页面（包含 /tree/分支名/目录）。")
    return GitHubFolder(parts[0], parts[1], parts[3], "/".join(parts[4:]))


def destination_for(parent: Path, folder_name: str) -> Path:
    candidate = parent / folder_name
    index = 2
    while candidate.exists():
        candidate = parent / f"{folder_name} ({index})"
        index += 1
    return candidate


@lru_cache(maxsize=1)
def github_token() -> str:
    """Return an optional local token without writing it to disk or logs."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if token := os.environ.get(name, "").strip():
            return token
    if shutil.which("gh"):
        try:
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return ""


def api_headers() -> dict[str, str]:
    headers = {"User-Agent": API_USER_AGENT, "Accept": "application/vnd.github+json"}
    if token := github_token():
        headers["Authorization"] = f"Bearer {token}"
    return headers


def remote_files(item: GitHubFolder) -> list[dict[str, object]]:
    """List blobs below a public GitHub folder without cloning its repository."""
    request = Request(item.tree_url, headers=api_headers())
    for attempt in range(1, NETWORK_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except (HTTPError, URLError, OSError) as exc:
            if attempt == NETWORK_ATTEMPTS:
                raise DirectDownloadError(f"无法读取 GitHub 目录清单（已重试 {attempt} 次）：{exc}") from exc
            time.sleep(attempt)

    if payload.get("truncated"):
        raise DirectDownloadError("仓库目录树过大，无法使用极速下载。")
    prefix = item.folder.rstrip("/") + "/"
    files = [entry for entry in payload.get("tree", [])
             if entry.get("type") == "blob" and str(entry.get("path", "")).startswith(prefix)]
    if not files:
        raise DirectDownloadError("未在 GitHub 中找到目标文件夹。")
    return files


def raw_file_url(item: GitHubFolder, path: str) -> str:
    return "https://raw.githubusercontent.com/{}/{}/{}/{}".format(
        item.owner, item.repository, quote(item.branch, safe=""), quote(path, safe="/"))


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.minsize(820, 690)
        self.geometry("900x740")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.download_queue: queue.Queue[DownloadTask] = queue.Queue()
        self.task_rows: dict[int, str] = {}
        self.removed_task_ids: set[int] = set()
        self.next_task_id = 1
        self.active_task_id: int | None = None
        self.active_process: subprocess.Popen[str] | None = None
        self.cancelled = False

        self.url_var = tk.StringVar()
        self.location_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.status_var = tk.StringVar(value="粘贴 GitHub 文件夹链接，然后选择保存位置。")
        self._build()
        self.after(100, self._consume_events)
        threading.Thread(target=self._queue_worker, daemon=True).start()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=22)
        root.pack(fill=BOTH, expand=True)
        ttk.Label(root, text="GitHub 文件夹下载器", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor=W)
        ttk.Label(root, text="仅下载指定文件夹；公开仓库默认使用极速直连下载。", foreground="#505a68").pack(anchor=W, pady=(5, 20))

        ttk.Label(root, text="GitHub 文件夹链接").pack(anchor=W)
        self.url_entry = ttk.Entry(root, textvariable=self.url_var)
        self.url_entry.pack(fill=X, pady=(6, 16), ipady=5)
        self.url_entry.insert(0, "https://github.com/owner/repository/tree/main/folder")

        ttk.Label(root, text="保存到").pack(anchor=W)
        location = ttk.Frame(root)
        location.pack(fill=X, pady=(6, 16))
        self.location_entry = ttk.Entry(location, textvariable=self.location_var)
        self.location_entry.pack(side=LEFT, fill=X, expand=True, ipady=5)
        self.browse_button = ttk.Button(location, text="选择位置...", command=self._choose_location)
        self.browse_button.pack(side=RIGHT, padx=(8, 0))

        actions = ttk.Frame(root)
        actions.pack(fill=X, pady=(0, 12))
        self.download_button = ttk.Button(actions, text="加入下载队列", command=self._start_download)
        self.download_button.pack(side=LEFT)
        self.cancel_button = ttk.Button(actions, text="取消当前任务", command=self._cancel, state="disabled")
        self.cancel_button.pack(side=LEFT, padx=(8, 0))
        self.remove_button = ttk.Button(actions, text="移除选中等待任务", command=self._remove_selected)
        self.remove_button.pack(side=LEFT, padx=(8, 0))

        ttk.Label(root, text="下载队列（按添加顺序执行）").pack(anchor=W, pady=(4, 6))
        self.task_table = ttk.Treeview(root, columns=("folder", "location", "status"), show="headings", height=7)
        self.task_table.heading("folder", text="文件夹")
        self.task_table.heading("location", text="保存位置")
        self.task_table.heading("status", text="状态")
        self.task_table.column("folder", width=170, anchor=W)
        self.task_table.column("location", width=440, anchor=W)
        self.task_table.column("status", width=170, anchor=W)
        self.task_table.pack(fill=X, pady=(0, 12))

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill=X, pady=(0, 12))
        ttk.Label(root, textvariable=self.status_var).pack(anchor=W)

        ttk.Label(root, text="下载日志").pack(anchor=W, pady=(12, 6))
        self.log = tk.Text(root, height=10, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill=BOTH, expand=True)

    def _choose_location(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.location_var.get() or str(Path.home()))
        if chosen:
            self.location_var.set(chosen)

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(END, line.rstrip() + "\n")
        self.log.see(END)
        self.log.configure(state="disabled")

    def _start_download(self) -> None:
        try:
            item = parse_github_folder_url(self.url_var.get())
            parent = Path(self.location_var.get()).expanduser()
            if not parent.is_dir():
                raise ValueError("请选择一个已存在的保存位置。")
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        task = DownloadTask(self.next_task_id, item, parent)
        self.next_task_id += 1
        target = destination_for(parent, item.folder_name)
        row = self.task_table.insert("", END, values=(item.folder, str(target), "等待中"))
        self.task_rows[task.task_id] = row
        self.download_queue.put(task)
        self._append_log(f"已加入队列：{item.clone_url}，目录：{item.folder}")
        self.status_var.set(f"已加入队列，等待任务数：{self.download_queue.qsize()}。")

    def _remove_selected(self) -> None:
        selected = self.task_table.selection()
        if not selected:
            return
        row = selected[0]
        task_id = next((key for key, value in self.task_rows.items() if value == row), None)
        if task_id is None or task_id == self.active_task_id:
            messagebox.showinfo(APP_NAME, "当前正在下载的任务请使用“取消当前任务”。")
            return
        values = self.task_table.item(row, "values")
        if values and values[2] == "等待中":
            self.removed_task_ids.add(task_id)
            self.task_table.delete(row)
            del self.task_rows[task_id]
            self.status_var.set("已移除等待任务。")

    def _task_event(self, kind: str, value: str) -> None:
        if self.active_task_id is not None:
            self.events.put((kind, (self.active_task_id, value)))

    def _queue_worker(self) -> None:
        while True:
            task = self.download_queue.get()
            if task.task_id in self.removed_task_ids:
                self.download_queue.task_done()
                continue
            self.active_task_id = task.task_id
            self.cancelled = False
            self.events.put(("task_started", task.task_id))
            try:
                mode, target, count = self._download(task.item, task.parent)
                self.events.put(("task_finished", (task.task_id, True, f"完成（{mode}，{count} 个文件）", str(target))))
            except Exception as exc:
                self.events.put(("task_finished", (task.task_id, False, f"失败：{exc}", "")))
            finally:
                self.active_task_id = None
                self.download_queue.task_done()

    def _run(self, args: list[str], cwd: Path | None = None) -> None:
        self._task_event("task_log", "$ " + subprocess.list2cmdline(args))
        self.active_process = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                               text=True, encoding="utf-8", errors="replace")
        assert self.active_process.stdout is not None
        for line in self.active_process.stdout:
            self._task_event("task_log", line)
        code = self.active_process.wait()
        self.active_process = None
        if self.cancelled:
            raise RuntimeError("下载已取消。")
        if code:
            raise RuntimeError(f"命令执行失败（退出代码 {code}）。")

    def _download_file(self, item: GitHubFolder, path: str, output: Path) -> int:
        if self.cancelled:
            raise RuntimeError("下载已取消。")
        destination = output / Path(path).relative_to(item.folder)
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = Request(raw_file_url(item, path), headers={"User-Agent": API_USER_AGENT})
        for attempt in range(1, NETWORK_ATTEMPTS + 1):
            total = 0
            try:
                with urlopen(request, timeout=60) as response, destination.open("wb") as file:
                    while chunk := response.read(1024 * 1024):
                        if self.cancelled:
                            raise RuntimeError("下载已取消。")
                        file.write(chunk)
                        total += len(chunk)
                return total
            except (HTTPError, URLError, OSError) as exc:
                if destination.exists():
                    destination.unlink()
                if attempt == NETWORK_ATTEMPTS:
                    raise RuntimeError(f"文件下载失败（已重试 {attempt} 次）：{path}；{exc}") from exc
                time.sleep(attempt)
        raise RuntimeError(f"文件下载失败：{path}")

    def _download_direct(self, item: GitHubFolder, target: Path) -> int:
        files = remote_files(item)
        total_bytes = sum(int(entry.get("size", 0)) for entry in files)
        self._task_event("task_status", f"极速下载：准备下载 {len(files)} 个文件...")
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.downloading-", dir=target.parent))
        content = stage / "content"
        content.mkdir()
        completed = 0
        downloaded_bytes = 0
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(self._download_file, item, str(entry["path"]), content) for entry in files]
                for future in concurrent.futures.as_completed(futures):
                    downloaded_bytes += future.result()
                    completed += 1
                    self._task_event("task_status", f"极速下载：{completed}/{len(files)} 个文件，{downloaded_bytes / 1024 / 1024:.1f}/{total_bytes / 1024 / 1024:.1f} MB")
            content.replace(target)
            return completed
        except Exception as exc:
            shutil.rmtree(stage, ignore_errors=True)
            if self.cancelled:
                raise RuntimeError("下载已取消。") from exc
            raise DirectDownloadError(str(exc)) from exc
        finally:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)

    def _download_with_git(self, item: GitHubFolder, target: Path) -> int:
        if shutil.which("git") is None:
            raise RuntimeError("极速下载不可用，且未找到 Git。请安装 Git for Windows 后重试：https://git-scm.com/download/win")
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.git-", dir=target.parent))
        repository = stage / "repository"
        try:
            self._task_event("task_status", "正在使用 Git 兼容模式下载...")
            self._run(["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", "--branch", item.branch,
                       item.clone_url, str(repository)])
            self._run(["git", "-C", str(repository), "sparse-checkout", "set", "--no-cone", item.folder])
            self._run(["git", "-C", str(repository), "checkout", item.branch])
            downloaded = repository / item.folder
            if not downloaded.is_dir():
                raise RuntimeError("未找到目标文件夹；请检查链接是否正确。")
            count = sum(1 for path in downloaded.rglob("*") if path.is_file())
            downloaded.replace(target)
            return count
        finally:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)

    def _download(self, item: GitHubFolder, parent: Path) -> tuple[str, Path, int]:
        target = destination_for(parent, item.folder_name)
        try:
            count = self._download_direct(item, target)
            mode = "极速直连"
        except DirectDownloadError as exc:
            self._task_event("task_log", f"极速下载不可用，切换至 Git 兼容模式：{exc}")
            count = self._download_with_git(item, target)
            mode = "Git 兼容模式"
        return mode, target, count

    def _cancel(self) -> None:
        self.cancelled = True
        if self.active_process and self.active_process.poll() is None:
            self.active_process.terminate()
        self.status_var.set("正在取消下载...")

    def _consume_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "task_started":
                    task_id = int(value)
                    row = self.task_rows.get(task_id)
                    if row:
                        values = list(self.task_table.item(row, "values"))
                        values[2] = "下载中"
                        self.task_table.item(row, values=values)
                    self.progress.start(12)
                    self.cancel_button.configure(state="normal")
                    self.status_var.set("正在下载队列中的下一个任务...")
                elif kind in {"task_status", "task_log"}:
                    task_id, text = value  # type: ignore[misc]
                    row = self.task_rows.get(task_id)
                    if kind == "task_status" and row:
                        values = list(self.task_table.item(row, "values"))
                        values[2] = str(text)
                        self.task_table.item(row, values=values)
                        self.status_var.set(str(text))
                    elif kind == "task_log":
                        self._append_log(str(text))
                elif kind == "task_finished":
                    task_id, succeeded, status, target = value  # type: ignore[misc]
                    row = self.task_rows.get(task_id)
                    if row:
                        values = list(self.task_table.item(row, "values"))
                        values[1] = str(target) or values[1]
                        values[2] = str(status)
                        self.task_table.item(row, values=values)
                    self.progress.stop()
                    self.cancel_button.configure(state="disabled")
                    self.status_var.set("任务完成，正在等待下一个任务。" if succeeded else "任务失败，正在继续队列。")
                    self._append_log(str(status))
        except queue.Empty:
            pass
        self.after(100, self._consume_events)


if __name__ == "__main__":
    DownloaderApp().mainloop()
