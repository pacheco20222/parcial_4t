import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { PublicPoint } from '../core/api/models';
import { PointsStore } from '../core/state/points.store';
import { LiveService, LiveState } from '../core/live/live.service';
import { StatusBandComponent } from './status-band.component';

describe('StatusBandComponent', () => {
  it('shows a readable status sentence and connection state without extra live regions', async () => {
    const now = Date.parse('2026-11-12T12:00:09Z');
    const point: PublicPoint = {id:'P01',name:'Centro',zone:'Centro',lat:20.97,lon:-89.62,status:'Alert',simulated:true,waterDepthCm:38.4,updatedAt:'2026-11-12T12:00:00Z',lastUpdateAgeSeconds:9};
    const state = signal<LiveState>('connected');
    TestBed.configureTestingModule({imports:[StatusBandComponent],providers:[
      {provide:PointsStore,useValue:{points:signal([point]),now:signal(now),worstStatus:signal('Alert'),loading:signal(false),error:signal(null)}},
      {provide:LiveService,useValue:{state}},
    ]});
    const fixture = TestBed.createComponent(StatusBandComponent);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('1 punto en Alerta — actualizado hace 9 s');
    expect(el.textContent).toContain('En vivo');
    state.set('reconnecting');
    await fixture.whenStable();
    expect(el.textContent).toContain('Reconectando…');
    expect(el.querySelector('[aria-live]')).toBeNull();
  });
});
