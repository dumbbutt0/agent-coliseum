"use strict";

(function installPlayback(global) {
  function boundedInteger(value, fallback = 0) {
    const numeric = Number(value);
    return Number.isInteger(numeric) ? numeric : fallback;
  }

  function clampPosition(value, lastPosition) {
    const last = Math.max(0, boundedInteger(lastPosition));
    return Math.max(0, Math.min(last, boundedInteger(value)));
  }

  function adjacentPosition(current, lastPosition, direction) {
    const delta = direction < 0 ? -1 : 1;
    return clampPosition(clampPosition(current, lastPosition) + delta, lastPosition);
  }

  function adjacentEventPosition(events, current, direction) {
    const positions = [...new Set(events.map((event) => boundedInteger(event.position, -1))
      .filter((position) => position >= 0))].sort((left, right) => left - right);
    if (direction < 0) return positions.slice().reverse().find((position) => position < current);
    return positions.find((position) => position > current);
  }

  function delayForSpeed(speed) {
    const numeric = Number(speed);
    return 800 / ([0.5, 1, 2, 4].includes(numeric) ? numeric : 1);
  }

  function transition(current, lastPosition, action) {
    const position = clampPosition(current?.position, lastPosition);
    const playing = current?.playing === true;
    if (!action || typeof action.type !== "string") return {position, playing};
    if (action.type === "pause") return {position, playing: false};
    if (action.type === "seek") {
      return {position: clampPosition(action.position, lastPosition), playing};
    }
    if (action.type === "play") {
      return {position: position >= lastPosition ? 0 : position, playing: true};
    }
    if (action.type === "tick") {
      if (!playing) return {position, playing: false};
      const next = adjacentPosition(position, lastPosition, 1);
      return {position: next, playing: next < lastPosition};
    }
    return {position, playing};
  }

  global.ColiseumPlayback = Object.freeze({
    adjacentEventPosition, adjacentPosition, clampPosition, delayForSpeed,
    transition,
  });
})(globalThis);
