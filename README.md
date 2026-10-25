# GitHub Folder Downloader

一个面向普通用户的 Windows 桌面工具：复制 GitHub 仓库中某个文件夹的链接，选择保存位置，即可只下载该文件夹。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![Tests](https://github.com/Zhang21901/GitHub-Folder-Downloader/actions/workflows/tests.yml/badge.svg)](https://github.com/Zhang21901/GitHub-Folder-Downloader/actions/workflows/tests.yml)

> 适合需要下载课程资料、项目子模块或仓库内某份文档，但不想下载完整仓库的用户。

## 功能

- 仅下载 GitHub 仓库中指定的目录，不再保留 `.git` 元数据
- 公开仓库默认采用 8 路并发直连下载，减少 Git 初始化和解压等待
- 图形界面，无需手动输入 Git 命令
- 支持中文和 URL 编码路径
- 显示实时下载日志、成功状态和错误信息
- 同名目录自动添加序号，避免覆盖已有资料
- 支持顺序下载队列：下载中也可继续添加其他文件夹
- 支持取消当前任务或移除尚未开始的等待任务

## 使用方法

### 1. 安装前置工具

- [Git for Windows](https://git-scm.com/download/win)
- [Python 3.10 或更高版本](https://www.python.org/downloads/)

### 2. 启动程序

下载或克隆本项目后，双击 `run.bat`。也可以在项目目录打开 PowerShell 后执行：

```powershell
python app.py
```

### 3. 下载一个文件夹

1. 在 GitHub 网页中打开要下载的文件夹。
2. 复制浏览器地址，格式类似：

   ```text
   https://github.com/owner/repository/tree/main/path/to/folder
   ```

3. 将链接粘贴到程序中，选择“保存到”的本地位置。
4. 点击“加入下载队列”。

任务会按添加顺序逐个下载。下载某个大文件夹时，可以继续添加其他链接；它们会显示为“等待中”，并在前一个任务结束后自动开始。默认不同时下载多个目录，以避免争抢带宽和触发限流。

程序会把内容保存到：

```text
保存位置/文件夹名称
```

例如，下载链接：

```text
https://github.com/Fux-i/Learning-In-UESTC/tree/main/3-%E5%A4%A7%E4%BA%8C%E4%B8%8A/%E7%BC%96%E8%AF%91%E5%8E%9F%E7%90%86
```

会得到：

```text
所选保存位置/编译原理
```

## 常见问题

### 提示“未找到 Git”

安装 Git for Windows 后，关闭并重新打开程序。

### 为什么会切换到 Git 兼容模式？

公开仓库会优先使用极速直连下载。遇到 GitHub API 限流、超大仓库目录树或私有仓库时，程序会自动改用 Git 的 sparse checkout。兼容模式需要安装 Git for Windows，速度也可能受 Git 初始化影响。

### 如何取消或删除队列任务？

- 选择当前显示“下载中”的任务后，点击“取消当前任务”。
- 选择状态为“等待中”的任务后，点击“移除选中等待任务”。

### 提示 GitHub API rate limit exceeded

匿名 GitHub API 每小时只有 60 次请求额度，校园网、代理或公司网络中的多个用户可能共享同一个出口额度。程序会自动使用本机 GitHub CLI 的登录令牌；已通过 `gh auth login` 登录的用户无需额外设置。

未安装 GitHub CLI 时，也可在启动程序前设置个人访问令牌，程序只在内存中用于 API 请求，不会写入日志或保存到项目目录：

```powershell
$env:GITHUB_TOKEN = "github_pat_你的令牌"
python app.py
```

### 哪些链接可用？

目前支持 GitHub 文件夹页面链接，即地址中包含 `/tree/分支名/目录路径` 的链接。请复制浏览器地址栏中的链接，而不是文件链接或仓库首页链接。

## 原理

公开仓库默认通过 GitHub API 获取目录树，再以 8 路并发方式下载该目录的原始文件。API 不可用时，工具调用 Git 的 partial clone 与 `sparse-checkout` 作为备用路径。

## 开发

项目仅依赖 Python 标准库。运行测试：

```powershell
python -m unittest -v
```

欢迎提交 Issue 和 Pull Request。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目采用 [MIT License](LICENSE)。
