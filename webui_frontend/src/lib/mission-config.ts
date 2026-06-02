import type { MissionConfigPayload } from '../types/api-contract'

export type ExportFormLike = {
  stepDistance: string
  fps: string
  altitudeMode: 'fixed' | 'follow_nodes'
  fixedZ: string
  altitudeOffset: string
  takeoffLandingRelativeZ: string
  takeoffLandingStepDistance: string
  nodeSampleRadius: string
  randomSeed: string
  turnSmoothingEnabled: boolean
  cornerRadius: string
  smallTurnYawBlendThresholdDeg: string
  cornerMinAngleDeg: string
  uTurnThresholdDeg: string
  uTurnTransitionDistance: string
  cornerMaxYawStepDeg: string
  uTurnPivotYawStepDeg: string
}

export type SmoothingDefaults = {
  cornerRadius: string
  smallTurnYawBlendThresholdDeg: string
  cornerMinAngleDeg: string
  uTurnThresholdDeg: string
  uTurnTransitionDistance: string
  cornerMaxYawStepDeg: string
  uTurnPivotYawStepDeg: string
}

export function parseOptionalNumber(rawValue: string, label: string): number | null {
  const text = rawValue.trim()
  if (!text) {
    return null
  }
  const value = Number(text)
  if (!Number.isFinite(value)) {
    throw new Error(`${label} 必须是数字`)
  }
  return value
}

export function parseRequiredPositiveNumber(
  rawValue: string,
  label: string,
  { allowZero = false }: { allowZero?: boolean } = {},
): number {
  const value = parseOptionalNumber(rawValue, label)
  if (value == null) {
    throw new Error(`${label} 不能为空`)
  }
  if ((!allowZero && value <= 0) || (allowZero && value < 0)) {
    throw new Error(`${label} 必须${allowZero ? '大于等于 0' : '大于 0'}`)
  }
  return value
}

export function parseOptionalInteger(
  rawValue: string,
  label: string,
  { allowZero = false }: { allowZero?: boolean } = {},
): number | null {
  const text = rawValue.trim()
  if (!text) {
    return null
  }
  const value = Number(text)
  if (!Number.isInteger(value)) {
    throw new Error(`${label} 必须是整数`)
  }
  if ((!allowZero && value <= 0) || (allowZero && value < 0)) {
    throw new Error(`${label} 必须${allowZero ? '大于等于 0' : '大于 0'}`)
  }
  return value
}

export function parseRequiredInteger(
  rawValue: string,
  label: string,
  { allowZero = false }: { allowZero?: boolean } = {},
): number {
  const value = parseOptionalInteger(rawValue, label, { allowZero })
  if (value == null) {
    throw new Error(`${label} 不能为空`)
  }
  return value
}

export function coerceNumberOrFallback(rawValue: string, fallback: number): number {
  const value = Number(rawValue.trim())
  return Number.isFinite(value) ? value : fallback
}

export function buildMissionGeometryInputsSnapshot(exportForm: ExportFormLike) {
  return {
    step_distance: exportForm.stepDistance,
    fps: exportForm.fps,
    altitude_mode: exportForm.altitudeMode,
    fixed_z: exportForm.fixedZ,
    altitude_offset: exportForm.altitudeOffset,
    takeoff_landing_relative_z: exportForm.takeoffLandingRelativeZ,
    takeoff_landing_step_distance: exportForm.takeoffLandingStepDistance,
    node_sample_radius: exportForm.nodeSampleRadius,
    random_seed: exportForm.randomSeed,
    turn_smoothing_enabled: exportForm.turnSmoothingEnabled,
    corner_radius: exportForm.cornerRadius,
    small_turn_yaw_blend_threshold_deg: exportForm.smallTurnYawBlendThresholdDeg,
    corner_min_angle_deg: exportForm.cornerMinAngleDeg,
    u_turn_threshold_deg: exportForm.uTurnThresholdDeg,
    u_turn_transition_distance: exportForm.uTurnTransitionDistance,
    corner_max_yaw_step_deg: exportForm.cornerMaxYawStepDeg,
    u_turn_pivot_yaw_step_deg: exportForm.uTurnPivotYawStepDeg,
  }
}

