export type PointStatus = 'Normal' | 'Watch' | 'Alert' | 'NoData';
export type Role = 'Operator' | 'Supervisor' | 'Admin';
export type AlertLevel = 'Watch' | 'Alert' | 'DataGap';
export type OrderStatus = 'Open' | 'Assigned' | 'InProgress' | 'Resolved' | 'Closed' | 'Cancelled';
export type Priority = 'Low' | 'Medium' | 'High' | 'Critical';
export type ReportCategory = 'Encharcamiento' | 'CalleIntransitable' | 'DrenajeTapado' | 'Otro';
export interface PublicPoint { id: string; name: string; zone: string; lat: number; lon: number; status: PointStatus; simulated: boolean; waterDepthCm: number | null; updatedAt: string | null; lastUpdateAgeSeconds: number | null; watchThresholdCm?: number; alertThresholdCm?: number; }
export interface TelemetryKpis { pointsByStatus: Record<PointStatus, number>; maxDepthCm: number | null; rainLast60minMm: number | null; rainLast60minByPoint: Record<string, number | null>; dataFreshnessSeconds: number | null; }
export interface OpsKpis { openOrders: number; overdue: number; byPriority: {priority: Priority; count: number}[]; avgMinutesAlertToOnSiteLast7Days: number | null; openAlertsByLevel: {level: AlertLevel; count: number}[]; }
export interface Alert { id: string; pointId: string; pointName: string; zone: string; level: AlertLevel; status: 'Open' | 'Closed'; openedAt: string; closedAt: string | null; reason: string; depthCm: number | null; }
export interface WorkOrder { id: string; folio: string; alertId: string | null; citizenReportId: string | null; pointId: string; title: string; status: OrderStatus; priority: Priority; crewId: string | null; createdAt: string; slaDueAt: string; assignedAt: string | null; onSiteAt: string | null; resolvedAt: string | null; closedAt: string | null; cancelReason: string | null; version: string; }
export interface CitizenReport { id: string; folio: string; pointId: string | null; category: ReportCategory; description: string; status: 'Pending' | 'Validated' | 'Rejected'; reportedAt: string; linkedWorkOrderId: string | null; }
export interface ReportReceipt { id: string; folio: string; status: CitizenReport['status']; }
export interface Crew { id: string; name: string; zone: string; available: boolean; }
export interface User { id: string; email: string; roles: Role[]; mfaEnabled: boolean; }
export type Me = User;
export interface AuditEntry { id: number; userId: string | null; action: string; entity: string; at: string; ip: string | null; }
export interface Reading { capturedAt: string; waterDepthCm: number | null; rainMm5min: number | null; }
export interface Forecast { forecastFor: string; issuedAt: string; precipMm: number; }
export interface PointStatusEvent { pointId: string; status: PointStatus; waterDepthCm: number | null; capturedAt: string; }
export interface ReadingEvent extends Reading, PointStatusEvent { type: string; deviceId: string; qualityFlag: 'ok' | 'suspect'; }
export type WorkOrderStatus = OrderStatus;
