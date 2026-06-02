import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveNodePulseState } from '../src/lib/node-pulse.ts'

test('primary selected nodes resolve to the primary pulse state', () => {
  const state = resolveNodePulseState({
    nodeId: 'N-01',
    isSelected: true,
    isPrimarySelected: true,
  })

  assert.equal(state.pulseVariant, 'primary')
  assert.ok(state.pulseDelayMs <= 0)
})

test('non-primary selected nodes resolve to the selected pulse state', () => {
  const state = resolveNodePulseState({
    nodeId: 'N-02',
    isSelected: true,
    isPrimarySelected: false,
  })

  assert.equal(state.pulseVariant, 'selected')
  assert.ok(state.pulseDelayMs <= 0)
})

test('unselected nodes do not pulse', () => {
  const state = resolveNodePulseState({
    nodeId: 'N-03',
    isSelected: false,
    isPrimarySelected: false,
  })

  assert.equal(state.pulseVariant, 'none')
  assert.equal(state.pulseDelayMs, 0)
})

test('pulse delay is stable for the same node id and differs across node ids', () => {
  const first = resolveNodePulseState({
    nodeId: 'Node-A',
    isSelected: true,
    isPrimarySelected: false,
  })
  const second = resolveNodePulseState({
    nodeId: 'Node-A',
    isSelected: true,
    isPrimarySelected: false,
  })
  const different = resolveNodePulseState({
    nodeId: 'Node-B',
    isSelected: true,
    isPrimarySelected: false,
  })

  assert.equal(first.pulseDelayMs, second.pulseDelayMs)
  assert.notEqual(first.pulseDelayMs, different.pulseDelayMs)
})
