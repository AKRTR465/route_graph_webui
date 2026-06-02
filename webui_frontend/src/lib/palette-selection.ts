export function normalizeOptionalHexColor(value: unknown): string | null {
  const text = String(value ?? '').trim()
  if (!text) {
    return null
  }
  const normalized = text.startsWith('#') ? text.toUpperCase() : `#${text.toUpperCase()}`
  return /^#[0-9A-F]{6}$/.test(normalized) ? normalized : null
}

function normalizeColorSequence(colors: string[]): string[] {
  const normalizedColors: string[] = []
  const seen = new Set<string>()
  for (const color of colors) {
    const normalizedColor = normalizeOptionalHexColor(color)
    if (!normalizedColor || seen.has(normalizedColor)) {
      continue
    }
    seen.add(normalizedColor)
    normalizedColors.push(normalizedColor)
  }
  return normalizedColors
}

export function resolvePaletteBrushColor(
  usedColors: string[],
  sessionColors: string[],
  currentColor: string | null,
  preferredColor: string | null,
): string | null {
  const normalizedUsedColors = normalizeColorSequence(usedColors)
  const normalizedSessionColors = normalizeColorSequence(sessionColors).filter(
    (color) => !normalizedUsedColors.includes(color),
  )
  const availableColors = [...normalizedUsedColors, ...normalizedSessionColors]
  const current = normalizeOptionalHexColor(currentColor)
  if (current && availableColors.includes(current)) {
    return current
  }
  const preferred = normalizeOptionalHexColor(preferredColor)
  if (preferred && availableColors.includes(preferred)) {
    return preferred
  }
  return availableColors[0] ?? null
}

export type PaletteSelectionResult = {
  paintColor: string | null
  activeGroupColor: string | null
}

export function resolvePaletteSelectionResult(
  usedColors: string[],
  sessionColors: string[],
  requestedColor: string | null,
  activeGroupColor: string | null,
): PaletteSelectionResult {
  const normalizedActiveGroupColor = normalizeOptionalHexColor(activeGroupColor)
  const nextPaintColor = resolvePaletteBrushColor(
    usedColors,
    sessionColors,
    requestedColor,
    normalizedActiveGroupColor,
  )
  const normalizedUsedColors = normalizeColorSequence(usedColors)
  const nextActiveGroupColor =
    nextPaintColor && normalizedUsedColors.includes(nextPaintColor)
      ? nextPaintColor
      : normalizedActiveGroupColor
  return {
    paintColor: resolvePaletteBrushColor(
      usedColors,
      sessionColors,
      nextPaintColor,
      nextActiveGroupColor,
    ),
    activeGroupColor: nextActiveGroupColor,
  }
}
