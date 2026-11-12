import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { PointStatus } from '../core/api/models';

export type IconName = PointStatus | 'menu' | 'close' | 'logout' | 'external' | 'refresh' | 'check' | 'user';
@Component({
  selector: 'app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    @switch (name()) {
      @case ('Alert') { <path d="M12 3 22 21H2Z"/><path d="M12 9v5m0 3v.1"/> }
      @case ('Watch') { <path d="m12 2 10 10-10 10L2 12Z"/><path d="M12 7v6m0 4v.1"/> }
      @case ('Normal') { <circle cx="12" cy="12" r="9"/> }
      @case ('NoData') { <path d="M3 3h18v18H3Zm0 7 7-7M3 17 17 3M7 21 21 7m-7 14 7-7"/> }
      @case ('menu') { <path d="M3 6h18M3 12h18M3 18h18"/> }
      @case ('close') { <path d="m5 5 14 14M5 19 19 5"/> }
      @case ('logout') { <path d="M9 3H3v18h6m5-14 5 5-5 5m-6-5h11"/> }
      @case ('external') { <path d="M14 3h7v7m0-7L10 14m0-11H3v18h18v-7"/> }
      @case ('refresh') { <path d="M20 7V2m0 5h-5M4 17v5m0-5h5M4 8a9 9 0 0 1 16-1M20 16a9 9 0 0 1-16 1"/> }
      @case ('check') { <path d="m4 12 5 5L20 6"/> }
      @case ('user') { <circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3"/> }
    }
  </svg>`,
  styles: `:host{display:inline-flex;inline-size:1.25em;block-size:1.25em;flex-shrink:0;vertical-align:middle}svg{width:100%;height:100%}`,
})
export class IconComponent { readonly name = input<IconName>('Normal'); }
