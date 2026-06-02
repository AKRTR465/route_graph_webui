import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeOptionalHexColor,
  resolvePaletteBrushColor,
  resolvePaletteSelectionResult,
} from '../src/lib/palette-selection.ts'

test('selecting a used group color syncs the active group highlight', () => {
  const result = resolvePaletteSelectionResult(
    ['#857efa', '#BDA339'],
    ['#123456'],
    '#857efa',
    null,
  )

  assert.equal(result.paintColor, '#857EFA')
  assert.equal(result.activeGroupColor, '#857EFA')
})

test('selecting a session palette color keeps the current active group', () => {
  const result = resolvePaletteSelectionResult(
    ['#857EFA', '#BDA339'],
    ['#123456'],
    '#123456',
    '#BDA339',
  )

  assert.equal(result.paintColor, '#123456')
  assert.equal(result.activeGroupColor, '#BDA339')
})

test('missing requested colors fall back to the active group color', () => {
  const result = resolvePaletteSelectionResult(
    ['#857EFA', '#BDA339'],
    ['#123456'],
    '#999999',
    '#bda339',
  )

  assert.equal(result.paintColor, '#BDA339')
  assert.equal(result.activeGroupColor, '#BDA339')
})

test('palette brush resolution normalizes and deduplicates colors', () => {
  assert.equal(
    resolvePaletteBrushColor(
      ['#857efa', '#857EFA'],
      ['123456', '#123456'],
      '#123456',
      '#857efa',
    ),
    '#123456',
  )
  assert.equal(normalizeOptionalHexColor('857efa'), '#857EFA')
  assert.equal(normalizeOptionalHexColor('not-a-color'), null)
})
