import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app import api_headers, destination_for, github_token, parse_github_folder_url, raw_file_url


class UrlParsingTests(unittest.TestCase):
    def test_parses_directory_url(self):
        item = parse_github_folder_url("https://github.com/Fux-i/Learning-In-UESTC/tree/main/3-%E5%A4%A7%E4%BA%8C%E4%B8%8A/%E7%BC%96%E8%AF%91%E5%8E%9F%E7%90%86")
        self.assertEqual(item.owner, "Fux-i")
        self.assertEqual(item.repository, "Learning-In-UESTC")
        self.assertEqual(item.branch, "main")
        self.assertEqual(item.folder, "3-大二上/编译原理")

    def test_rejects_non_folder_url(self):
        with self.assertRaises(ValueError):
            parse_github_folder_url("https://github.com/Fux-i/Learning-In-UESTC")

    def test_chooses_unique_destination(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "资料").mkdir()
            self.assertEqual(destination_for(root, "资料").name, "资料 (2)")

    def test_builds_encoded_raw_file_url(self):
        item = parse_github_folder_url("https://github.com/a/repo/tree/main/course/%E7%BC%96%E8%AF%91.pdf")
        self.assertEqual(
            raw_file_url(item, "course/编译.pdf"),
            "https://raw.githubusercontent.com/a/repo/main/course/%E7%BC%96%E8%AF%91.pdf",
        )

    def test_uses_environment_token_for_api_requests(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
            github_token.cache_clear()
            self.assertEqual(api_headers()["Authorization"], "Bearer test-token")
        github_token.cache_clear()


if __name__ == "__main__":
    unittest.main()
