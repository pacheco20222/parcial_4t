import { PointStatus, PublicPoint } from '../api/models';

export function pointLabel(point: {id: string; zone: string}): string {
  return `${point.id} ${point.zone}`.trim();
}
export function statusLabel(status: PointStatus): string {
  return {Normal: 'Normal', Watch: 'Vigilancia', Alert: 'Alerta', NoData: 'Sin datos'}[status];
}
export function priorityLabel(value: string): string {
  return ({Critical: 'Crítica', High: 'Alta', Medium: 'Media', Low: 'Baja'} as Record<string, string>)[value] ?? value;
}
export function orderStatusLabel(value: string): string {
  return ({Open: 'Abierta', Assigned: 'Asignada', InProgress: 'En proceso', Resolved: 'Resuelta', Closed: 'Cerrada', Cancelled: 'Cancelada'} as Record<string, string>)[value] ?? value;
}
export function alertLevelLabel(value: string): string {
  return ({Watch: 'Vigilancia', Alert: 'Alerta', DataGap: 'Sin datos'} as Record<string, string>)[value] ?? value;
}
export function alertStatusLabel(value: string): string {
  return ({Open: 'Abierta', Closed: 'Cerrada'} as Record<string, string>)[value] ?? value;
}
export function reportStatusLabel(value: string): string {
  return ({Pending: 'Pendiente', Validated: 'Validado', Rejected: 'Rechazado', Linked: 'Vinculado'} as Record<string, string>)[value] ?? value;
}
export function roleLabel(value: string): string {
  return ({Operator: 'Operador', Supervisor: 'Supervisor', Admin: 'Administrador'} as Record<string, string>)[value] ?? value;
}
export function displayText(text: string, points: readonly PublicPoint[] = [], pointId?: string): string {
  if (text === 'Water depth threshold exceeded') return 'Tirante superó el umbral';
  if (text === 'Telemetry unavailable') return 'Sin datos de telemetría';
  const match = /^(Flood response|Inspect device)(?::\s*(.*))?$/i.exec(text);
  if (!match) return text;
  const name = match[2] ?? '';
  const point = points.find(item => item.id === pointId || item.name === name || pointLabel(item) === name);
  const compact = point ? pointLabel(point) : name.replace(/^Punto simulado\s+(P\d+)\s*[—–-]\s*/i, '$1 ');
  const label = match[1].toLowerCase() === 'flood response' ? 'Atención de inundación' : 'Revisar sensor';
  return compact ? `${label}: ${compact}` : label;
}
