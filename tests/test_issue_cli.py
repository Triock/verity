import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from specctl.cli import main
from tests.test_issue_registry import snapshot


class IssueCliTests(unittest.TestCase):
    def test_start_dispatches_validated_issue_to_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", directory], check=True)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/Triock/verity.git"], cwd=directory, check=True)
            previous = Path.cwd()
            try:
                os.chdir(directory)
                output = io.StringIO()
                expected = {"branch": "verity/issue-7", "durable": True}
                with patch("specctl.cli.fetch_issue", return_value=snapshot()) as fetched:
                    with patch("specctl.cli.start_issue", return_value=expected) as started:
                        with redirect_stdout(output):
                            status = main(["issue", "start", "7", "--token-file", "/tmp/token"])
            finally:
                os.chdir(previous)
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue()), expected)
            fetched.assert_called_once_with(7, Path("/tmp/token"))
            started.assert_called_once_with(Path(directory), snapshot(), Path("/tmp/token"))

    def test_import_records_issue_without_claiming_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", directory], check=True)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/Triock/verity.git"], cwd=directory, check=True)
            previous = Path.cwd()
            try:
                (Path(directory) / "nested").mkdir()
                os.chdir(Path(directory) / "nested")
                output = io.StringIO()
                with patch("specctl.cli.fetch_issue", return_value=snapshot()), redirect_stdout(output):
                    status = main(["issue", "import", "7", "--token-file", "/tmp/token"])
            finally:
                os.chdir(previous)
            self.assertEqual(status, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["source"], "github:Triock/verity#7")
            self.assertFalse(result["committed"])
            self.assertTrue((Path(directory) / result["snapshot_path"]).exists())
            self.assertTrue((Path(directory) / result["current_path"]).exists())
            self.assertFalse((Path(directory) / "nested" / ".verity").exists())

    def test_import_rejects_other_account_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", directory], check=True)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/RichardHillman-Aderant/verity.git"], cwd=directory, check=True)
            previous = Path.cwd()
            try:
                os.chdir(directory)
                errors = io.StringIO()
                with patch("specctl.cli.fetch_issue", return_value=snapshot()):
                    with redirect_stderr(errors):
                        status = main(["issue", "import", "7", "--token-file", "/tmp/token"])
            finally:
                os.chdir(previous)
            self.assertEqual(status, 2)
            self.assertIn("Triock/verity", errors.getvalue())
            self.assertFalse((Path(directory) / ".verity").exists())


if __name__ == "__main__":
    unittest.main()
