"""Closed encodings, paths, identities, and change algebra for HSC v1."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

from tools.council.schemas import (SchemaViolation, canonical_json,
                                   domain_hash)
from tools.council.schemas import validate_request_id as \
    _canonical_request_id


class HSCValidationError(ValueError):
    """A derived HSC record or relation violates the frozen v1 contract."""


H_RE = re.compile(r"^[0-9a-f]{64}$")
G_RE = re.compile(r"^[0-9a-f]{40}$")
EVENT_RE = re.compile(r"^[0-9]{6}-[0-9a-f]{8}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

NATIVE_PROFILE = "linux-native-id-v1"
NATIVE_PLATFORM = "linux-bwrap-v1"
NATIVE_RESOLUTION = "openat2-beneath-no-magiclinks-no-symlinks-v1"


def fail(message: str) -> None:
    raise HSCValidationError(message)


def exact_keys(value: Mapping[str, Any], keys: Iterable[str], where: str) -> None:
    if not isinstance(value, dict):
        fail(f"{where} must be an object")
    wanted = set(keys)
    have = set(value)
    if have != wanted:
        fail(f"{where} keys mismatch: missing={sorted(wanted-have)!r} "
             f"extra={sorted(have-wanted)!r}")


def require_string(value: Any, where: str, *, nonempty: bool = True,
                   max_bytes: int = 16384) -> str:
    if not isinstance(value, str):
        fail(f"{where} must be a string")
    length = len(value.encode("utf-8"))
    if (nonempty and length == 0) or length > max_bytes:
        fail(f"{where} has invalid UTF-8 byte length")
    return value


def require_literal(value: Any, allowed: Iterable[Any], where: str) -> Any:
    choices = tuple(allowed)
    if value not in choices or isinstance(value, bool) and value not in choices:
        fail(f"{where} must be one of {choices!r}")
    return value


def require_int(value: Any, where: str, *, minimum: int = 0,
                maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        fail(f"{where} must be a JSON integer")
    if value < minimum or maximum is not None and value > maximum:
        fail(f"{where} is outside its declared bound")
    return value


def require_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        fail(f"{where} must be a JSON boolean")
    return value


def require_h(value: Any, where: str) -> str:
    if not isinstance(value, str) or H_RE.fullmatch(value) is None:
        fail(f"{where} must be lowercase sha256 hex")
    return value


def require_g(value: Any, where: str) -> str:
    if not isinstance(value, str) or G_RE.fullmatch(value) is None:
        fail(f"{where} must be a lowercase 40-hex Git id")
    return value


def require_event(value: Any, where: str) -> str:
    if not isinstance(value, str) or EVENT_RE.fullmatch(value) is None:
        fail(f"{where} must be a Council event id")
    return value


def require_slug(value: Any, where: str) -> str:
    if not isinstance(value, str) or SLUG_RE.fullmatch(value) is None:
        fail(f"{where} must be a bounded lowercase slug")
    return value


def require_request_id(value: Any, where: str) -> str:
    # One grammar only: the canonical Council request-id validator. An HSC
    # identity must never exist for a request id the Council refuses.
    try:
        _canonical_request_id(value)
    except SchemaViolation:
        fail(f"{where} must be a canonical Council request id")
    return value


def require_hex_bytes(value: Any, where: str, *, minimum_bytes: int = 1,
                      maximum_bytes: int = 4096) -> bytes:
    if not isinstance(value, str) or not value or len(value) % 2 or \
            value.lower() != value or re.fullmatch(r"[0-9a-f]+", value) is None:
        fail(f"{where} must be nonempty even-length lowercase hex")
    raw = bytes.fromhex(value)
    if not minimum_bytes <= len(raw) <= maximum_bytes:
        fail(f"{where} decoded length is outside its bound")
    return raw


def canonical_sort_key(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def require_sorted_unique(values: Any, where: str, *, key=canonical_sort_key,
                          nonempty: bool = False) -> list[Any]:
    if not isinstance(values, list):
        fail(f"{where} must be an array")
    if nonempty and not values:
        fail(f"{where} must be nonempty")
    keys = [key(value) for value in values]
    if keys != sorted(keys):
        fail(f"{where} must be sorted canonically")
    if len(keys) != len(set(keys)):
        fail(f"{where} contains a duplicate")
    return values


def require_ordered(values: Any, where: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(values, list) or nonempty and not values:
        fail(f"{where} must be {'a nonempty ' if nonempty else 'an '}array")
    for ordinal, item in enumerate(values):
        if not isinstance(item, dict) or item.get("ordinal") != ordinal:
            fail(f"{where} ordinals must be contiguous from zero")
    return values


def validate_ref(value: Any, where: str, *, nullable: bool = False) -> dict | None:
    if value is None and nullable:
        return None
    exact_keys(value, {"record_id", "content_sha256"}, where)
    require_h(value["record_id"], f"{where}.record_id")
    require_h(value["content_sha256"], f"{where}.content_sha256")
    return value


def validate_path(value: Any, where: str = "path") -> str:
    require_string(value, where, max_bytes=1024)
    if "\\" in value or "\x00" in value or value.startswith("/") or \
            value.startswith("//") or re.match(r"^[A-Za-z]:", value):
        fail(f"{where} is not a safe repository-relative path")
    encoded = value.encode("utf-8")
    segments = value.split("/")
    if not 1 <= len(segments) <= 64 or not 1 <= len(encoded) <= 1024:
        fail(f"{where} exceeds path bounds")
    for segment in segments:
        if PATH_SEGMENT_RE.fullmatch(segment) is None:
            fail(f"{where} contains an invalid segment")
        if segment in (".", "..") or segment.casefold() == ".git" or \
                segment.casefold() in WINDOWS_RESERVED or \
                segment.endswith((".", " ")):
            fail(f"{where} contains a forbidden segment")
    return value


def path_collision_key(path: str) -> tuple[str, ...]:
    validate_path(path)
    return tuple(unicodedata.normalize("NFC", part).casefold()
                 for part in path.split("/"))


def require_unique_paths(paths: Sequence[str], where: str) -> None:
    keys: dict[tuple[str, ...], str] = {}
    for path in paths:
        key = path_collision_key(path)
        if key in keys:
            fail(f"{where} path collision between {keys[key]!r} and {path!r}")
        keys[key] = path


def validate_native_rel_path(value: Any, where: str = "native_path",
                             *, allow_empty: bool = False) -> tuple[bytes, ...]:
    exact_keys(value, {"segments_hex"}, where)
    segments = value["segments_hex"]
    if not isinstance(segments, list) or (not allow_empty and not segments) or \
            len(segments) > 256:
        fail(f"{where}.segments_hex has invalid depth")
    decoded: list[bytes] = []
    for index, segment in enumerate(segments):
        raw = require_hex_bytes(segment, f"{where}.segments_hex[{index}]",
                                maximum_bytes=255)
        if raw in (b".", b"..") or b"\x00" in raw or b"/" in raw:
            fail(f"{where} contains a forbidden native segment")
        decoded.append(raw)
    if sum(map(len, decoded)) + max(0, len(decoded) - 1) > 4096:
        fail(f"{where} exceeds the decoded byte bound")
    return tuple(decoded)


def validate_native_locator(value: Any, where: str = "native_locator") -> None:
    exact_keys(value, {"platform", "anchor_name", "anchor_id",
                       "segments_hex", "resolution"}, where)
    require_literal(value["platform"], (NATIVE_PLATFORM,), f"{where}.platform")
    require_slug(value["anchor_name"], f"{where}.anchor_name")
    require_h(value["anchor_id"], f"{where}.anchor_id")
    validate_native_rel_path({"segments_hex": value["segments_hex"]}, where,
                             allow_empty=True)
    require_literal(value["resolution"], (NATIVE_RESOLUTION,),
                    f"{where}.resolution")


def validate_native_observation(value: Any, where: str = "native_identity") -> None:
    keys = {"profile", "statx_mount_id", "device_major", "device_minor",
            "statfs_fsid_word0", "statfs_fsid_word1", "file_handle_type",
            "file_handle_bytes_hex", "inode", "file_type", "link_count",
            "native_mode"}
    exact_keys(value, keys, where)
    require_literal(value["profile"], (NATIVE_PROFILE,), f"{where}.profile")
    require_int(value["statx_mount_id"], f"{where}.statx_mount_id",
                maximum=2**64 - 1)
    for field in ("device_major", "device_minor", "statfs_fsid_word0",
                  "statfs_fsid_word1", "file_handle_type", "native_mode"):
        require_int(value[field], f"{where}.{field}", maximum=2**32 - 1)
    require_hex_bytes(value["file_handle_bytes_hex"],
                      f"{where}.file_handle_bytes_hex", maximum_bytes=256)
    require_int(value["inode"], f"{where}.inode", maximum=2**64 - 1)
    file_type = require_literal(value["file_type"], ("regular", "directory"),
                                f"{where}.file_type")
    require_int(value["link_count"], f"{where}.link_count",
                maximum=2**64 - 1)
    if value["link_count"] < 1:
        fail(f"{where}.link_count must be positive")
    expected_type_bits = 0o100000 if file_type == "regular" else 0o040000
    if value["native_mode"] & 0o170000 != expected_type_bits:
        fail(f"{where} native_mode type bits disagree with file_type")


def filesystem_id(observation: Mapping[str, Any]) -> str:
    validate_native_observation(observation)
    return domain_hash("council:linux-filesystem-id:v1", {
        "device_major": observation["device_major"],
        "device_minor": observation["device_minor"],
        "statfs_fsid_word0": observation["statfs_fsid_word0"],
        "statfs_fsid_word1": observation["statfs_fsid_word1"],
    })


def file_id(observation: Mapping[str, Any]) -> str:
    fsid = filesystem_id(observation)
    return domain_hash("council:linux-file-id:v1", {
        "file_handle_bytes_hex": observation["file_handle_bytes_hex"],
        "file_handle_type": observation["file_handle_type"],
        "file_type": observation["file_type"],
        "filesystem_id": fsid,
        "inode": observation["inode"],
    })


def locator_sha256(locator: Mapping[str, Any]) -> str:
    validate_native_locator(locator)
    return domain_hash("council:native-root-locator:v1", locator)


def validate_native_entry(value: Any, where: str) -> None:
    exact_keys(value, {"path", "native_identity", "filesystem_id", "file_id",
                       "content_sha256", "kind"}, where)
    validate_native_rel_path(value["path"], f"{where}.path")
    validate_native_observation(value["native_identity"],
                                f"{where}.native_identity")
    require_h(value["filesystem_id"], f"{where}.filesystem_id")
    require_h(value["file_id"], f"{where}.file_id")
    kind = require_literal(value["kind"], ("regular", "directory"),
                           f"{where}.kind")
    if value["native_identity"]["file_type"] != kind:
        fail(f"{where} kind disagrees with native observation")
    if value["filesystem_id"] != filesystem_id(value["native_identity"]) or \
            value["file_id"] != file_id(value["native_identity"]):
        fail(f"{where} native ids do not reconstruct")
    if kind == "regular":
        if value["native_identity"]["link_count"] != 1:
            fail(f"{where} regular entry must have exactly one native link")
        require_h(value["content_sha256"], f"{where}.content_sha256")
    elif value["content_sha256"] is not None:
        fail(f"{where}.content_sha256 must be null for a directory")


def _mode(value: Any, where: str, nullable: bool = True) -> str | None:
    if value is None and nullable:
        return None
    return require_literal(value, ("100644", "100755"), where)


CHANGE_KINDS = ("add", "delete", "modify", "mode", "rename")


def change_sort_key(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return (value["path"], value["kind"], value.get("rename_source") or "")


def validate_predicted_change(value: Any, where: str = "predicted_change") -> None:
    exact_keys(value, {"path", "kind", "rename_source", "blob_before",
                       "mode_before", "required"}, where)
    validate_path(value["path"], f"{where}.path")
    kind = require_literal(value["kind"], CHANGE_KINDS, f"{where}.kind")
    require_bool(value["required"], f"{where}.required")
    source = value["rename_source"]
    before = value["blob_before"]
    mode = value["mode_before"]
    if kind == "add":
        if source is not None or before is not None or mode is not None:
            fail(f"{where} add must have null before fields")
    else:
        require_h(before, f"{where}.blob_before")
        _mode(mode, f"{where}.mode_before", nullable=False)
        if kind == "rename":
            validate_path(source, f"{where}.rename_source")
            if source == value["path"]:
                fail(f"{where} rename cannot be a no-op")
        elif source is not None:
            fail(f"{where} only rename may name a source")


def validate_actual_change(value: Any, where: str = "actual_change") -> None:
    exact_keys(value, {"path", "kind", "rename_source", "blob_before",
                       "blob_after", "mode_before", "mode_after"}, where)
    validate_path(value["path"], f"{where}.path")
    kind = require_literal(value["kind"], CHANGE_KINDS, f"{where}.kind")
    source = value["rename_source"]
    before, after = value["blob_before"], value["blob_after"]
    mode_before, mode_after = value["mode_before"], value["mode_after"]
    if kind == "add":
        if source is not None or before is not None or mode_before is not None:
            fail(f"{where} add before fields must be null")
        require_h(after, f"{where}.blob_after")
        _mode(mode_after, f"{where}.mode_after", nullable=False)
    elif kind == "delete":
        if source is not None or after is not None or mode_after is not None:
            fail(f"{where} delete after fields must be null")
        require_h(before, f"{where}.blob_before")
        _mode(mode_before, f"{where}.mode_before", nullable=False)
    elif kind == "modify":
        if source is not None:
            fail(f"{where} modify source must be null")
        require_h(before, f"{where}.blob_before")
        require_h(after, f"{where}.blob_after")
        _mode(mode_before, f"{where}.mode_before", nullable=False)
        _mode(mode_after, f"{where}.mode_after", nullable=False)
        if before == after or mode_before != mode_after:
            fail(f"{where} modify must change only content")
    elif kind == "mode":
        if source is not None:
            fail(f"{where} mode source must be null")
        require_h(before, f"{where}.blob_before")
        require_h(after, f"{where}.blob_after")
        _mode(mode_before, f"{where}.mode_before", nullable=False)
        _mode(mode_after, f"{where}.mode_after", nullable=False)
        if before != after or mode_before == mode_after:
            fail(f"{where} mode must change only mode")
    else:
        validate_path(source, f"{where}.rename_source")
        require_h(before, f"{where}.blob_before")
        require_h(after, f"{where}.blob_after")
        _mode(mode_before, f"{where}.mode_before", nullable=False)
        _mode(mode_after, f"{where}.mode_after", nullable=False)
        if source == value["path"] or before != after or mode_before != mode_after:
            fail(f"{where} rename must be pure")


def validate_change_set(values: Any, where: str, *, predicted: bool,
                        nonempty: bool = False) -> list[dict]:
    require_sorted_unique(values, where, key=change_sort_key, nonempty=nonempty)
    destinations: list[str] = []
    sources: list[str] = []
    for index, value in enumerate(values):
        (validate_predicted_change if predicted else validate_actual_change)(
            value, f"{where}[{index}]")
        destinations.append(value["path"])
        if value["rename_source"] is not None:
            sources.append(value["rename_source"])
    require_unique_paths(destinations + sources, where)
    return values


def predicted_matches_actual(predicted: Mapping[str, Any],
                             actual: Mapping[str, Any]) -> bool:
    validate_predicted_change(predicted)
    validate_actual_change(actual)
    if (predicted["path"], predicted["kind"], predicted["rename_source"],
        predicted["blob_before"], predicted["mode_before"]) != \
       (actual["path"], actual["kind"], actual["rename_source"],
        actual["blob_before"], actual["mode_before"]):
        return False
    return True


def compute_record_id(schema_version: str, payload: Mapping[str, Any],
                      registry: Mapping[str, tuple[str, str]]) -> str:
    try:
        id_field, domain = registry[schema_version]
    except KeyError as exc:
        raise HSCValidationError(f"unknown schema_version {schema_version!r}") from exc
    del id_field
    return domain_hash(domain, {"schema_version": schema_version,
                                "payload": payload})


def compute_record_content_sha256(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HSCRequestBinding:
    target_commit: str
    root_path: str
    root_id: str
    root_sha256: str
    root_git_blob: str
    scope_path: str
    scope_id: str
    scope_sha256: str
    scope_git_blob: str


_BINDING_RE = re.compile(
    r"^HSC_V1 target_commit=([0-9a-f]{40}) root_path=([^ ]+) "
    r"root_id=([0-9a-f]{64}) root_sha256=([0-9a-f]{64}) "
    r"root_git_blob=([0-9a-f]{40}) scope_path=([^ ]+) "
    r"scope_id=([0-9a-f]{64}) scope_sha256=([0-9a-f]{64}) "
    r"scope_git_blob=([0-9a-f]{40})$")


def parse_hsc_request_binding(line: Any, *,
                              expected_request_id: str | None = None) \
        -> HSCRequestBinding:
    require_string(line, "HSC binding", max_bytes=4096)
    match = _BINDING_RE.fullmatch(line)
    if match is None:
        fail("malformed HSC_V1 request binding")
    values = match.groups()
    root_path = validate_path(values[1], "root_path")
    scope_path = validate_path(values[5], "scope_path")
    parts = root_path.split("/")
    # v1 fixes exactly artifacts/section-council/<request-id>/root.json —
    # exactly four segments, and the directory segment is a canonical
    # Council request id bound to the wrapper-supplied expectation.
    if len(parts) != 4 or parts[:2] != ["artifacts", "section-council"] or \
            parts[3] != "root.json":
        fail("root_path is not the fixed four-segment HSC root path")
    require_request_id(parts[2], "root_path request segment")
    if expected_request_id is not None and parts[2] != expected_request_id:
        fail("root_path request segment differs from the expected request id")
    if scope_path != "/".join(parts[:-1] + ["final-scope.json"]):
        fail("scope_path is not paired with root_path")
    return HSCRequestBinding(values[0], root_path, values[2], values[3],
                             values[4], scope_path, values[6], values[7],
                             values[8])


def strict_json_bytes(data: bytes, where: str = "JSON") -> Any:
    if not isinstance(data, bytes) or not data:
        fail(f"{where} must be nonempty bytes")
    try:
        text = data.decode("utf-8")
        value = json.loads(text, parse_constant=lambda token: fail(
            f"{where} contains non-finite {token}"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HSCValidationError(f"{where} is not strict UTF-8 JSON") from exc
    if text != canonical_json(value):
        fail(f"{where} bytes are not the sole canonical JSON encoding")
    return value


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            fail(f"duplicate JSON key {key!r}")
        result[key] = value
    return result
