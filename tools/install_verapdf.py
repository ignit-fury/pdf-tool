"""Install authenticated veraPDF 1.30.3 CLI for development/CI only.

Official provenance: https://docs.verapdf.org/install/ documents the signing key
and unattended CLI pack. Distribution is dual GPLv3+/MPLv2+; preserve upstream
notices. Java is required (CI uses Temurin 21); no JVM or runtime dependency is
installed by this script. Archive digest was authenticated before Phase 8 work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import zipfile

VERSION = "1.30.3"
ARCHIVE_URL = f"https://software.verapdf.org/rel/1.30/verapdf-greenfield-{VERSION}-installer.zip"
SIGNATURE_URL = ARCHIVE_URL + ".asc"
KEY_URL = "https://software.verapdf.org/keys/KEY"
SHA256 = "b512bf24945503a33fc10738ecffc1f2dccaaf8593a448e94ee9ac86a9559a59"
FINGERPRINT = "13DD102B4DD69354D12DE5A83184863278B17FE7"
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024


def download(url: str, target: Path) -> None:
    with urlopen(url, timeout=60) as response, target.open("wb") as output:
        size = 0
        while chunk := response.read(65536):
            size += len(chunk)
            if size > MAX_DOWNLOAD_BYTES:
                raise ValueError("installer download exceeds limit")
            output.write(chunk)


def install(destination: Path, archive: Path | None = None,
            signature: Path | None = None, key: Path | None = None) -> Path:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"destination must not exist: {destination}")
    java_home = os.environ.get("JAVA_HOME")
    java = str(Path(java_home) / "bin/java") if java_home else shutil.which("java")
    gpg = shutil.which("gpg")
    if not java or not gpg:
        raise ValueError("Java and GPG must already be available")
    with tempfile.TemporaryDirectory(prefix="verapdf-installer-") as temporary:
        work = Path(temporary)
        downloads = []
        for supplied, url, name in ((archive, ARCHIVE_URL, "installer.zip"),
                                    (signature, SIGNATURE_URL, "installer.zip.asc"),
                                    (key, KEY_URL, "signing-key.asc")):
            path = supplied.resolve() if supplied else work / name
            if not supplied:
                download(url, path)
            downloads.append(path)
        archive, signature, key = downloads
        with archive.open("rb") as archive_file:
            digest = hashlib.file_digest(archive_file, "sha256").hexdigest()
        if digest != SHA256:
            raise ValueError(f"archive SHA-256 mismatch: {digest}")
        keyring = work / "gnupg"
        keyring.mkdir(mode=0o700)
        # Public-key verification needs no agent or persistent user keyring.
        gpg_args = [gpg, "--no-options", "--no-autostart", "--homedir", str(keyring), "--batch"]
        subprocess.run([*gpg_args, "--import", str(key)], check=True, timeout=60,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        verified = subprocess.run([*gpg_args, "--status-fd", "1", "--verify",
                                   str(signature), str(archive)], check=True, timeout=60,
                                  capture_output=True, text=True)
        signatures = [line.split()[2:] for line in verified.stdout.splitlines()
                      if line.startswith("[GNUPG:] VALIDSIG ")]
        if not any(fields and (fields[0] == FINGERPRINT or fields[-1] == FINGERPRINT)
                   for fields in signatures):
            raise ValueError("signature does not match pinned publisher fingerprint")

        # Extract only the exact JAR, never arbitrary archive paths/symlinks.
        jar_name = f"verapdf-greenfield-{VERSION}/verapdf-izpack-installer-{VERSION}.jar"
        with zipfile.ZipFile(archive) as package:
            info = package.getinfo(jar_name)
            if info.file_size > 128 * 1024 * 1024:
                raise ValueError("installer JAR exceeds limit")
            jar = work / "installer.jar"
            jar.write_bytes(package.read(info))
        root = ET.Element("AutomatedInstallation", langpack="eng")
        ET.SubElement(root, "com.izforge.izpack.panels.htmlhello.HTMLHelloPanel", id="welcome")
        target = ET.SubElement(root, "com.izforge.izpack.panels.target.TargetPanel", id="install_dir")
        ET.SubElement(target, "installpath").text = str(destination)
        packs = ET.SubElement(root, "com.izforge.izpack.panels.packs.PacksPanel", id="sdk_pack_select")
        for index, name in enumerate(("veraPDF GUI", "veraPDF CLI", "veraPDF Documentation",
                                      "veraPDF Sample Plugins")):
            ET.SubElement(packs, "pack", index=str(index), name=name,
                          selected="true" if index == 1 else "false")
        ET.SubElement(root, "com.izforge.izpack.panels.install.InstallPanel", id="install")
        ET.SubElement(root, "com.izforge.izpack.panels.finish.FinishPanel", id="finish")
        config = work / "auto-install.xml"
        ET.ElementTree(root).write(config, encoding="utf-8", xml_declaration=True)
        subprocess.run([java, "-jar", str(jar), str(config)], check=True, timeout=120)
        launcher = destination / "verapdf"
        if not launcher.is_file():
            raise ValueError("CLI installer did not produce the expected launcher")
        launcher.chmod(0o755)
        smoke = subprocess.run([str(launcher), "--version"], check=True, timeout=30,
                               capture_output=True, text=True)
        if f"veraPDF {VERSION}" not in smoke.stdout:
            raise ValueError(f"unexpected installed version: {smoke.stdout}")
        (destination / "provenance.json").write_text(json.dumps({
            "version": VERSION, "archive_url": ARCHIVE_URL, "signature_url": SIGNATURE_URL,
            "key_url": KEY_URL, "archive_sha256": SHA256, "signing_fingerprint": FINGERPRINT,
            "signature_verified": True, "cli_only": True, "java_requirement": "Java; CI Temurin 21",
            "licenses": ["GPL-3.0-or-later", "MPL-2.0"],
            "license_urls": ["https://www.gnu.org/licenses/gpl-3.0.html",
                             "https://www.mozilla.org/MPL/2.0/"],
            "installation_docs": "https://docs.verapdf.org/install/",
            "scope": "dev/CI subprocess only; preserve upstream license notices",
        }, indent=2) + "\n")
        return launcher


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="optional cached exact release ZIP")
    parser.add_argument("--signature", type=Path, help="optional cached detached signature")
    parser.add_argument("--key", type=Path, help="optional cached publisher key")
    args = parser.parse_args()
    try:
        print(install(args.destination, args.archive, args.signature, args.key))
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        parser.exit(1, f"veraPDF installation failed: {exc}\n{detail or ''}\n")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        parser.exit(1, f"veraPDF installation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
