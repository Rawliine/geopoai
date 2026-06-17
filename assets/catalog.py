"""Blessed asset pack catalog — programmatic resolvers only, no manual URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote

_GOOGLE_FONTS_RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl"


@dataclass(frozen=True)
class PackDefinition:
    """Static catalog entry for a provisionable asset pack."""

    name: str
    kind: str
    license: str
    license_url: str
    resolve: Callable[[], "ResolvedSource"]


@dataclass(frozen=True)
class ResolvedSource:
    """Download target before sha256 is known (computed on first fetch)."""

    resolved_url: str
    version: str
    archive_prefix: str = ""
    extract_glob: str = ""
    dest_subdir: str = ""
    direct_files: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def _github_release_asset(repo: str, asset_substring: str) -> ResolvedSource:
    import json
    import urllib.request

    api = f"https://api.github.com/repos/{repo}/releases/latest"
    with urllib.request.urlopen(api, timeout=60) as resp:
        release = json.loads(resp.read().decode("utf-8"))
    tag = release["tag_name"]
    asset = next(
        a for a in release["assets"] if asset_substring in a["name"]
    )
    return ResolvedSource(
        resolved_url=asset["browser_download_url"],
        version=tag.lstrip("v"),
        archive_prefix="",
        extract_glob="**/*.svg",
        dest_subdir="",
    )


def _github_tag_archive(
    repo: str,
    tag: str,
    *,
    archive_prefix: str,
    extract_glob: str,
    dest_subdir: str = "",
) -> ResolvedSource:
    return ResolvedSource(
        resolved_url=f"https://github.com/{repo}/archive/refs/tags/{tag}.zip",
        version=tag.lstrip("v"),
        archive_prefix=archive_prefix,
        extract_glob=extract_glob,
        dest_subdir=dest_subdir,
    )


def _github_branch_archive(
    repo: str,
    branch: str,
    *,
    archive_prefix: str,
    extract_glob: str,
    dest_subdir: str = "",
    version: str | None = None,
) -> ResolvedSource:
    return ResolvedSource(
        resolved_url=f"https://github.com/{repo}/archive/refs/heads/{branch}.zip",
        version=version or branch,
        archive_prefix=archive_prefix,
        extract_glob=extract_glob,
        dest_subdir=dest_subdir,
    )


def _google_font_files(
    family_dir: str,
    filenames: tuple[str, ...],
    *,
    version: str = "main",
) -> ResolvedSource:
    """Pin individual TTFs from google/fonts main (variable/static as shipped)."""
    files = tuple(
        (f"{_GOOGLE_FONTS_RAW}/{family_dir}/{quote(name)}", name)
        for name in filenames
    )
    return ResolvedSource(
        resolved_url=files[0][0],
        version=version,
        direct_files=files,
    )


def _repo_archive_prefix(repo: str, tag: str) -> str:
    """Top-level folder name inside a GitHub tag archive zip."""
    short = repo.split("/")[-1]
    return f"{short}-{tag.lstrip('v')}/"


# Pack registry keyed by CLI name.
PACKS: dict[str, PackDefinition] = {
    "lucide": PackDefinition(
        name="lucide",
        kind="icons",
        license="ISC",
        license_url="https://opensource.org/licenses/ISC",
        resolve=lambda: _github_release_asset("lucide-icons/lucide", "lucide-icons-"),
    ),
    "tabler": PackDefinition(
        name="tabler",
        kind="icons",
        license="MIT",
        license_url="https://opensource.org/licenses/MIT",
        resolve=lambda: _github_tag_archive(
            "tabler/tabler-icons",
            "v3.44.0",
            archive_prefix=f"{_repo_archive_prefix('tabler/tabler-icons', 'v3.44.0')}icons/",
            extract_glob="*.svg",
        ),
    ),
    "phosphor": PackDefinition(
        name="phosphor",
        kind="icons",
        license="MIT",
        license_url="https://opensource.org/licenses/MIT",
        resolve=lambda: _github_tag_archive(
            "phosphor-icons/phosphor-icons",
            "v2.1.2",
            archive_prefix=f"{_repo_archive_prefix('phosphor-icons/phosphor-icons', 'v2.1.2')}src/regular/",
            extract_glob="*.svg",
        ),
    ),
    "circle-flags": PackDefinition(
        name="circle-flags",
        kind="icons",
        license="MIT",
        license_url="https://opensource.org/licenses/MIT",
        resolve=lambda: _github_tag_archive(
            "HatScripts/circle-flags",
            "v2.8.0",
            archive_prefix=f"{_repo_archive_prefix('HatScripts/circle-flags', 'v2.8.0')}flags/",
            extract_glob="*.svg",
        ),
    ),
    "kenney-ui-audio": PackDefinition(
        name="kenney-ui-audio",
        kind="sfx",
        license="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        resolve=lambda: _github_branch_archive(
            "Calinou/kenney-ui-audio",
            "master",
            archive_prefix="kenney-ui-audio-master/addons/kenney_ui_audio/",
            extract_glob="**/*.{wav,ogg}",
            version="1.0.0",
        ),
    ),
    "kenney-impact-sounds": PackDefinition(
        name="kenney-impact-sounds",
        kind="sfx",
        license="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        resolve=lambda: _github_branch_archive(
            "Boyquotes/kenney-impact-sounds-for-godot",
            "main",
            archive_prefix=(
                "kenney-impact-sounds-for-godot-main/addons/kenney impact sounds/"
            ),
            extract_glob="impact*.ogg",
            version="1.0.0",
        ),
    ),
    "Inter": PackDefinition(
        name="Inter",
        kind="font",
        license="OFL-1.1",
        license_url="https://openfontlicense.org/",
        resolve=lambda: _google_font_files(
            "inter",
            ("Inter[opsz,wght].ttf", "Inter-Italic[opsz,wght].ttf"),
        ),
    ),
    "Barlow Condensed": PackDefinition(
        name="Barlow Condensed",
        kind="font",
        license="OFL-1.1",
        license_url="https://openfontlicense.org/",
        resolve=lambda: _google_font_files(
            "barlowcondensed",
            (
                "BarlowCondensed-Regular.ttf",
                "BarlowCondensed-Bold.ttf",
                "BarlowCondensed-SemiBold.ttf",
            ),
        ),
    ),
    "JetBrains Mono": PackDefinition(
        name="JetBrains Mono",
        kind="font",
        license="OFL-1.1",
        license_url="https://openfontlicense.org/",
        resolve=lambda: _google_font_files(
            "jetbrainsmono",
            ("JetBrainsMono[wght].ttf", "JetBrainsMono-Italic[wght].ttf"),
        ),
    ),
    "STIX Two Math": PackDefinition(
        name="STIX Two Math",
        kind="font",
        license="OFL-1.1",
        license_url="https://openfontlicense.org/",
        resolve=lambda: _google_font_files(
            "stixtwomath",
            ("STIXTwoMath-Regular.ttf",),
        ),
    ),
}


def pack_slug(name: str) -> str:
    """Filesystem-safe pack directory name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def list_pack_names() -> list[str]:
    return sorted(PACKS.keys())
