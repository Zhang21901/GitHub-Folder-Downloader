# 贡献指南

感谢你愿意改进 GitHub Folder Downloader。

## 提交问题

提交 Issue 前，请确认问题可以稳定复现，并附上：

- 使用的 GitHub 文件夹链接（隐私链接请删除敏感信息）
- Windows、Python 与 Git 版本
- 程序日志中的完整错误信息
- 复现步骤和预期结果

## 提交代码

1. Fork 本仓库并创建功能分支。
2. 保持改动小且聚焦，避免混入无关格式化。
3. 为逻辑改动补充或更新单元测试。
4. 提交前执行：

   ```powershell
   python -m unittest -v
   ```

5. 在 Pull Request 中说明改动内容、验证方式和相关 Issue。

## 代码约定

- 使用 Python 3.10+ 兼容语法。
- 保持项目零第三方 Python 依赖。
- 用户可见文案使用清晰、简洁的中文。
