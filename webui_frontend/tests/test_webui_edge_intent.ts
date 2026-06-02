import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { resolveEdgeCreationIntent } from '../src/lib/edge-intent.ts'
import {
  EDGE_KIND_BRIDGE,
  EDGE_KIND_GROUP,
} from '../src/types/graph-meta.ts'

test('edge intent infers group bridge and fallback creation metadata', () => {
const grouping = {
    nodeGroupLookup: new Map<string, string>([
      ['A', '#FF0000'],
      ['B', '#FF0000'],
      ['C', '#00AAFF'],
    ]),
    conflictingNodeIds: new Set<string>(),
  }

  assert.deepEqual(
    resolveEdgeCreationIntent('A', 'B', grouping, null, {
      group: EDGE_KIND_GROUP,
      bridge: EDGE_KIND_BRIDGE,
    }),
    { edge_kind: EDGE_KIND_GROUP, group_color: '#FF0000' },
  )
  assert.deepEqual(
    resolveEdgeCreationIntent('A', 'C', grouping, null, {
      group: EDGE_KIND_GROUP,
      bridge: EDGE_KIND_BRIDGE,
    }),
    { edge_kind: EDGE_KIND_BRIDGE, group_color: null },
  )
  assert.deepEqual(
    resolveEdgeCreationIntent('A', 'D', grouping, null, {
      group: EDGE_KIND_GROUP,
      bridge: EDGE_KIND_BRIDGE,
    }),
    { edge_kind: EDGE_KIND_GROUP, group_color: '#FF0000' },
  )
  assert.deepEqual(
    resolveEdgeCreationIntent('D', 'E', grouping, '#334155', {
      group: EDGE_KIND_GROUP,
      bridge: EDGE_KIND_BRIDGE,
    }),
    { edge_kind: EDGE_KIND_GROUP, group_color: '#334155' },
  )
})

test('edge intent rejects conflicting or uncolored ungrouped nodes', () => {
  assert.throws(
    () => resolveEdgeCreationIntent(
      'A',
      'B',
      {
        nodeGroupLookup: new Map<string, string>(),
        conflictingNodeIds: new Set<string>(['A']),
      },
      '#334155',
      { group: EDGE_KIND_GROUP, bridge: EDGE_KIND_BRIDGE },
    ),
    /归属多个颜色组/,
  )
  assert.throws(
    () => resolveEdgeCreationIntent(
      'A',
      'B',
      {
        nodeGroupLookup: new Map<string, string>(),
        conflictingNodeIds: new Set<string>(),
      },
      null,
      { group: EDGE_KIND_GROUP, bridge: EDGE_KIND_BRIDGE },
    ),
    /尚未归组/,
  )
})

test('vite dev server defaults to local-only host unless explicitly opened', () => {
  const viteConfig = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8')
  assert.match(viteConfig, /'127\.0\.0\.1'/)
  assert.match(viteConfig, /ROUTE_GRAPH_WEBUI_ALLOW_LAN/)
  assert.match(viteConfig, /ROUTE_GRAPH_WEBUI_VITE_HOST/)
})
