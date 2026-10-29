"""Mandatory combined-runtime proof, outside the Node-only image build stage."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def test_native_text_edit_preserves_managed_image_editability():
    root = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    assert node, 'The combined CI image must include its existing Node test runtime'
    result = subprocess.run([node, '--test', '--test-name-pattern',
        'real native engine text edit', 'client/src/pageOps/managedImages.test.mjs'],
        cwd=root, env={**os.environ, 'PDF_TOOL_TEST_PYTHON': sys.executable},
        capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout+result.stderr
    assert re.search(r'^# pass 1$', result.stdout, re.MULTILINE), result.stdout
