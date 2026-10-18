# Bot Hot Wheels — Varias cuentas / varias PCs

**Estado:** propuesta para decidir (no implementada) · **Fecha:** 2026-10-18 · **Autor:** análisis técnico para Gonza

## 1. Objetivo

Alcanzar más piezas en un drop de Mattel Creations usando más de una cuenta o
más de una PC.

## 2. Hallazgo clave: el límite no es técnico

Antes de multiplicar cuentas hay que entender por qué una sola no alcanza:

| Freno | Qué pasa | ¿Lo resuelve tener más cuentas? |
|---|---|---|
| **Límite por cliente / hogar** | En los drops, Mattel pone límite de piezas por persona o por hogar, y puede cancelar pedidos que lo excedan. | **No**: Mattel liga las cuentas por dirección, tarjeta, teléfono y dispositivo. Varias cuentas con tu dirección o tu tarjeta se cancelan juntas. |
| **Compras automatizadas** | Los términos de las tiendas grandes suelen permitir cancelar pedidos hechos con bots. **Revisa los Términos de venta de Mattel Creations antes de decidir.** | **No**: más bots son más huella. Arriesgas también la cuenta principal. |
| **Membresía RLC** | Es personal (una persona, una membresía) y es tu activo más valioso para las piezas RLC. | **No**: perderla cuesta más que una pieza. |
| **Velocidad** | Llegar antes que los demás. | Ya se atacó: aviso express, modo drop, navegador caliente, sin esperas fijas y cronómetro. |

**Conclusión:** varias cuentas tuyas, con tu dirección o tu tarjeta, **no te dan
más piezas y sí aumentan el riesgo** de cancelaciones y de perder la cuenta RLC.

Solo tiene sentido con **personas reales distintas**: un familiar con su propia
cuenta, su dirección, su tarjeta y su consentimiento, que compra lo que le
corresponde a su hogar.

## 3. Opciones evaluadas

| Opción | Cómo sería | A favor | En contra |
|---|---|---|---|
| **A. Un `.env` con varias cuentas** | `CUENTA1_CORREO`, `CUENTA1_TARJETA`, `CUENTA2_...` en el mismo archivo. | Rápido de hacer. | Mezcla tarjetas y direcciones en un archivo (un error de dedo paga con la tarjeta equivocada). Todos los secretos quedan juntos, un solo archivo filtrado los expone todos y no se puede apagar una cuenta sin tocar las otras. **No recomendado.** |
| **B. Un perfil por persona** (`compradores/<alias>/.env` + `perfil_mattel/`) | Cada comprador tiene su carpeta con sus datos y su sesión de Mattel. | Aislado: un perfil no ve los datos de otro. Se activa o apaga uno solo. Encaja con el navegador caliente (un perfil = una sesión). | Todos salen desde **la misma IP**, así que Mattel los puede ligar igual. |
| **C. B + varias PCs con un despachador central** | Cada PC corre el bot con **un** perfil. Railway reparte las piezas. | Distinta IP, dispositivo y persona por PC. Sin compras dobles (el despachador reserva cada pieza). | Más piezas que mantener. Cada PC necesita su propia instalación y su propio tope de gasto. |

**Recomendación:** si un familiar quiere participar, usa la **opción C**.
Mientras tanto, tú sigues con **una sola cuenta** (la RLC), que ya está
optimizada.

**El `.env` con varias cuentas (A) no lo haría:** es la opción con más riesgo
de pagar con la tarjeta equivocada o de filtrar todo junto.

## 4. Especificación funcional (si se aprueba la opción C)

### 4.1 Perfiles de comprador

- **RF-1.** Cada PC compradora tiene **un** perfil: alias, correo de Mattel, dirección, tarjeta y sesión (`perfil_mattel/`).
- **RF-2.** La tarjeta y el CVV se guardan en el **Administrador de credenciales de Windows** (librería `keyring`), no en `.env` en texto plano.
- **RF-3.** Cada perfil tiene su propio **tope por pieza y por mes**, y el **límite de piezas por hogar** de cada drop.
- **RF-4.** Un perfil solo se activa con el **consentimiento escrito** de su dueño, registrado en el panel con fecha.

### 4.2 Despachador en Railway

- **RF-5.** El monitor (PC o relevo) publica cada pieza comprable en una **cola** en Railway, por ejemplo `POST /api/bot/piezas`.
- **RF-6.** Cada PC compradora manda su latido (ya existe) y **pide trabajo**, por ejemplo `POST /api/bot/tomar`.
  - El despachador **reserva** cada pieza para un solo perfil a la vez (candado en SQLite, como `reservar_compra`).
  - Ninguna pieza se compra dos veces por error.
- **RF-7.** Reglas de reparto, en este orden:
  1. Las piezas RLC solo van a perfiles con sesión RLC.
  2. No se pasa del límite por hogar del perfil.
  3. Gana el perfil con mejor cronómetro reciente.
- **RF-8.** La confirmación sigue siendo humana: Telegram dice *"¿Comprar con el perfil Mamá (PC 2)?"*. Nada se compra solo.
- **RF-9.** El resultado (pedido, cobro, guía) se anota en el inventario con el **perfil que compró**, para saber de quién es cada paquete.

### 4.3 Panel

- **RF-10.** Una tarjeta por perfil:
  - estado (en línea, comprando, sin sesión, ciego)
  - última compra
  - gasto del mes contra su tope
  - cronómetro promedio
- **RF-11.** Un botón para **pausar** un perfil sin apagar los demás.

### 4.4 No funcionales

- **RNF-1.** Railway nunca guarda tarjetas ni CVV: solo alias, estado y reservas.
- **RNF-2.** Las PCs se autentican con un token por PC (revocable), no con tu contraseña.
- **RNF-3.** Si el despachador no responde, cada PC puede comprar solo lo que el usuario confirme a mano (como hoy).
- **RNF-4.** Pruebas: dos PCs falsas pidiendo la misma pieza, y solo una la obtiene.

## 5. Criterios de aceptación

1. Con dos PCs y una pieza, **solo una** compra (prueba automática).
2. Un perfil sin sesión RLC **nunca** recibe una pieza RLC.
3. Ningún archivo de Railway ni del repo contiene números de tarjeta.
4. Pausar un perfil detiene sus compras en menos de 1 min.

## 6. Fases sugeridas

| Fase | Entrega | Esfuerzo |
|---|---|---|
| 1 | Perfiles aislados en una PC (opción B) + `keyring` para la tarjeta | 1–2 sesiones |
| 2 | Cola y reservas en Railway + "pedir trabajo" desde la PC | 2 sesiones |
| 3 | Panel por perfil + reglas de reparto + pruebas de dos PCs | 1–2 sesiones |

## 7. Fuera de alcance

- Cuentas falsas, direcciones inventadas o tarjetas de terceros sin consentimiento.
- Proxies o rotación de IP para evadir los límites de Mattel.
- Compras sin confirmación humana.
