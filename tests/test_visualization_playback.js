"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
require("../coliseum/textlab/visualization/static/playback.js");

const playback = globalThis.ColiseumPlayback;

test("exact seek and forward/backward stepping clamp to recorded positions", () => {
  assert.equal(playback.clampPosition(3, 8), 3);
  assert.equal(playback.clampPosition(-9, 8), 0);
  assert.equal(playback.clampPosition(19, 8), 8);
  assert.equal(playback.adjacentPosition(3, 8, 1), 4);
  assert.equal(playback.adjacentPosition(3, 8, -1), 2);
  assert.equal(playback.adjacentPosition(0, 8, -1), 0);
  assert.equal(playback.adjacentPosition(8, 8, 1), 8);
});

test("event jumps use stable unique recorded positions", () => {
  const events = [{position: 5}, {position: 2}, {position: 5}, {position: 9}];
  assert.equal(playback.adjacentEventPosition(events, 5, 1), 9);
  assert.equal(playback.adjacentEventPosition(events, 5, -1), 2);
  assert.equal(playback.adjacentEventPosition(events, 9, 1), undefined);
});

test("playback speed changes timing only", () => {
  assert.equal(playback.delayForSpeed(0.5), 1600);
  assert.equal(playback.delayForSpeed(1), 800);
  assert.equal(playback.delayForSpeed(2), 400);
  assert.equal(playback.delayForSpeed(4), 200);
  assert.equal(playback.delayForSpeed(999), 800);
});

test("pause, resume, seek, and terminal tick preserve exact state", () => {
  let state = playback.transition({position: 2, playing: false}, 4, {type: "play"});
  assert.deepEqual(state, {position: 2, playing: true});
  state = playback.transition(state, 4, {type: "tick"});
  assert.deepEqual(state, {position: 3, playing: true});
  state = playback.transition(state, 4, {type: "pause"});
  assert.deepEqual(state, {position: 3, playing: false});
  assert.deepEqual(playback.transition(state, 4, {type: "tick"}), state);
  state = playback.transition(state, 4, {type: "seek", position: 4});
  state = playback.transition(state, 4, {type: "play"});
  assert.deepEqual(state, {position: 0, playing: true});
  state = playback.transition({position: 3, playing: true}, 4, {type: "tick"});
  assert.deepEqual(state, {position: 4, playing: false});
});
