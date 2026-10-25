"""GitHub Folder Downloader - a small, dependency-free Windows desktop app."""

from __future__ import annotations

import concurrent.futures
import json
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
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


def remote_files(item: GitHubFolder) -> list[dict[str, object]]:
    """List blobs below a public GitHub folder without cloning its repository."""
    request = Request(item.tree_url, headers={"User-Agent": API_USER_AGENT, "Accept": "application/vnd.github+json"})
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
        self.minsize(760, 530)
        self.geometry("820x580")
        self.events: queue.Queue[tuple[str, str | int]] = queue.Queue()
        self.active_process: subprocess.Popen[str] | None = None
        self.cancelled = False

        self.url_var = tk.StringVar()
        self.location_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.status_var = tk.StringVar(value="粘贴 GitHub 文件夹链接，然后选择保存位置。")
        self._build()
        self.after(100, self._consume_events)

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
        self.download_button = ttk.Button(actions, text="开始下载", command=self._start_download)
        self.download_button.pack(side=LEFT)
        self.cancel_button = ttk.Button(actions, text="取消", command=self._cancel, state="disabled")
        self.cancel_button.pack(side=LEFT, padx=(8, 0))

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill=X, pady=(0, 12))
        ttk.Label(root, textvariable=self.status_var).pack(anchor=W)

        ttk.Label(root, text="下载日志").pack(anchor=W, pady=(18, 6))
        self.log = tk.Text(root, height=13, wrap="word", state="disabled", font=("Consolas", 9))
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

        self.cancelled = False
        self.download_button.configure(state="disabled")
        self.browse_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.start(12)
        self._append_log(f"链接：{item.clone_url}，目录：{item.folder}")
        threading.Thread(target=self._download, args=(item, parent), daemon=True).start()

    def _run(self, args: list[str], cwd: Path | None = None) -> None:
        self.events.put(("log", "$ " + subprocess.list2cmdline(args)))
        self.active_process = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                               text=True, encoding="utf-8", errors="replace")
        assert self.active_process.stdout is not None
        for line in self.active_process.stdout:
            self.events.put(("log", line))
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
        self.events.put(("status", f"极速下载：准备下载 {len(files)} 个文件..."))
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
                    self.events.put(("status", f"极速下载：{completed}/{len(files)} 个文件，{downloaded_bytes / 1024 / 1024:.1f}/{total_bytes / 1024 / 1024:.1f} MB"))
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
            self.events.put(("status", "正在使用 Git 兼容模式下载..."))
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

    def _download(self, item: GitHubFolder, parent: Path) -> None:
        target = destination_for(parent, item.folder_name)
        try:
            try:
                count = self._download_direct(item, target)
                mode = "极速直连"
            except DirectDownloadError as exc:
                self.events.put(("log", f"极速下载不可用，切换至 Git 兼容模式：{exc}"))
                count = self._download_with_git(item, target)
                mode = "Git 兼容模式"
            self.events.put(("success", f"下载完成（{mode}）：{target}\n共下载 {count} 个文件。"))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _cancel(self) -> None:
        self.cancelled = True
        if self.active_process and self.active_process.poll() is None:
            self.active_process.terminate()
        self.status_var.set("正在取消下载...")

    def _finish(self) -> None:
        self.progress.stop()
        self.download_button.configure(state="normal")
        self.browse_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def _consume_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(value))
                elif kind == "status":
                    self.status_var.set(str(value))
                elif kind == "success":
                    self._finish()
                    self.status_var.set("下载完成。")
                    self._append_log(str(value))
                    messagebox.showinfo(APP_NAME, str(value))
                elif kind == "error":
                    self._finish()
                    self.status_var.set("下载未完成。")
                    self._append_log("错误：" + str(value))
                    messagebox.showerror(APP_NAME, str(value))
        except queue.Empty:
            pass
        self.after(100, self._consume_events)


if __name__ == "__main__":
    DownloaderApp().mainloop()
