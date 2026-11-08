"""scripts/package_extension.py: the zip for the Chrome Web Store, and what the store would refuse."""
import importlib.util
import json
import os
import shutil
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTENSION = os.path.join(ROOT, "extension")
spec = importlib.util.spec_from_file_location("package_extension", os.path.join(ROOT, "scripts", "package_extension.py"))
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def copy_with(tmp_path, change):
    folder = str(tmp_path / "extension")
    shutil.copytree(EXTENSION, folder, ignore=shutil.ignore_patterns("__pycache__"))
    path = os.path.join(folder, "manifest.json")
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    change(manifest)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    return folder


def test_the_real_extension_is_ready_and_its_zip_has_the_manifest_at_the_top(tmp_path):
    target = package.build(EXTENSION, str(tmp_path))
    with open(os.path.join(EXTENSION, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert os.path.basename(target) == "CrossChat-extension-%s.zip" % manifest["version"]
    with zipfile.ZipFile(target) as z:
        names = z.namelist()
        assert z.testzip() is None
        assert json.loads(z.read("manifest.json")) == manifest
    assert "background.js" in names and "icons/icon-128.png" in names
    for name in package.referenced(manifest):
        assert name in names
    assert names == sorted(names) and not any("\\" in n or n.endswith("/") or "__pycache__" in n for n in names)


def test_the_same_sources_make_the_same_zip(tmp_path):
    one = package.build(EXTENSION, str(tmp_path / "a"))
    two = package.build(EXTENSION, str(tmp_path / "b"))
    with open(one, "rb") as a, open(two, "rb") as b:
        assert a.read() == b.read()


@pytest.mark.parametrize("change, expected", [
    (lambda m: m.update(description="x" * 133), "description is 133 characters"),
    (lambda m: m.update(description=""), "description is 0 characters"),
    (lambda m: m.update(name="x" * 76), "name must be"),
    (lambda m: m.update(version="1.8.0-beta"), "version must be"),
    (lambda m: m.update(version="1.2.3.4.5"), "version must be"),
    (lambda m: m.update(manifest_version=2), "manifest_version must be 3"),
    (lambda m: m.update(key="abc"), '"key" is not allowed'),
    (lambda m: m.update(update_url="https://example.com"), '"update_url" is not allowed'),
    (lambda m: m["icons"].pop("128"), "128 x 128 icon"),
    (lambda m: m["content_scripts"][0]["js"].append("gone.js"), "names gone.js"),
    (lambda m: m["background"].update(service_worker="gone.js"), "names gone.js"),
])
def test_what_the_store_would_refuse_is_refused_here(tmp_path, change, expected):
    folder = copy_with(tmp_path, change)
    with pytest.raises(ValueError, match=expected):
        package.build(folder, str(tmp_path / "dist"))
    assert not os.path.exists(str(tmp_path / "dist"))


def test_exactly_at_the_limits_is_fine(tmp_path):
    folder = copy_with(tmp_path, lambda m: m.update(description="x" * 132, name="y" * 75))
    assert os.path.isfile(package.build(folder, str(tmp_path / "dist")))
