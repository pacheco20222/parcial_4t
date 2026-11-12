import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import { MfaService, mfaQrImage } from '../../core/auth/mfa.service';
import { roleLabel } from '../../core/state/labels';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-account', imports: [FormsModule, IconComponent],
  template: `
    <main class="view account"><header class="view-header"><h1>Mi cuenta</h1></header>
      @if (auth.me(); as me) {
        <dl class="identity"><div><dt>Correo electrónico</dt><dd>{{ me.email }}</dd></div>
          <div><dt>Rol</dt><dd>@for (role of me.roles; track role) { <span>{{ roleLabel(role) }}</span> }</dd></div>
          <div><dt>Autenticación multifactor (MFA)</dt><dd class="account-state" [class.enabled]="me.mfaEnabled"><app-icon [name]="me.mfaEnabled ? 'check' : 'NoData'" />{{ me.mfaEnabled ? 'Activada' : 'Sin activar' }}</dd></div>
        </dl>
        @if (!me.mfaEnabled) {
          <section aria-labelledby="mfa-title"><h2 id="mfa-title">Protege tu acceso</h2>
            <p>Usa una aplicación de autenticación para verificar tu identidad al iniciar sesión.</p>
            @if (!uri()) {
              <button type="button" (click)="setup()" [disabled]="busy()">{{ busy() ? 'Preparando MFA…' : 'Activar MFA' }}</button>
            } @else {
              <p>Escanea este código en tu aplicación de autenticación.</p>
              <img class="qr" [src]="qrImage()" width="240" height="240" alt="Código QR para configurar MFA en tu aplicación de autenticación" />
              <label for="mfa-uri">Clave de configuración (también puedes copiarla)</label>
              <textarea id="mfa-uri" class="uri" readonly [value]="uri()" rows="3" (focus)="selectUri($event)"></textarea>
              <form (ngSubmit)="enable()" class="enrollment" novalidate>
                <label for="mfa-code">Código de verificación</label>
                <input id="mfa-code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" [(ngModel)]="code" aria-describedby="mfa-code-hint" [attr.aria-invalid]="submitted() && !validCode()" required />
                <p id="mfa-code-hint" [class.error]="submitted() && !validCode()">Ingresa los seis dígitos que muestra tu aplicación.</p>
                <button type="submit" [disabled]="busy()">{{ busy() ? 'Verificando…' : 'Confirmar activación' }}</button>
              </form>
            }
            @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
          </section>
        }
        <p class="feedback" role="status">{{ feedback() }}</p>
      }
    </main>`,
  styleUrls: ['./views.scss', './account.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AccountComponent {
  readonly auth = inject(AuthService);
  private readonly mfa = inject(MfaService);
  private readonly destroyRef = inject(DestroyRef);
  readonly roleLabel = roleLabel;
  readonly busy = signal(false);
  readonly uri = signal('');
  readonly qrImage = signal('');
  readonly error = signal('');
  readonly feedback = signal('');
  readonly submitted = signal(false);
  code = '';
  validCode(): boolean { return /^\d{6}$/.test(this.code); }
  selectUri(event: Event): void { (event.target as HTMLTextAreaElement).select(); }
  setup(): void {
    if (this.busy() || this.auth.me()?.mfaEnabled) return;
    this.busy.set(true); this.error.set(''); this.feedback.set('');
    this.mfa.setup().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.busy.set(false))).subscribe({
      next: result => {
        try { this.qrImage.set(mfaQrImage(result.otpauthUri)); this.uri.set(result.otpauthUri); }
        catch { this.error.set('No pudimos preparar el código QR. Intenta activar MFA de nuevo.'); }
      },
      error: () => this.error.set('No pudimos preparar MFA. Intenta de nuevo.'),
    });
  }
  enable(): void {
    this.submitted.set(true);
    if (this.busy() || !this.uri() || !this.validCode()) return;
    this.busy.set(true); this.error.set('');
    this.mfa.enable(this.code).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.busy.set(false))).subscribe({
      next: me => {
        this.code = ''; this.uri.set(''); this.qrImage.set('');
        if (me?.mfaEnabled) this.feedback.set('MFA activada. Tu próximo acceso solicitará un código.');
        else this.error.set('No pudimos confirmar la activación. Vuelve a iniciar sesión para revisar tu cuenta.');
      },
      error: () => this.error.set('No pudimos activar MFA. Revisa el código e intenta de nuevo.'),
    });
  }
}
