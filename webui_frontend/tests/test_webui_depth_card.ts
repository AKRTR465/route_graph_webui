import test from 'node:test'
import assert from 'node:assert/strict'

import { computeDepthCardState } from '../src/lib/depth-card.ts'

const rect = {
  left: 100,
  top: 50,
  width: 240,
  height: 120,
}

test('card center resolves to zero rotation', () => {
  const state = computeDepthCardState(
    rect,
    {
      clientX: rect.left + rect.width / 2,
      clientY: rect.top + rect.height / 2,
    },
    { mode: 'tracking' },
  )

  assert.equal(state.rotateXDeg, 0)
  assert.equal(state.rotateYDeg, 0)
  assert.equal(state.liftPx, 4)
})

test('card corners are clamped to the max tilt range', () => {
  const topLeft = computeDepthCardState(
    rect,
    {
      clientX: rect.left,
      clientY: rect.top,
    },
    { mode: 'tracking' },
  )
  const bottomRight = computeDepthCardState(
    rect,
    {
      clientX: rect.left + rect.width,
      clientY: rect.top + rect.height,
    },
    { mode: 'tracking' },
  )

  assert.equal(topLeft.rotateXDeg, 3.5)
  assert.equal(topLeft.rotateYDeg, -3.5)
  assert.equal(bottomRight.rotateXDeg, -3.5)
  assert.equal(bottomRight.rotateYDeg, 3.5)
})

test('pointer coordinates outside the card bounds are clamped before mapping', () => {
  const state = computeDepthCardState(
    rect,
    {
      clientX: rect.left + rect.width * 5,
      clientY: rect.top - rect.height * 5,
    },
    { mode: 'tracking' },
  )

  assert.equal(state.rotateXDeg, 3.5)
  assert.equal(state.rotateYDeg, 3.5)
})

test('shadow-only mode keeps rotation at zero', () => {
  const state = computeDepthCardState(
    rect,
    {
      clientX: rect.left,
      clientY: rect.top,
    },
    { mode: 'shadow-only' },
  )

  assert.equal(state.rotateXDeg, 0)
  assert.equal(state.rotateYDeg, 0)
  assert.equal(state.liftPx, 2)
})

test('subtle tracking mode reduces the wobble amplitude', () => {
  const state = computeDepthCardState(
    rect,
    {
      clientX: rect.left,
      clientY: rect.top,
    },
    { mode: 'tracking', intensity: 'subtle' },
  )

  assert.equal(state.rotateXDeg, 2.4)
  assert.equal(state.rotateYDeg, -2.4)
  assert.equal(state.liftPx, 3)
  assert.equal(state.shadowXpx, -8)
  assert.equal(state.shadowYpx, 14)
})

test('tracking scale can reduce motion for a single card', () => {
  const state = computeDepthCardState(
    rect,
    {
      clientX: rect.left,
      clientY: rect.top,
    },
    { mode: 'tracking', scale: 0.2 },
  )

  assert.equal(state.rotateXDeg, 0.7)
  assert.equal(state.rotateYDeg, -0.7)
  assert.equal(state.liftPx, 0.8)
  assert.equal(state.shadowXpx, -2.4)
  assert.equal(state.shadowYpx, 3.2)
})
