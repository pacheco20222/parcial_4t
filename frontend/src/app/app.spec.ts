import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { signal } from '@angular/core';
import { App } from './app';
import { AuthService } from './core/auth/auth.service';
import { PointsStore } from './core/state/points.store';
import { PublicPoint } from './core/api/models';

describe('App', () => {
  it('keeps prototype notice and announces meaningful status changes in one region', async () => {
    const point: PublicPoint = {id:'P01',name:'Punto simulado P01 — Centro',zone:'Centro',lat:20.97,lon:-89.62,status:'Normal',waterDepthCm:3,simulated:true,updatedAt:null,lastUpdateAgeSeconds:null};
    const points = signal<PublicPoint[]>([point]);
    TestBed.configureTestingModule({ imports: [App], providers: [provideRouter([]),
      { provide: AuthService, useValue: {loadMe: () => of(null)} },
      { provide: PointsStore, useValue: {points} },
    ] });
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('footer')?.textContent).toContain('Datos simulados · Prototipo académico, no es un servicio oficial');
    expect(element.querySelectorAll('[role="status"]').length).toBe(1);
    expect(element.querySelector('[role="status"]')?.textContent).toBe('');
    points.set([{...point,status:'Alert'}]);
    await fixture.whenStable();
    expect(element.querySelector('[role="status"]')?.textContent).toBe('P01 Centro pasó a Alerta');
    points.set([{...point,status:'Alert',waterDepthCm:40}]);
    await fixture.whenStable();
    expect(element.querySelector('[role="status"]')?.textContent).toBe('P01 Centro pasó a Alerta');
  });
});
