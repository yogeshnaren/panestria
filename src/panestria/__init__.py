"""Installed panestria package."""

from importlib.metadata import version

__all__ = ["package_version"]


def package_version() -> str:
    return version("panestria")
