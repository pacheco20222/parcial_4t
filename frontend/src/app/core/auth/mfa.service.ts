import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, switchMap } from 'rxjs';
import qrcode from 'qrcode-generator';
import { AuthService } from './auth.service';
import { Me } from '../api/models';

export function mfaQrImage(uri: string): string {
  const qr = qrcode(0, 'M');
  qr.addData(uri);
  qr.make();
  return `data:image/svg+xml,${encodeURIComponent(qr.createSvgTag({ cellSize: 4, margin: 16 }))}`;
}

@Injectable({ providedIn: 'root' })
export class MfaService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  setup(): Observable<{ otpauthUri: string }> {
    return this.http.post<{ otpauthUri: string }>('/api/ops/auth/mfa/setup', {});
  }
  enable(code: string): Observable<Me | null> {
    return this.http.post<void>('/api/ops/auth/mfa/enable', { code }).pipe(switchMap(() => this.auth.loadMe(true)));
  }
}
