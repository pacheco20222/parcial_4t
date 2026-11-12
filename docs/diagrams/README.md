# Diagramas de arquitectura

Fuentes en `src/` (`.mmd` Mermaid y/o `.drawio` editable); exportaciones PNG (escala 2x) y SVG en esta carpeta, con el XML de draw.io incrustado (se pueden reabrir en draw.io). Etiquetas en español (México). Fuente de verdad: `architecture.md`, `docs/contracts.md`, `docker-compose.yml`, `.github/workflows/ci.yml`.

| Archivo | Qué muestra | Pie de figura (PDF) | Criterio de rúbrica |
|---|---|---|---|
| `01-contexto` | C4 nivel 1: actores, plataforma, sensores simulados y Open-Meteo | Figura 1. Contexto del sistema (C4 nivel 1): actores y sistemas externos del Sistema de Monitoreo de Inundaciones de Mérida. | 1 (backend/arquitectura) |
| `02-contenedores` | C4 nivel 2: Caddy, SPA, microservicios, Mosquitto, Redis, PostgreSQL, SOC, por red | Figura 2. Contenedores (C4 nivel 2): dos microservicios (C# y Python) desacoplados por eventos en Redis, agrupados por zona de red. | 1 (microservicios, ERP/MES) |
| `03-red-idmz-zero-trust` | Segmentación IDMZ, subredes, IP fijas, matriz de flujos F1-F12, frontera del firewall, controles Zero Trust | Figura 3. Segmentación de red con IDMZ bajo Zero Trust: microsegmentación por zonas, lista blanca de puertos (F1-F12) y ausencia de ruta directa OT-TI. | 3 (IDMZ / Zero Trust) |
| `04-flujo-telemetria` | Secuencia sensor a tablero (MQTT, validación, deduplicación, Redis, SignalR) | Figura 4. Flujo de telemetría de extremo a extremo, del sensor simulado al tablero en tiempo real. | 1 y 2 (ingesta, tiempo real) |
| `05-modelo-datos` | ER con esquemas `telemetry` y `ops` diferenciados | Figura 5. Modelo de datos: un esquema y un rol de BD por servicio; `pointId` en `ops` es referencia por valor. | 1 (persistencia, ERP/MES) |
| `06-estados-punto` | Máquina de estados del punto de monitoreo | Figura 6. Estados de un punto: Normal, Vigilancia, Alerta y SinDatos. | 1 y 2 |
| `07-ciclo-orden-trabajo` | Ciclo de vida de la orden de trabajo | Figura 7. Ciclo de vida de la orden de trabajo (emulación ERP/MES). | 1 (ERP/MES) |
| `08-autenticacion` | Login y verificación de JWT RS256 entre microservicios | Figura 8. Autenticación: ops-service firma el JWT y telemetry-service lo verifica con la clave pública. | 3 (control de acceso) |
| `09-soc-siem` | Logs, Promtail, Loki, reglas SR-01..SR-07, respuesta | Figura 9. Flujo SOC/SIEM: de los logs a las reglas de detección y la respuesta a incidentes. | 3 (regla SIEM) |
| `10-ci-cd` | Pipeline actual de GitHub Actions | Figura 10. Pipeline de CI: pruebas por servicio, escaneo de secretos, CodeQL, Trivy y prueba de humo con Compose (CD diseñado, no habilitado). | 4 (calidad / DevSecOps) |
| `11-despliegue-vps` | VPS Hostinger (IaaS): firewall, pila Compose, volúmenes, Let's Encrypt, GitHub | Figura 11. Despliegue en un VPS IaaS de Hostinger: firewall (22 solo administración, 80, 443), Docker Compose y Caddy con Let's Encrypt. | 1 (justificación IaaS) |

## Regenerar

Requiere Docker (no se necesita draw.io instalado). Ejecutar desde `docs/diagrams`:

```bash
D="docker run --rm -v $PWD:/data -w /data rlespinasse/drawio-desktop-headless@sha256:95f6c9cec1346592a3122b4d8c2e1008a92cb36276e3a657cdb74524ba1f0fcb"

# Mermaid -> .drawio (solo 01, 04, 08, 09, 10)
$D -x -f xml -o src/NOMBRE.drawio src/NOMBRE.mmd

# .drawio -> PNG / SVG con XML incrustado
$D -x -f png -e -b 10 -s 2 -o NOMBRE.png src/NOMBRE.drawio
$D -x -f svg -e -b 10 -o NOMBRE.svg src/NOMBRE.drawio
```

`02`, `03`, `05`, `06`, `07` y `11` se editaron como XML de draw.io (posiciones exactas); su `.drawio` en `src/` es la fuente. Se pueden modificar abriéndolos en draw.io y volver a exportar con los comandos anteriores.
