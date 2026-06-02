import type { GraphEnvelope } from '../types/api-contract'

export type GraphMutation<TPayload> = (payload: TPayload) => Promise<GraphEnvelope>

export function useGraphMutations(applyGraphEnvelope: (envelope: GraphEnvelope) => void) {
  async function runGraphMutation<TPayload>(
    mutation: GraphMutation<TPayload>,
    payload: TPayload,
  ): Promise<GraphEnvelope> {
    const envelope = await mutation(payload)
    applyGraphEnvelope(envelope)
    return envelope
  }

  return {
    runGraphMutation,
  }
}
