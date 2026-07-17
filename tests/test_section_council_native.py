"""linux-native-id-v1 encoder proofs (HSC-B foundation).

These exercise the real openat2/statx/name_to_handle_at/fstatfs primitives
against a temporary directory. Where a primitive is genuinely unavailable the
encoder must fail closed; this environment (WSL2, kernel 6.6, bwrap 0.9.0) has
all of them, so the happy-path assertions run here.
"""

from __future__ import annotations

import os

import pytest

from tools.section_council import native
from tools.section_council.core import (file_id, filesystem_id,
                                        validate_native_observation)
from tools.section_council.native import NativeIdentityUnavailable

_AVAILABLE = True
try:
    native.probe_availability()
except NativeIdentityUnavailable:
    _AVAILABLE = False

requires_native = pytest.mark.skipif(
    not _AVAILABLE, reason="linux-native-id-v1 primitives unavailable")


@requires_native
def test_observation_validates_and_derives_ids(tmp_path):
    (tmp_path / "file.txt").write_bytes(b"hello")
    anchor = os.open(str(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        obs = native.observe(anchor, b"file.txt")
        directory = native.observe(anchor, b".", directory=True)
    finally:
        os.close(anchor)
    # The regular file and the directory both validate under the HSC-A schema.
    validate_native_observation(obs)
    validate_native_observation(directory)
    assert obs["file_type"] == "regular"
    assert obs["native_mode"] & native.S_IFMT == native.S_IFREG
    assert obs["link_count"] == 1
    assert directory["file_type"] == "directory"
    assert directory["native_mode"] & native.S_IFMT == native.S_IFDIR
    # Derived ids reconstruct through the frozen domains.
    assert len(filesystem_id(obs)) == 64
    assert len(file_id(obs)) == 64
    # Two distinct files on the same filesystem share filesystem_id but not
    # file_id.
    (tmp_path / "other.txt").write_bytes(b"world")
    anchor = os.open(str(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        other = native.observe(anchor, b"other.txt")
    finally:
        os.close(anchor)
    assert filesystem_id(other) == filesystem_id(obs)
    assert file_id(other) != file_id(obs)


@requires_native
def test_observation_is_stable_across_repeat(tmp_path):
    (tmp_path / "f").write_bytes(b"x")
    anchor = os.open(str(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        first, first_fs, first_file = native.observe_ids(anchor, b"f")
        second, second_fs, second_file = native.observe_ids(anchor, b"f")
    finally:
        os.close(anchor)
    assert first == second
    assert (first_fs, first_file) == (second_fs, second_file)


@requires_native
def test_symlink_is_refused_no_follow(tmp_path):
    (tmp_path / "real").write_bytes(b"data")
    os.symlink("real", str(tmp_path / "link"))
    anchor = os.open(str(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        # RESOLVE_NO_SYMLINKS makes the final-component symlink itself refuse.
        with pytest.raises(NativeIdentityUnavailable):
            native.observe(anchor, b"link")
    finally:
        os.close(anchor)


@requires_native
def test_escape_above_anchor_is_refused(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    anchor = os.open(str(sub), os.O_RDONLY | os.O_DIRECTORY)
    try:
        # RESOLVE_BENEATH refuses a traversal that would escape the anchor.
        with pytest.raises(NativeIdentityUnavailable):
            native.observe(anchor, b"../sibling")
    finally:
        os.close(anchor)


@requires_native
def test_absent_target_fails_closed(tmp_path):
    anchor = os.open(str(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(NativeIdentityUnavailable):
            native.observe(anchor, b"does-not-exist")
    finally:
        os.close(anchor)
