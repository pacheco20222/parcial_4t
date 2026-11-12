import { Reading } from '../../core/api/models';

export const CHART_LEFT = 54;
export const CHART_RIGHT = 846;
export const CHART_TOP = 30;
export const CHART_BOTTOM = 240;

export function validThresholds(watch: number | null, alert: number | null): boolean {
  return watch !== null && alert !== null && Number.isFinite(watch) && Number.isFinite(alert) && watch > 0 && watch < alert && alert <= 150;
}

export function axisMaximum(values: readonly (number | null | undefined)[]): number {
  const maximum = values.reduce<number>((max, value) => value != null && Number.isFinite(value) ? Math.max(max, value) : max, 0);
  return Math.max(10, Math.ceil(maximum * 1.1 / 10) * 10);
}

export function chartX(at: number, from: number, to: number): number {
  return CHART_LEFT + Math.max(0, Math.min(1, (at - from) / Math.max(1, to - from))) * (CHART_RIGHT - CHART_LEFT);
}

export function chartY(value: number, maximum: number): number {
  return CHART_BOTTOM - Math.max(0, Math.min(1, value / Math.max(1, maximum))) * (CHART_BOTTOM - CHART_TOP);
}

export function depthPath(rows: readonly Reading[], from: number, to: number, maximum: number): string {
  let previous = false;
  const commands: string[] = [];
  for (const row of rows) {
    const at = Date.parse(row.capturedAt);
    if (row.waterDepthCm == null || !Number.isFinite(row.waterDepthCm) || !Number.isFinite(at)) { previous = false; continue; }
    commands.push(`${previous ? 'L' : 'M'}${chartX(at, from, to)},${chartY(row.waterDepthCm, maximum)}`);
    previous = true;
  }
  return commands.join(' ');
}
