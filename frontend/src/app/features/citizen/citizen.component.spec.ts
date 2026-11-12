import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PublicPoint } from '../../core/api/models';
import { PointsStore } from '../../core/state/points.store';
import { MapComponent } from '../../shared/map.component';
import { StatusBandComponent } from '../../shared/status-band.component';
import { CitizenComponent } from './citizen.component';

@Component({ selector: 'app-map', template: '', changeDetection: ChangeDetectionStrategy.OnPush })
class MapStub {
  readonly points = input<PublicPoint[]>([]);
  readonly selectedId = input<string | null>(null);
  // Match the shared map's public API without initializing Leaflet in these form tests.
  // eslint-disable-next-line @angular-eslint/no-output-native
  readonly select = output<string>();
}
@Component({ selector: 'app-status-band', template: '', changeDetection: ChangeDetectionStrategy.OnPush })
class StatusBandStub {}

describe('CitizenComponent report form', () => {
  const endpoint = '/api/ops/public/reports';
  function setup() {
    const points = { points: signal<PublicPoint[]>([]), now: signal(0), loading: signal(false), error: signal(null), reload: vi.fn() };
    TestBed.configureTestingModule({
      imports: [CitizenComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting(), { provide: PointsStore, useValue: points }],
    });
    TestBed.overrideComponent(CitizenComponent, {
      remove: { imports: [MapComponent, StatusBandComponent] },
      add: { imports: [MapStub, StatusBandStub] },
    });
    const fixture = TestBed.createComponent(CitizenComponent);
    fixture.detectChanges();
    return { fixture, form: fixture.componentInstance, http: TestBed.inject(HttpTestingController) };
  }
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('does not post incomplete, blank, or over-500-character descriptions', () => {
    const { form, http } = setup();
    form.send();
    form.category = 'Otro';
    form.description = '   ';
    form.send();
    form.description = 'x'.repeat(501);
    form.send();
    http.expectNone(endpoint);
    expect(form.submitted()).toBe(true);
    expect(form.sending()).toBe(false);
  });

  it('omits an optional point and sends the exact category and trimmed description', () => {
    const { form, http } = setup();
    form.category = 'CalleIntransitable';
    form.description = '  El agua cubre la calle.  ';
    form.send();
    const request = http.expectOne(endpoint);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ category: 'CalleIntransitable', description: 'El agua cubre la calle.' });
    request.flush({ folio: 'RC-2026-00001' });
  });

  it('includes a selected point and focuses the returned folio', async () => {
    const { fixture, form, http } = setup();
    form.pointId = 'P03';
    form.category = 'DrenajeTapado';
    form.description = 'Hay basura sobre la rejilla.';
    form.send();
    const request = http.expectOne(endpoint);
    expect(request.request.body).toEqual({ pointId: 'P03', category: 'DrenajeTapado', description: 'Hay basura sobre la rejilla.' });
    request.flush({ folio: 'RC-2026-00002' });
    fixture.detectChanges();
    await fixture.whenStable();
    expect(form.folio()).toBe('RC-2026-00002');
    expect(document.activeElement?.textContent).toContain('RC-2026-00002');
    expect(form.description).toBe('');
    expect(form.sending()).toBe(false);
  });

  it('shows and focuses the rate-limit message after HTTP 429', async () => {
    const { fixture, form, http } = setup();
    form.category = 'Encharcamiento';
    form.description = 'El agua sube en la esquina.';
    form.send();
    http.expectOne(endpoint).flush({ error: 'internal rate-limit details' }, { status: 429, statusText: 'Too Many Requests' });
    fixture.detectChanges();
    await fixture.whenStable();
    expect(document.activeElement?.textContent).toContain('Espera 10 minutos');
    expect(fixture.nativeElement.textContent).not.toContain('internal rate-limit details');
    expect(form.sending()).toBe(false);
    expect(form.description).toBe('El agua sube en la esquina.');
  });
});
