import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { OrderStatus, Priority } from '../core/api/models';
import { orderStatusLabel, priorityLabel } from '../core/state/labels';

@Component({
  selector: 'app-order-state',
  template: '<span class="state"><span class="step" aria-hidden="true">{{ step() }}</span>{{ label(status()) }}</span>',
  styles: [':host{display:inline-flex;color:var(--ink)}.state{display:inline-flex;align-items:center;gap:6px}.step{display:inline-grid;place-items:center;min-width:22px;height:22px;border:1px solid currentColor;font-weight:600}'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OrderStateComponent {
  readonly status = input.required<OrderStatus>();
  readonly label = orderStatusLabel;
  readonly step = computed(() => ({Open: '1', Assigned: '2', InProgress: '3', Resolved: '4', Closed: '4', Cancelled: '—'})[this.status()]);
}

@Component({
  selector: 'app-order-priority',
  template: '<span class="priority"><span class="bars" aria-hidden="true">@for(bar of bars;track bar){<i [class.filled]="bar <= weight()"></i>}</span>{{ label(priority()) }}</span>',
  styles: [':host{display:inline-flex;color:var(--ink)}.priority{display:inline-flex;align-items:center;gap:6px}.bars{display:inline-flex;align-items:end;gap:2px;height:14px}.bars i{display:block;width:3px;height:100%;background:var(--line)}.bars .filled{background:var(--ink)}'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OrderPriorityComponent {
  readonly priority = input.required<Priority>();
  readonly label = priorityLabel;
  readonly bars = [1, 2, 3, 4];
  readonly weight = computed(() => ({Critical: 4, High: 3, Medium: 2, Low: 1})[this.priority()]);
}
