import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { UsersComponent } from './users.component';
import { CrewsComponent } from './crews.component';
import { AuditComponent } from './audit.component';
import { AuthService } from '../../core/auth/auth.service';
import { Role } from '../../core/api/models';

describe('Administrative lists', () => {
  let http: HttpTestingController;
  function configure(role: Role = 'Admin') {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), { provide: AuthService, useValue: { hasRole: (minimum: Role) => ({ Operator: 0, Supervisor: 1, Admin: 2 })[role] >= ({ Operator: 0, Supervisor: 1, Admin: 2 })[minimum] } }] });
    http = TestBed.inject(HttpTestingController);
  }
  afterEach(() => http.verify());
  it('requires a valid email and at least 12 password characters before creating a user', () => {
    configure();
    const component = TestBed.createComponent(UsersComponent).componentInstance;
    http.expectOne(request => request.url === '/api/ops/users' && request.params.get('limit') === '50' && request.params.get('offset') === '0').flush([]);
    component.email = 'invalid'; component.password = '123456789012'; component.create();
    http.expectNone(request => request.method === 'POST');
    component.email = 'staff@example.test'; component.password = 'short'; component.create();
    http.expectNone(request => request.method === 'POST');
    component.password = '123456789012'; component.role = 'Supervisor'; component.create(); component.create();
    const request = http.expectOne('/api/ops/users');
    expect(request.request.body).toEqual({ email: 'staff@example.test', password: '123456789012', role: 'Supervisor' });
    expect(component.saving()).toBe(true);
    request.flush({ id: 'new' });
    http.expectOne(request => request.url === '/api/ops/users' && request.method === 'GET').flush([]);
    expect(component.password).toBe(''); expect(component.feedback()).toBe('Usuario creado.');
  });
  it('hides crew creation and blocks direct creation attempts by an operator', () => {
    configure('Operator');
    const fixture = TestBed.createComponent(CrewsComponent);
    http.expectOne(request => request.url === '/api/ops/crews').flush([]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
    fixture.componentInstance.name = 'Centro'; fixture.componentInstance.zone = 'Centro'; fixture.componentInstance.create();
    http.expectNone(request => request.method === 'POST');
  });
  it('sends trimmed crew fields and shows a generic recoverable failure', () => {
    configure('Supervisor');
    const component = TestBed.createComponent(CrewsComponent).componentInstance;
    http.expectOne(request => request.url === '/api/ops/crews').flush([]);
    component.name = ' Equipo centro '; component.zone = ' Centro '; component.create();
    const request = http.expectOne('/api/ops/crews');
    expect(request.request.body).toEqual({ name: 'Equipo centro', zone: 'Centro' });
    request.flush({ error: 'sensitive backend details' }, { status: 400, statusText: 'Bad Request' });
    expect(component.saving()).toBe(false); expect(component.name).toBe(' Equipo centro ');
    expect(component.saveError()).toBe('No pudimos crear la cuadrilla. Revisa los datos e intenta de nuevo.');
  });
  it('pages audit with limit and offset and suppresses duplicate paging while pending', () => {
    configure();
    const component = TestBed.createComponent(AuditComponent).componentInstance;
    http.expectOne(request => request.url === '/api/ops/audit' && request.params.get('offset') === '0' && request.params.get('limit') === '50').flush([]);
    component.page(1); component.page(1);
    http.expectOne(request => request.url === '/api/ops/audit' && request.params.get('offset') === '50').flush([]);
    expect(component.offset()).toBe(50);
    component.page(-1);
    http.expectOne(request => request.url === '/api/ops/audit' && request.params.get('offset') === '0').flush([]);
  });
});
