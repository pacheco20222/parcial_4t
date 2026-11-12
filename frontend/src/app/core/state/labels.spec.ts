import { PublicPoint } from '../api/models';
import { alertLevelLabel, displayText, orderStatusLabel, pointLabel, priorityLabel, reportStatusLabel } from './labels';
const points = [{id: 'P05', zone: 'Sur', name: 'Punto simulado P05 — Sur'}] as PublicPoint[];
describe('Spanish display labels', () => {
  it('uses point id and zone without duplicated simulated names', () => {
    expect(pointLabel(points[0])).toBe('P05 Sur');
  });
  it('translates known backend messages and keeps unknown content', () => {
    expect(displayText('Water depth threshold exceeded')).toBe('Tirante superó el umbral');
    expect(displayText('Telemetry unavailable')).toBe('Sin datos de telemetría');
    expect(displayText('Flood response: Punto simulado P05 — Sur', points)).toBe('Atención de inundación: P05 Sur');
    expect(displayText('Inspect device: Punto simulado P05 — Sur', points)).toBe('Revisar sensor: P05 Sur');
    expect(displayText('Inspect device', points, 'P05')).toBe('Revisar sensor: P05 Sur');
    expect(displayText('Nota de la operadora')).toBe('Nota de la operadora');
  });
  it('centralizes enum translations with safe unknown fallbacks', () => {
    expect(priorityLabel('Critical')).toBe('Crítica'); expect(orderStatusLabel('InProgress')).toBe('En proceso');
    expect(alertLevelLabel('DataGap')).toBe('Sin datos'); expect(reportStatusLabel('Linked')).toBe('Vinculado');
    expect(reportStatusLabel('Future')).toBe('Future');
  });
});
