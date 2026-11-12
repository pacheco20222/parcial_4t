import { PointStatus, PublicPoint } from '../api/models';
export const STATUS_ORDER: PointStatus[] = ['Alert', 'Watch', 'NoData', 'Normal'];
export { statusLabel } from './labels';
export function formatAge(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return 'sin datos';
  const age = Math.max(0, Math.floor(seconds));
  if (age < 60) return `hace ${age} s`;
  if (age < 3600) return `hace ${Math.floor(age / 60)} min`;
  return `hace ${Math.floor(age / 3600)} h`;
}
export function pointAge(point: PublicPoint, now = Date.now()): number | null {
  if (!point.updatedAt) return point.lastUpdateAgeSeconds;
  const captured = Date.parse(point.updatedAt);
  return Number.isFinite(captured) ? Math.max(0, (now - captured) / 1000) : null;
}
export function formatSla(dueAt: string, now = Date.now()): string {
  const remaining = Date.parse(dueAt) - now;
  if (!Number.isFinite(remaining)) return 'Sin plazo disponible';
  const minutes = Math.max(0, remaining < 0 ? Math.floor(-remaining / 60000) : Math.ceil(remaining / 60000));
  const duration = minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`;
  return remaining < 0 ? `Vencida hace ${duration}` : `Quedan ${duration}`;
}
export function statusSentence(points: readonly PublicPoint[], now = Date.now()): string {
  if (!points.length) return 'Sin puntos disponibles — esperando datos';
  const counts = { Alert: 0, Watch: 0, NoData: 0, Normal: 0 };
  points.forEach(point => counts[point.status]++);
  const parts: string[] = [];
  if (counts.Alert) parts.push(`${counts.Alert} ${counts.Alert === 1 ? 'punto' : 'puntos'} en Alerta`);
  if (counts.Watch) parts.push(`${counts.Watch} en Vigilancia`);
  if (counts.NoData) parts.push(`${counts.NoData} sin datos`);
  if (!parts.length) parts.push(`${counts.Normal} ${counts.Normal === 1 ? 'punto' : 'puntos'} en Normal`);
  const ages = points.map(point => pointAge(point, now)).filter((age): age is number => age !== null);
  return `${parts.join(', ')} — ${ages.length ? `actualizado ${formatAge(Math.min(...ages))}` : 'sin actualización disponible'}`;
}

export function formatDepth(depth: number | null | undefined): string {
  return depth == null || !Number.isFinite(depth) ? 'sin datos' : `${depth.toFixed(1)} cm`;
}
