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

  global.ColiseumPlayback = Object.freeze({
    adjacentEventPosition, adjacentPosition, clampPosition, delayForSpeed,
  });
})(globalThis);
