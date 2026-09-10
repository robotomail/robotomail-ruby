"""Reject publishing a branch or a tag that differs from package metadata."""
import json
import os
import re
import subprocess
from pathlib import Path
import tomllib

config = json.loads(Path("sdk.json").read_text())
version = config["version"]
tag = os.environ["RELEASE_TAG"]
assert re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) and tag == "v" + version
assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == subprocess.check_output(["git", "rev-parse", tag + "^{commit}"], text=True).strip()
language = config["language"]
if language == "node":
    actual = json.loads(Path("package.json").read_text())["version"]
elif language == "python":
    actual = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
elif language == "rust":
    actual = tomllib.loads(Path("Cargo.toml").read_text())["package"]["version"]
else:
    actual = re.search(r'VERSION = "([^"]+)"', Path("lib/robotomail.rb").read_text())[1]
assert actual == version, "Package version differs from the release tag"
print("Release version verified:", tag)
