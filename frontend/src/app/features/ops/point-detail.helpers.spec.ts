import { describe, expect, it } from 'vitest';
import { axisMaximum, chartY, depthPath, validThresholds } from './point-detail.helpers';

describe('point chart scales', () => {
  it('keeps an empty or zero series readable and includes thresholds', () => {
    expect(axisMaximum([])).toBe(10);
    expect(axisMaximum([null, 0, Number.NaN])).toBe(10);
    expect(axisMaximum([12, 70])).toBe(80);
  });
  it('maps zero to baseline, caps values and keeps all coordinates finite', () => {
    expect(chartY(0, 50)).toBe(240);
    expect(chartY(50, 50)).toBe(30);
    expect(chartY(100, 50)).toBe(30);
    expect(chartY(-2, 50)).toBe(240);
  });
  it('breaks the depth line at missing data rather than drawing zero', () => {
    const rows = [
      {capturedAt: '2026-11-12T00:00:00Z', waterDepthCm: 10, rainMm5min: 0},
      {capturedAt: '2026-11-12T00:01:00Z', waterDepthCm: null, rainMm5min: 0},
      {capturedAt: '2026-11-12T00:02:00Z', waterDepthCm: 20, rainMm5min: 0},
    ];
    expect(depthPath(rows, Date.parse(rows[0].capturedAt), Date.parse(rows[2].capturedAt), 50)).toBe('M54,198 M846,156');
  });
});

describe('threshold validation', () => {
  it('accepts fractional values and the 150 cm upper bound', () => {
    expect(validThresholds(.5, 150)).toBe(true);
    expect(validThresholds(20, 40)).toBe(true);
  });
  it('rejects blank, non-finite, unordered and out-of-range thresholds', () => {
    for (const [watch, alert] of [[0, 20], [-1, 20], [20, 20], [30, 20], [20, 150.1], [null, 30], [20, null], [NaN, 30], [20, Infinity]]) {
      expect(validThresholds(watch, alert)).toBe(false);
    }
  });
});
