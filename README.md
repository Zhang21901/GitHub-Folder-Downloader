# GitHub Folder Downloader

一个面向普通用户的 Windows 桌面工具：复制 GitHub 仓库中某个文件夹的链接，选择保存位置，即可只下载该文件夹。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![Tests](https://github.com/Zhang21901/GitHub-Folder-Downloader/actions/workflows/tests.yml/badge.svg)](https://github.com/Zhang21901/GitHub-Folder-Downloader/actions/workflows/tests.yml)

> 适合需要下载课程资料、项目子模块或仓库内某份文档，但不想下载完整仓库的用户。

## 功能

- 仅下载 GitHub 仓库中指定的目录
- 图形界面，无需手动输入 Git 命令
- 支持中文和 URL 编码路径
- 显示实时下载日志、成功状态和错误信息
- 同名目录自动添加序号，避免覆盖已有资料
- 取消下载按钮可停止当前 Git 操作

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
4. 点击“开始下载”。

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

### 下载结果比预期多出 `.git` 文件夹

这是 Git 为记录下载来源和支持后续更新而创建的元数据目录。它不会影响资料的正常打开；如果确认不再需要更新，可以手动删除 `.git` 文件夹。

### 哪些链接可用？

目前支持 GitHub 文件夹页面链接，即地址中包含 `/tree/分支名/目录路径` 的链接。请复制浏览器地址栏中的链接，而不是文件链接或仓库首页链接。

## 原理

本工具调用 Git 的 partial clone 与 `sparse-checkout`。它先获取仓库元数据，再仅把用户指定的路径检出到本地工作区。

## 开发

项目仅依赖 Python 标准库。运行测试：

```powershell
python -m unittest -v
```

欢迎提交 Issue 和 Pull Request。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目采用 [MIT License](LICENSE)。
