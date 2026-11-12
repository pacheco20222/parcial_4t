import { describe, expect, it } from 'vitest';
import { WorkOrder } from '../api/models';
import { compareOpenWorkOrders } from './work-order-ordering';
const now = Date.parse('2026-11-12T12:00:00Z');
function order(priority: WorkOrder['priority'], due: string, status: WorkOrder['status'] = 'Open') { return {priority, slaDueAt: due, status}; }
describe('work order urgency ordering', () => {
  it('puts overdue active orders ahead of future critical orders', () => {
    expect(compareOpenWorkOrders(order('Low', '2026-11-12T11:00:00Z'), order('Critical', '2026-11-12T13:00:00Z'), now)).toBeLessThan(0);
  });
  it('ranks priority before due time within the same overdue group', () => {
    const rows = ['Low', 'Medium', 'High', 'Critical'].map(priority => order(priority as WorkOrder['priority'], '2026-11-12T13:00:00Z'));
    expect(rows.sort((a, b) => compareOpenWorkOrders(a, b, now)).map(row => row.priority)).toEqual(['Critical', 'High', 'Medium', 'Low']);
  });
  it('breaks equal priority ties by earliest SLA', () => {
    expect(compareOpenWorkOrders(order('High', '2026-11-12T13:00:00Z'), order('High', '2026-11-12T14:00:00Z'), now)).toBeLessThan(0);
  });
  it('does not treat resolved orders as overdue', () => {
    expect(compareOpenWorkOrders(order('Low', '2026-11-12T11:00:00Z'), order('Critical', '2026-11-12T10:00:00Z', 'Resolved'), now)).toBeLessThan(0);
  });
});
