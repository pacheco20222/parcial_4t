import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { Subject, of, throwError } from 'rxjs';
import { AccountComponent } from './account.component';
import { AuthService } from '../../core/auth/auth.service';
import { MfaService } from '../../core/auth/mfa.service';
import { Me } from '../../core/api/models';

const identity: Me = { id: '1', email: 'staff@example.test', roles: ['Operator'], mfaEnabled: false };

describe('AccountComponent', () => {
  function setup() {
    const auth = { me: signal<Me | null>(identity) };
    const mfa = { setup: vi.fn().mockReturnValue(of({ otpauthUri: 'otpauth://totp/Flood:test?secret=EXAMPLE&issuer=Flood' })), enable: vi.fn().mockReturnValue(of({ ...identity, mfaEnabled: true })) };
    TestBed.configureTestingModule({ imports: [AccountComponent], providers: [{ provide: AuthService, useValue: auth }, { provide: MfaService, useValue: mfa }] });
    const fixture = TestBed.createComponent(AccountComponent);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, auth, mfa };
  }
  it('shows QR and selectable URI after setup without exposing an HTML style attribute', () => {
    const { fixture, component } = setup();
    component.setup(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img').getAttribute('src')).toMatch(/^data:image\/svg\+xml,/);
    expect(fixture.nativeElement.querySelector('textarea').value).toBe(component.uri());
    expect(fixture.nativeElement.querySelector('[style]')).toBeNull();
    component.code = '123'; component.enable();
    expect(component.submitted()).toBe(true);
  });
  it('blocks duplicate setup and malformed codes, then clears enrollment secrets after success', () => {
    const { fixture, component, mfa } = setup();
    const pending = new Subject<{ otpauthUri: string }>();
    mfa.setup.mockReturnValue(pending);
    component.setup(); component.setup();
    expect(mfa.setup).toHaveBeenCalledOnce();
    pending.next({ otpauthUri: 'otpauth://totp/Flood:test?secret=EXAMPLE' }); pending.complete();
    component.code = '12a456'; component.enable();
    expect(mfa.enable).not.toHaveBeenCalled();
    component.code = '123456'; component.enable(); fixture.detectChanges();
    expect(mfa.enable).toHaveBeenCalledWith('123456');
    expect(component.uri()).toBe(''); expect(component.qrImage()).toBe(''); expect(component.code).toBe('');
    expect(fixture.nativeElement.querySelector('[role="status"]').textContent).toContain('MFA activada');
  });
  it('keeps enrollment available and hides server error details after invalid code', () => {
    const { component, mfa } = setup();
    component.setup(); component.code = '123456';
    mfa.enable.mockReturnValue(throwError(() => new Error('private detail')));
    component.enable();
    expect(component.uri()).toMatch(/^otpauth:/);
    expect(component.busy()).toBe(false);
    expect(component.error()).toBe('No pudimos activar MFA. Revisa el código e intenta de nuevo.');
  });
  it('hides enrollment when MFA already enabled', () => {
    const { fixture, auth } = setup();
    auth.me.set({ ...identity, mfaEnabled: true }); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Activada');
  });
});
