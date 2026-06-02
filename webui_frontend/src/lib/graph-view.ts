export type GraphPoint = {
  x: number
  y: number
}

export function rotatePointByQuadrants(point: GraphPoint, quadrants: number): GraphPoint {
  const normalized = ((Math.round(quadrants) % 4) + 4) % 4
  switch (normalized) {
    case 1:
      return { x: -point.y, y: point.x }
    case 2:
      return { x: -point.x, y: -point.y }
    case 3:
      return { x: point.y, y: -point.x }
    default:
      return { x: point.x, y: point.y }
  }
}

export function transformGraphPoint(
  point: GraphPoint,
  options: { rotationQuadrants: number; flipHorizontal: boolean; flipVertical: boolean },
): GraphPoint {
  const rotated = rotatePointByQuadrants(point, options.rotationQuadrants)
  return {
    x: options.flipHorizontal ? -rotated.x : rotated.x,
    y: options.flipVertical ? -rotated.y : rotated.y,
  }
}
