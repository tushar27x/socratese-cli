"""Vault detection and discovery.

Per decisions log: detect a vault by `.obsidian` directory presence,
walk upward from cwd (git-status-style) for single-vault lookup, and
do a bounded scan from OS-conventional roots for `init`.
"""
