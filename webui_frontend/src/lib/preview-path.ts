export type PreviewPoint = {
  x: number
  y: number
}

export function buildPreviewPathSegments(points: PreviewPoint[]): string[] {
  if (points.length < 2) {
    return []
  }
  const segments: string[] = []
  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1]
    const end = points[index]
    segments.push(`M ${start.x} ${start.y} L ${end.x} ${end.y}`)
  }
  return segments
}

export function computeChevronGlyph(
  start: PreviewPoint,
  end: PreviewPoint,
  ratio: number,
): { x: number; y: number; angle: number } {
  const clampedRatio = Math.max(0, Math.min(1, ratio))
  return {
    x: start.x + (end.x - start.x) * clampedRatio,
    y: start.y + (end.y - start.y) * clampedRatio,
    angle: (Math.atan2(end.y - start.y, end.x - start.x) * 180) / Math.PI,
  }
}
