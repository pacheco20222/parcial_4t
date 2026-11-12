import { Priority, WorkOrder } from '../api/models';

const priorityRank: Record<Priority, number> = {Critical: 0, High: 1, Medium: 2, Low: 3};
type SortableOrder = Pick<WorkOrder, 'status' | 'priority' | 'slaDueAt'>;
export function compareOpenWorkOrders(a: SortableOrder, b: SortableOrder, now = Date.now()): number {
  const overdue = (order: SortableOrder) => !['Resolved', 'Closed', 'Cancelled'].includes(order.status) && Date.parse(order.slaDueAt) < now;
  return Number(overdue(b)) - Number(overdue(a)) || priorityRank[a.priority] - priorityRank[b.priority] || Date.parse(a.slaDueAt) - Date.parse(b.slaDueAt);
}
