import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from specctl.cli import main
from tests.test_issue_registry import snapshot


class IssueCliTests(unittest.TestCase):
    def test_import_records_issue_without_claiming_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
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


if __name__ == "__main__":
    unittest.main()
