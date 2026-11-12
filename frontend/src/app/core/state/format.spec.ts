import { PublicPoint } from '../api/models';
import { formatAge, formatDepth, formatSla, statusSentence } from './format';
const point: PublicPoint = {id: 'P01', name: 'Centro', zone: 'Centro', lat: 20.97, lon: -89.62, status: 'Normal', simulated: true, waterDepthCm: 2, updatedAt: '2026-11-12T00:00:00Z', lastUpdateAgeSeconds: 0};
describe('status formatting', () => {
  it('formats depths consistently without inventing absent readings', () => {
    expect(formatDepth(0)).toBe('0.0 cm');
    expect(formatDepth(12.34)).toBe('12.3 cm');
    expect(formatDepth(null)).toBe('sin datos');
    expect(formatDepth(Number.NaN)).toBe('sin datos');
  });
  it('formats seconds/minutes without fabricating null data', () => { expect(formatAge(9)).toBe('hace 9 s'); expect(formatAge(180)).toBe('hace 3 min'); expect(formatAge(null)).toBe('sin datos'); expect(formatAge(-4)).toBe('hace 0 s'); });
  it('formats upcoming and overdue SLA', () => {
    const now = Date.parse('2026-11-12T00:00:00Z'); expect(formatSla('2026-11-12T01:05:00Z', now)).toBe('Quedan 1 h 05 min'); expect(formatSla('2026-11-11T23:42:00Z', now)).toBe('Vencida hace 18 min');
  });
  it('builds band sentence from real counts and freshest age', () => {
    const points: PublicPoint[] = [{...point, status: 'Alert'}, {...point, id: 'P02', status: 'Watch'}, {...point, id: 'P03', status: 'NoData', waterDepthCm: null}];
    expect(statusSentence(points, Date.parse('2026-11-12T00:00:09Z'))).toBe('1 punto en Alerta, 1 en Vigilancia, 1 sin datos — actualizado hace 9 s'); expect(statusSentence([])).toBe('Sin puntos disponibles — esperando datos');
  });
});
