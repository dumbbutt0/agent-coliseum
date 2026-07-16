"""Deterministic conflict, dispatch, dependency, and staleness calculations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .core import (HSCValidationError, path_collision_key, require_h,
                   require_int, require_slug, validate_path)


@dataclass(frozen=True)
class WorkAccess:
    work_item_id: str
    section_id: str
    priority: int
    dependency_work_item_ids: tuple[str, ...]
    write_paths: tuple[str, ...]
    read_paths: tuple[str, ...]
    immutable_read_paths: tuple[str, ...] = ()
    shared_interfaces: tuple[tuple[str, int, str], ...] = ()
    stale: bool = False
    blocked: bool = False
    unknown: bool = False

    def __post_init__(self) -> None:
        require_h(self.work_item_id, "work_item_id")
        require_slug(self.section_id, "section_id")
        require_int(self.priority, "priority")
        for dependency in self.dependency_work_item_ids:
            require_h(dependency, "dependency_work_item_id")
        if len(self.dependency_work_item_ids) != \
                len(set(self.dependency_work_item_ids)):
            raise HSCValidationError("duplicate dependency_work_item_id")
        for path in self.write_paths + self.read_paths + self.immutable_read_paths:
            validate_path(path)
        if not set(self.immutable_read_paths) <= set(self.read_paths):
            raise HSCValidationError("immutable reads must be a subset of reads")
        _keyed(self.write_paths)
        _keyed(self.read_paths)
        interfaces = {}
        for interface in self.shared_interfaces:
            if not isinstance(interface, tuple) or len(interface) != 3:
                raise HSCValidationError("shared interface must be a typed triple")
            name, version, digest = interface
            require_slug(name, "shared_interface.interface_id")
            require_int(version, "shared_interface.version", minimum=1)
            require_h(digest, "shared_interface.digest")
            if name in interfaces:
                raise HSCValidationError("duplicate shared interface identity")
            interfaces[name] = (version, digest)


@dataclass(frozen=True)
class ConflictResult:
    conflict: bool
    uncertain: bool
    reasons: tuple[str, ...]


def classify_conflict(left: WorkAccess, right: WorkAccess, *,
                      satisfied_dependencies: Iterable[str] = ()) -> ConflictResult:
    """Apply the frozen HSC v1 conflict relation, failing closed on unknowns."""
    reasons: list[str] = []
    uncertain = left.unknown or right.unknown
    if uncertain:
        reasons.append("unclassified access")
    if left.stale or right.stale:
        reasons.append("stale work item")
    if left.blocked or right.blocked:
        reasons.append("blocked work item")
    lwrite = _keyed(left.write_paths)
    rwrite = _keyed(right.write_paths)
    lread = _keyed(left.read_paths)
    rread = _keyed(right.read_paths)
    limmutable = set(_keyed(left.immutable_read_paths))
    rimmutable = set(_keyed(right.immutable_read_paths))
    if set(lwrite) & set(rwrite):
        reasons.append("write/write overlap")
    if any(key in rread and key not in rimmutable for key in lwrite):
        reasons.append("left write/right mutable read overlap")
    if any(key in lread and key not in limmutable for key in rwrite):
        reasons.append("right write/left mutable read overlap")
    left_interfaces = {name: (version, digest)
                       for name, version, digest in left.shared_interfaces}
    right_interfaces = {name: (version, digest)
                        for name, version, digest in right.shared_interfaces}
    for key in set(left_interfaces) & set(right_interfaces):
        if left_interfaces[key] != right_interfaces[key]:
            reasons.append("shared interface version/digest mismatch")
    satisfied = set(satisfied_dependencies)
    unmet = (set(left.dependency_work_item_ids) |
             set(right.dependency_work_item_ids)) - satisfied
    if unmet:
        reasons.append("dependency closure unsatisfied")
    return ConflictResult(bool(reasons), uncertain, tuple(sorted(set(reasons))))


def dependency_closure(graph: Mapping[str, Iterable[str]]) -> dict[str, frozenset[str]]:
    """Return exact transitive prerequisites and reject unknowns/cycles."""
    normalized = {node: tuple(dependencies)
                  for node, dependencies in graph.items()}
    nodes = set(normalized)
    for node, dependencies in normalized.items():
        require_h(node, "work_item_id")
        unknown = set(dependencies) - nodes
        if unknown:
            raise HSCValidationError(f"unknown dependencies for {node}: {sorted(unknown)}")
    visiting: set[str] = set()
    done: dict[str, frozenset[str]] = {}
    def visit(node: str) -> frozenset[str]:
        if node in visiting:
            raise HSCValidationError("dependency graph contains a cycle")
        if node in done:
            return done[node]
        visiting.add(node)
        result: set[str] = set()
        for dependency in normalized[node]:
            result.add(dependency)
            result.update(visit(dependency))
        visiting.remove(node)
        done[node] = frozenset(result)
        return done[node]
    for node in sorted(nodes):
        visit(node)
    return done


def dispatch_order(items: Iterable[WorkAccess]) -> tuple[str, ...]:
    """Canonical ``(depth, priority, section_id, work_item_id)`` order."""
    item_list = tuple(items)
    by_id = {item.work_item_id: item for item in item_list}
    if len(by_id) != len(item_list):
        raise HSCValidationError("duplicate work_item_id")
    graph = {item.work_item_id: item.dependency_work_item_ids
             for item in item_list}
    closure = dependency_closure(graph)
    depths: dict[str, int] = {}
    def depth(item_id: str) -> int:
        if item_id not in depths:
            depths[item_id] = 0 if not graph[item_id] else 1 + max(
                depth(parent) for parent in graph[item_id])
        return depths[item_id]
    eligible = [item for item in item_list
                if not item.stale and not item.blocked and not item.unknown]
    return tuple(item.work_item_id for item in sorted(
        eligible,
        key=lambda item: (depth(item.work_item_id), item.priority,
                          item.section_id, item.work_item_id)))


def stale_work_items(graph: Mapping[str, Iterable[str]],
                     staleness_inputs: Mapping[str, Iterable[str]],
                     changed_input_ids: Iterable[str]) -> frozenset[str]:
    """Invalidate directly affected work plus only its downstream dependents."""
    closure = dependency_closure(graph)
    changed = set(changed_input_ids)
    direct = {item for item, inputs in staleness_inputs.items()
              if set(inputs) & changed}
    if not direct <= set(graph) or set(staleness_inputs) != set(graph):
        raise HSCValidationError("staleness input membership differs from graph")
    stale = set(direct)
    for item, ancestors in closure.items():
        if ancestors & direct:
            stale.add(item)
    return frozenset(stale)


def _keyed(paths: Iterable[str]) -> dict[tuple[str, ...], str]:
    result: dict[tuple[str, ...], str] = {}
    for path in paths:
        key = path_collision_key(path)
        if key in result and result[key] != path:
            raise HSCValidationError("case/NFC path ambiguity")
        result[key] = path
    return result