export function buildMissionConfigRequestPayload(
  exportForm: ExportFormLike,
  smoothingDefaults: SmoothingDefaults,
): MissionConfigPayload {
  const smoothingEnabled = exportForm.turnSmoothingEnabled

  return {
    step_distance: parseRequiredPositiveNumber(exportForm.stepDistance, '步长'),
    fps: parseRequiredPositiveNumber(exportForm.fps, '帧率'),
    altitude_mode: exportForm.altitudeMode,
    fixed_z:
      exportForm.altitudeMode === 'fixed'
        ? parseOptionalNumber(exportForm.fixedZ, '固定 Z')
        : null,
    altitude_offset: parseRequiredPositiveNumber(exportForm.altitudeOffset, '高度偏移', {
      allowZero: true,
    }),
    takeoff_landing_relative_z: parseOptionalNumber(
      exportForm.takeoffLandingRelativeZ,
      '起降相对高度',
    ),
    takeoff_landing_step_distance: parseOptionalNumber(
      exportForm.takeoffLandingStepDistance,
      '起降步长',
    ),
    node_sample_radius: parseRequiredPositiveNumber(exportForm.nodeSampleRadius, '节点采样半径', {
      allowZero: true,
    }),
    random_seed: parseOptionalInteger(exportForm.randomSeed, '随机种子', {
      allowZero: true,
    }),
    turn_smoothing_enabled: smoothingEnabled,
    corner_radius: smoothingEnabled
      ? parseRequiredPositiveNumber(exportForm.cornerRadius, '拐角半径')
      : coerceNumberOrFallback(exportForm.cornerRadius, Number(smoothingDefaults.cornerRadius)),
    small_turn_yaw_blend_threshold_deg: smoothingEnabled
      ? parseRequiredPositiveNumber(
          exportForm.smallTurnYawBlendThresholdDeg,
          '小角度偏航混合阈值',
          { allowZero: true },
        )
      : coerceNumberOrFallback(
          exportForm.smallTurnYawBlendThresholdDeg,
          Number(smoothingDefaults.smallTurnYawBlendThresholdDeg),
        ),
    corner_min_angle_deg: smoothingEnabled
      ? parseRequiredPositiveNumber(exportForm.cornerMinAngleDeg, '拐角最小角度', {
          allowZero: true,
        })
      : coerceNumberOrFallback(exportForm.cornerMinAngleDeg, Number(smoothingDefaults.cornerMinAngleDeg)),
    u_turn_threshold_deg: smoothingEnabled
      ? parseRequiredPositiveNumber(exportForm.uTurnThresholdDeg, 'U 型掉头阈值')
      : coerceNumberOrFallback(exportForm.uTurnThresholdDeg, Number(smoothingDefaults.uTurnThresholdDeg)),
    u_turn_transition_distance: smoothingEnabled
      ? parseRequiredPositiveNumber(exportForm.uTurnTransitionDistance, 'U 型掉头过渡距离')
      : coerceNumberOrFallback(
          exportForm.uTurnTransitionDistance,
          Number(smoothingDefaults.uTurnTransitionDistance),
        ),
    corner_max_yaw_step_deg: smoothingEnabled
      ? parseRequiredPositiveNumber(exportForm.cornerMaxYawStepDeg, '拐角最大偏航步进')
      : coerceNumberOrFallback(exportForm.cornerMaxYawStepDeg, Number(smoothingDefaults.cornerMaxYawStepDeg)),
    u_turn_pivot_yaw_step_deg: smoothingEnabled
      ? parseRequiredPositiveNumber(exportForm.uTurnPivotYawStepDeg, 'U 型掉头枢轴偏航步进')
      : coerceNumberOrFallback(
          exportForm.uTurnPivotYawStepDeg,
          Number(smoothingDefaults.uTurnPivotYawStepDeg),
        ),
  }
}
