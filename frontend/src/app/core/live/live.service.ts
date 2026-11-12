import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { HubConnectionBuilder } from '@microsoft/signalr';
import { Subject } from 'rxjs';
import { Alert, CitizenReport, PointStatusEvent, ReadingEvent, WorkOrder } from '../api/models';
export type LiveState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';
@Injectable({ providedIn: 'root' })
export class LiveService {
  readonly state = signal<LiveState>('disconnected');
  readonly pointStatus$ = new Subject<PointStatusEvent>();
  readonly reading$ = new Subject<ReadingEvent>();
  readonly alert$ = new Subject<Alert>();
  readonly workOrder$ = new Subject<WorkOrder>();
  readonly report$ = new Subject<CitizenReport>();
  readonly reconnected$ = new Subject<void>();
  private readonly hub = new HubConnectionBuilder().withUrl('/hubs/live').withAutomaticReconnect().build();
  private generation = 0;
  private destroyed = false;
  private retry: ReturnType<typeof setTimeout> | undefined;
  private queue: Promise<void> = Promise.resolve();
  private stopping = false;
  constructor() {
    this.hub.on('pointStatus', (event: PointStatusEvent) => this.pointStatus$.next(event));
    this.hub.on('reading', (event: ReadingEvent) => this.reading$.next(event));
    this.hub.on('alert', (event: Alert) => this.alert$.next(event));
    this.hub.on('workOrder', (event: WorkOrder) => this.workOrder$.next(event));
    this.hub.on('report', (event: CitizenReport) => this.report$.next(event));
    this.hub.onreconnecting(() => this.state.set('reconnecting'));
    this.hub.onreconnected(() => { this.state.set('connected'); this.reconnected$.next(); });
    // Server-initiated close (e.g. CloseOnAuthenticationExpiration) or exhausted auto-reconnect:
    // reconnect with the (refreshed) cookie and reload lists, since events were missed.
    this.hub.onclose(() => {
      this.state.set('disconnected');
      const generation = this.generation;
      if (this.destroyed || this.stopping) return;
      clearTimeout(this.retry);
      this.retry = setTimeout(() => {
        if (generation !== this.generation) return;
        void this.connect(generation, 0).then(() => {
          if (this.state() === 'connected') this.reconnected$.next();
        });
      }, 5000);
    });
    inject(DestroyRef).onDestroy(() => { this.destroyed = true; this.stop(); });
  }
  start(): void { this.restart(); }
  restart(): void {
    const generation = ++this.generation;
    clearTimeout(this.retry);
    this.queue = this.queue.then(async () => {
      await this.stopHub();
      if (!this.destroyed && generation === this.generation) await this.connect(generation, 0);
    }).catch(() => this.state.set('disconnected'));
  }
  stop(): void { ++this.generation; clearTimeout(this.retry); void this.stopHub(); this.state.set('disconnected'); }
  private async stopHub(): Promise<void> {
    this.stopping = true;
    try { await this.hub.stop(); } finally { this.stopping = false; }
  }
  private async connect(generation: number, attempt: number): Promise<void> {
    if (this.destroyed || generation !== this.generation) return;
    this.state.set('connecting');
    try {
      await this.hub.start();
      if (generation === this.generation) this.state.set('connected');
    } catch {
      this.state.set('disconnected');
      if (attempt < 5 && generation === this.generation && !this.destroyed) {
        this.retry = setTimeout(() => void this.connect(generation, attempt + 1), 5000);
      }
    }
  }
}
