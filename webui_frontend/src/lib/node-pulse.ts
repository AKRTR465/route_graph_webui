export type NodePulseVariant = 'none' | 'selected' | 'primary'

export interface NodePulseInput {
  nodeId: string
  isSelected: boolean
  isPrimarySelected: boolean
}

export interface NodePulseState {
  pulseVariant: NodePulseVariant
  pulseDelayMs: number
}

const PULSE_DELAY_SPREAD_MS: Record<Exclude<NodePulseVariant, 'none'>, number> = {
  selected: 2600,
  primary: 2300,
}

function hashNodeId(nodeId: string) {
  let hash = 0
  for (const character of nodeId) {
    hash = (hash * 33 + character.charCodeAt(0)) % 2147483647
  }
  return Math.abs(hash)
}

export function resolveNodePulseState(input: NodePulseInput): NodePulseState {
  if (input.isPrimarySelected) {
    return {
      pulseVariant: 'primary',
      pulseDelayMs: -(hashNodeId(input.nodeId) % PULSE_DELAY_SPREAD_MS.primary),
    }
  }

  if (input.isSelected) {
    return {
      pulseVariant: 'selected',
      pulseDelayMs: -(hashNodeId(input.nodeId) % PULSE_DELAY_SPREAD_MS.selected),
    }
  }

  return {
    pulseVariant: 'none',
    pulseDelayMs: 0,
  }
}
