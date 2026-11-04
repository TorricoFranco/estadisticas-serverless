# ERS: Estadísticas de fútbol serverless

| Campo | Valor |
|---|---|
| Nombre de trabajo | `estadisticas-serverless` |
| Versión del documento | 0.1, borrador para aprobación |
| Fecha | 2026-11-03 |
| Estado | Pendiente de aprobación de Franco. No se implementa nada hasta que se apruebe. |
| Relación con ChiquiMafias | Proyecto independiente. No comparte código, cuentas, tablas ni infraestructura con `chiquimafias/`. |
| Ubicación prevista | `C:\Users\Franco\Desktop\fullstack\estadisticas-serverless\ERS.md` |

## Índice

1. Propósito, alcance y exclusiones
2. Glosario
3. Actores y casos de uso
4. Requisitos funcionales
5. Requisitos no funcionales
6. Arquitectura
7. Modelo de datos en DynamoDB
8. Contrato de la API
9. Eventos y mensajes
10. Seguridad
11. Pruebas y despliegue
12. Costos y control de gasto
13. Riesgos y preguntas abiertas
- Anexo A. Formatos de entrada y salida

## Convenciones

- Los identificadores (funciones, tablas, campos, rutas técnicas, nombres de recursos) van en inglés. Los textos que lee una persona (mensajes de error, resúmenes, reportes) van en español.
- **Debe**: obligatorio en la versión 1. **Debería**: recomendado; si se posterga, hay que justificarlo. **Puede**: opcional.
- Prefijos de identificadores: `C` decisión cerrada, `S` supuesto, `D` decisión abierta, `P` decisión propuesta por este documento, `RF` requisito funcional, `NFR` requisito no funcional, `UC` caso de uso, `T` caso de prueba, `R` riesgo.
- Los precios marcados **[verificado]** tienen fuente indicada. Los marcados **[estimación]** no están verificados: hay que confirmarlos en la calculadora de precios de AWS antes de usarlos como referencia.

## 1. Propósito, alcance y exclusiones

### 1.1 Propósito

Construir una API de estadísticas de fútbol que se llena sola a partir de archivos CSV. El operador sube el CSV con los partidos de una fecha. El sistema valida los datos, guarda los partidos, genera un resumen por partido y mantiene la tabla de posiciones.

### 1.2 Alcance de la versión 1

La versión 1 debe incluir:

- Subida de un CSV por fecha mediante una URL firmada de S3.
- Validación y normalización de cada fila, con rechazo de archivos inválidos y reporte de errores.
- Persistencia de partidos en DynamoDB, de forma idempotente.
- Un mensaje de SQS por partido nuevo o modificado, y una Lambda que genera el resumen con una plantilla.
- Tabla de posiciones por competición y temporada, recalculada una vez por día.
- API HTTP con tres rutas: `POST /uploads`, `GET /partidos` y `GET /tabla`.
- Logs estructurados, alarmas y una cola de mensajes muertos (DLQ) con alarma.
- Infraestructura completa en AWS CDK (Python), pruebas con pytest y moto, y un pipeline de GitHub Actions con OIDC.
- Un smoke test que verifica la demo desplegada.

### 1.3 Exclusiones de la versión 1

La versión 1 no incluye:

- Interfaz web. La demo se hace con `curl`, un script o la documentación OpenAPI.
- Usuarios finales, registro, login o roles. Solo el operador escribe datos.
- RAG, base vectorial ni búsqueda semántica. Si se suman después, son una etapa aparte. S3 Vectors está disponible desde diciembre de 2025 y sería una opción para esa etapa.
- Athena y consultas SQL sobre los CSV (decisión D-03: etapa aparte).
- Resumen con modelo de IA (decisión D-04: la v1 usa solo plantilla; la etapa de IA queda diseñada, con proveedor pendiente).
- Conexión automática con fuentes de datos externas (scraping o APIs de terceros). Los CSV los sube el operador.
- Actualizaciones en tiempo real, websockets o notificaciones push.
- Alta disponibilidad multirregión, réplicas o plan de recuperación ante desastres.
- EC2, RDS, NAT Gateway, balanceadores de carga, VPC con salida a internet, Secrets Manager y claves KMS propias.
- Alias de equipos (por ejemplo, tratar "River" y "River Plate" como un mismo equipo).
- Desempates de la tabla por enfrentamientos directos. La v1 usa solo los criterios de RF-13.
- Borrado de partidos que no aparecen en un CSV nuevo de la misma fecha (ver RF-05).

### 1.4 Decisiones de diseño cerradas

Estas decisiones vienen del pedido de Franco. Este documento no las reabre.

| ID | Decisión |
|---|---|
| C-01 | Solo serverless. Sin EC2, RDS, NAT Gateway, balanceadores ni Secrets Manager. |
| C-02 | Todo el código en Python. La infraestructura se describe con AWS CDK en Python. |
| C-03 | El despliegue se hace con GitHub Actions usando OIDC. No hay claves de acceso de larga duración. |
| C-04 | La configuración sensible va en SSM Parameter Store. No se crean claves KMS propias. |
| C-05 | Las pruebas usan pytest y moto. |
| C-06 | Los logs son estructurados y se retienen 7 días. |
| C-07 | Costo objetivo: menos de USD 1 al mes con uso de demo, usando la capa gratuita y los créditos de cuenta nueva. |
| C-08 | Sin RAG ni base vectorial en la v1. |
| C-09 | La API es una HTTP API de API Gateway con tres rutas: `POST /uploads`, `GET /partidos` y `GET /tabla`. |
| C-10 | La tabla de posiciones se recalcula con EventBridge una vez por día. |

### 1.5 Supuestos

| ID | Supuesto | Si no se cumple |
|---|---|---|
| S-01 | Hay una sola cuenta de AWS para la demo, sin AWS Organizations. | Hay que separar cuentas y revisar el presupuesto. |
| S-02 | Región de despliegue: `us-east-1` (propuesta por costo y disponibilidad de servicios; ver R-09). | Cambiar la región en CDK y revisar precios y latencia. |
| S-03 | Un solo operador (Franco), con acceso IAM. | Habría que agregar roles de usuario y auditoría. |
| S-04 | Los CSV están en UTF-8 y separados por coma. | Se rechazan con `ENCODING_INVALID` o `ROW_FORMAT_INVALID` (RF-02). |
| S-05 | Cada archivo corresponde a una sola competición, una temporada y una fecha. | Se rechaza el archivo (RF-04). |
| S-06 | Volumen de demo: decenas de partidos por fecha y cientos por temporada. | Revisar el recálculo de la tabla (R-05). |
| S-07 | Runtime de Lambda: Python 3.12 o 3.13, el que esté soportado al momento de implementar. | Ajustar la versión en CDK y en las pruebas. |

## 2. Glosario

### 2.1 Términos del dominio y del proyecto

| Término | Significado simple |
|---|---|
| Fecha (matchday) | Una jornada del torneo. Todos los partidos de una fecha van en un mismo CSV. |
| Partido | Un encuentro entre dos equipos, con los goles de local y de visitante. |
| Competición | El torneo, por ejemplo la liga. En el CSV va como slug (`liga-profesional`). |
| Temporada | El año o período del torneo (por ejemplo, `2026`). |
| Tabla de posiciones | Ranking de los equipos de una temporada, con puntos, partidos jugados y diferencia de goles. |
| CSV | Archivo de texto con una fila por partido y columnas separadas por coma. |
| Slug | Texto en minúsculas, sin tildes y con guiones en lugar de espacios. "Vélez Sarsfield" queda como `velez-sarsfield`. |
| Ingesta | Proceso que lee el CSV, lo valida, guarda los partidos y encola el trabajo siguiente. |
| Normalización | Limpieza de los datos: quitar espacios sobrantes, pasar fechas a formato ISO y generar identificadores estables. |
| Resumen | Texto corto que describe el resultado de un partido. En la v1 sale de una plantilla. |
| URL firmada | Dirección temporal que permite subir un archivo a S3 sin credenciales de AWS. Vence y tiene condiciones (tamaño, tipo). |
| Idempotente | Operación que, repetida con los mismos datos, deja el mismo resultado: no duplica partidos ni mensajes. |
| Cola de mensajes muertos (DLQ) | Cola donde van los mensajes que fallaron después de varios intentos. Tiene una alarma. |
| Recálculo | Volver a calcular la tabla de posiciones a partir de todos los partidos de la temporada. |
| Demo | Uso del sistema con volumen bajo, para presentarlo y probarlo. No hay tráfico real. |
| Operador | Franco. Es la única persona que sube CSV, despliega y revisa logs y alarmas. |

### 2.2 Servicios de AWS

| Servicio | Qué hace en este proyecto |
|---|---|
| Amazon S3 | Guarda los CSV subidos (prefijos `incoming/`, `processed/` y `rejected/`) y los reportes de error (`reports/`). Dispara la ingesta cuando llega un archivo. |
| AWS Lambda | Ejecuta el código Python sin servidores: las rutas de la API, la ingesta, los resúmenes y el recálculo de la tabla. Se paga por ejecución. |
| Amazon SQS | Cola de mensajes: un mensaje por partido para generar su resumen. Su DLQ recibe los mensajes que fallan. |
| Amazon DynamoDB | Base de datos NoSQL con las tablas de partidos y de posiciones. Modo on-demand, sin servidores que administrar. |
| Amazon API Gateway (HTTP API) | Expone las tres rutas HTTP y las conecta con sus Lambdas. Aplica límites de tasa. |
| Amazon EventBridge | Programador que dispara el recálculo de la tabla una vez por día. |
| Amazon CloudWatch | Guarda los logs de las Lambdas (7 días), mide errores y tiene las alarmas (DLQ, errores de Lambda y errores 5xx de la API). |
| AWS IAM | Define los permisos: un rol por función Lambda, el rol de despliegue de GitHub y el proveedor OIDC de GitHub. |
| AWS Systems Manager Parameter Store | Guarda la configuración (por ejemplo, la temporada por defecto o el modo del resumen). Los valores sensibles van como SecureString. |
| AWS CloudFormation | Crea, actualiza y borra los recursos a partir de la plantilla que genera CDK. |
| AWS CDK (Python) | Librería para describir la infraestructura en código Python. No es un servicio, pero genera la plantilla de CloudFormation. |
| AWS Budgets (propuesto) | Envía alertas cuando el gasto se acerca al objetivo de USD 1. No está en la lista original; ver sección 12. |
| Amazon SNS (propuesto) | Envía por email las alarmas de CloudWatch. No está en la lista original; ver RF-11. |
| Amazon Bedrock (solo etapa de IA) | Acceso administrado a modelos de IA. Solo si se activa la etapa de IA (D-04). |
| Amazon Athena (solo etapa aparte) | Consultas SQL sobre los CSV de S3. Fuera de la v1 (D-03). |

## 3. Actores y casos de uso

### 3.1 Actores

| Actor | Tipo | Qué hace |
|---|---|---|
| Operador (Franco) | Persona, con acceso IAM | Sube los CSV, despliega, revisa logs y alarmas. |
| Consumidor de la API | Persona o programa | Consulta partidos y la tabla. Puede ser un reclutador, un evaluador técnico o un front-end futuro. No se autentica en la v1. |
| EventBridge | Sistema (programador) | Dispara el recálculo de la tabla todos los días. |
| Amazon S3 | Sistema | Avisa a la ingesta cuando llega un CSV nuevo. |
| Proveedor de IA | Sistema externo (solo etapa de IA) | Genera el texto del resumen. Es opcional. |

### 3.2 Casos de uso

| ID | Caso de uso | Actor principal | Disparador |
|---|---|---|---|
| UC-01 | Subir el CSV de una fecha | Operador | Hay partidos nuevos o corregidos para cargar. |
| UC-02 | Consultar partidos | Consumidor | Quiere ver los resultados de una fecha o de una temporada. |
| UC-03 | Consultar la tabla | Consumidor | Quiere ver la tabla de posiciones. |
| UC-04 | Recibir el resumen de cada partido | Consumidor (lo lee dentro de UC-02) | Un partido se guardó y su resumen se genera de forma asíncrona. |
| UC-05 | Recalcular la tabla | EventBridge (y el operador, de forma manual) | Pasó el día, o el operador lo pide. |

### 3.3 Detalle de los casos de uso

#### UC-01 · Subir el CSV de una fecha

- **Actor:** Operador.
- **Precondiciones:** la API y el bucket están desplegados. El operador tiene credenciales IAM válidas.
- **Flujo principal:**
  1. El operador pide una URL firmada con `POST /uploads`, indicando el nombre del archivo y su tipo.
  2. La API responde con un `upload_id` y los campos necesarios para subir el archivo a S3.
  3. El operador sube el CSV a S3 antes de que venza la URL.
  4. S3 guarda el archivo como `incoming/<upload_id>.csv` y dispara la ingesta.
  5. La ingesta valida y normaliza cada fila.
  6. Si el archivo es válido, guarda los partidos en DynamoDB y encola un mensaje por cada partido nuevo o modificado.
  7. El archivo pasa a `processed/`.
- **Flujos alternativos:**
  - A1. El archivo no cumple las reglas de RF-02 a RF-04. Pasa a `rejected/` y se genera `reports/<upload_id>.json`. No se guarda ningún partido de ese archivo.
  - A2. El archivo supera 1 MB. S3 rechaza la subida y no se crea ningún objeto.
  - A3. La URL venció. La subida falla y hay que pedir otra URL.
  - A4. Falla técnica (excepción no controlada, timeout). Se reintenta y, si persiste, el evento va a la DLQ (RF-11).
- **Postcondiciones:** los partidos válidos están en DynamoDB y sus mensajes de resumen están encolados.
- **Requisitos:** RF-01 a RF-08, RF-11.

#### UC-02 · Consultar partidos

- **Actor:** Consumidor.
- **Precondiciones:** hay partidos cargados.
- **Flujo principal:** el consumidor llama a `GET /partidos` con `competition` y `season`, y opcionalmente `matchday`. Recibe los partidos con su resumen, si ya está generado.
- **Flujos alternativos:**
  - A1. Falta un parámetro obligatorio o tiene formato inválido. La API responde 400.
  - A2. No hay partidos con esos filtros. La API responde 200 con una lista vacía.
- **Postcondiciones:** ninguna (solo lectura).
- **Requisitos:** RF-12, NFR-04.

#### UC-03 · Consultar la tabla

- **Actor:** Consumidor.
- **Precondiciones:** existe una tabla calculada para la competición y la temporada.
- **Flujo principal:** el consumidor llama a `GET /tabla` con `competition` y `season`. Recibe los equipos ordenados por posición.
- **Flujos alternativos:**
  - A1. Parámetros inválidos. La API responde 400.
  - A2. No hay tabla para esa competición y temporada. La API responde 404.
- **Requisitos:** RF-13, NFR-04.

#### UC-04 · Recibir el resumen de cada partido

- **Actor:** Consumidor, que lo lee dentro de UC-02. El sistema lo genera de forma asíncrona.
- **Precondiciones:** el partido fue guardado por UC-01.
- **Flujo principal:** la ingesta encola un mensaje por partido. La Lambda de resúmenes lo consume, genera el texto con la plantilla y lo guarda en el partido (`summary`, `summary_status = READY`).
- **Flujos alternativos:**
  - A1. Mientras el resumen no existe, el partido aparece con `summary_status = PENDING` y `summary` vacío.
  - A2. El resumen falla en todos los intentos. El mensaje va a la DLQ y el partido queda con `summary_status = FAILED` (RF-09 y RF-11).
- **Requisitos:** RF-09, RF-10 (solo etapa de IA), RF-11.

#### UC-05 · Recalcular la tabla

- **Actor:** EventBridge (una vez por día) y el operador (de forma manual, para la demo).
- **Precondiciones:** hay partidos cargados.
- **Flujo principal:** la función lee los partidos de cada competición y temporada, calcula puntos, goles y posiciones, y reemplaza la tabla de esa temporada.
- **Flujos alternativos:**
  - A1. Falla técnica. Se reintenta y, si persiste, el evento va a la DLQ.
  - A2. Invocación manual con el comando de la sección 11.7.
- **Requisitos:** RF-14, NFR-08.

## 4. Requisitos funcionales

Cada requisito indica los casos de uso que lo usan. El criterio de aceptación es la prueba que dice si el requisito se cumple. Cuando un criterio dice "pytest", se verifica con moto o con un test unitario. Cuando dice "AWS real", se verifica en la demo desplegada.

### RF-01 · Generar la URL firmada para subir el CSV (UC-01)

- **Descripción:** `POST /uploads` devuelve una URL firmada de S3 de tipo POST (presigned POST) para subir un archivo a `incoming/<upload_id>.csv`. La firma incluye las condiciones: tamaño máximo de 1.048.576 bytes, `Content-Type` igual a `text/csv`, y vencimiento a los 300 segundos. El `upload_id` es un UUID v4 generado en el servidor.
- **Criterio de aceptación:**
  - Con un body válido, la respuesta es 201 con `upload_id`, `upload.url`, `upload.fields` y `expires_in: 300` (pytest).
  - La política firmada contiene la condición de tamaño y la de tipo de contenido (pytest).
  - Un archivo de 1.048.577 bytes es rechazado por S3 (AWS real).
  - Un nombre que no termina en `.csv` responde 400 `VALIDATION_ERROR` (pytest).

### RF-02 · Validar la estructura y el formato del archivo (UC-01)

- **Descripción:** antes de leer las filas, la ingesta valida:
  - a) el archivo no está vacío y pesa como máximo 1.048.576 bytes;
  - b) el contenido es UTF-8 (se acepta BOM);
  - c) la primera fila es el encabezado y tiene las columnas obligatorias: `competition`, `season`, `matchday`, `match_date`, `home_team`, `away_team`, `home_goals`, `away_goals`. Las columnas extra se ignoran y se registran como advertencia (`EXTRA_COLUMN_IGNORED`) en el reporte;
  - d) hay entre 1 y 500 filas de datos. Si no hay ninguna, `NO_DATA_ROWS`;
  - e) cada fila tiene la misma cantidad de campos que el encabezado.
- **Aclaraciones de implementación:** los nombres de columna no distinguen mayúsculas ni espacios sobrantes, y las líneas vacías se ignoran.
- **Criterio de aceptación:**
  - Un archivo sin `away_goals` se rechaza con `HEADER_MISSING_COLUMN` y nombra la columna faltante (pytest).
  - Un archivo con 501 filas se rechaza con `TOO_MANY_ROWS` (pytest).
  - Un archivo en Latin-1 con tildes se rechaza con `ENCODING_INVALID` (pytest).
  - Un archivo vacío se rechaza con `EMPTY_FILE` (pytest).
  - Una fila con más campos que el encabezado se rechaza con `ROW_FORMAT_INVALID` (pytest).

### RF-03 · Normalizar cada fila (UC-01)

- **Descripción:** cada fila pasa por estas reglas antes de validarse en detalle:
  - **Texto:** se quitan los espacios al inicio y al final, y se reducen los espacios internos a uno. No se cambian mayúsculas ni tildes de los nombres que se muestran.
  - **`competition`:** se convierte a slug (minúsculas, sin tildes, espacios y signos reemplazados por guiones, sin guiones repetidos). Debe quedar entre 2 y 40 caracteres, solo con `a-z`, `0-9` y guiones.
  - **`season`:** entero de 4 dígitos entre 2000 y 2100.
  - **`matchday`:** entero entre 1 y 99.
  - **`match_date`:** fecha en formato `YYYY-MM-DD`. No se aceptan otros formatos en la v1. Debe estar entre 2000-01-01 y un año después de la fecha de carga.
  - **`home_team` y `away_team`:** entre 2 y 60 caracteres. Se guarda el nombre normalizado y se calcula `team_id` como slug sin tildes.
  - **`home_goals` y `away_goals`:** enteros entre 0 y 30, sin signos ni decimales.
  - Si un campo obligatorio queda vacío después de normalizar, la fila se rechaza con `FIELD_REQUIRED`.
  - Cada fila recibe `match_id` (sección 7.4) y `data_hash` (SHA-256 de los campos normalizados).
- **Criterio de aceptación:**
  - `" Liga  Profesional "` queda como `liga-profesional` (pytest).
  - `"Vélez Sarsfield"` genera `team_id` igual a `velez-sarsfield` (pytest).
  - `"3.0"` en `home_goals` se rechaza con `GOALS_INVALID` (pytest).
  - `"2026-3-14"` en `match_date` se rechaza con `DATE_INVALID` (pytest).

### RF-04 · Validar la consistencia del archivo (UC-01)

- **Descripción:** después de normalizar, la ingesta valida las reglas que cruzan filas:
  - a) todas las filas tienen la misma `competition`, `season` y `matchday` (S-05). Si no, `MIXED_MATCHDAY`;
  - b) `home_team` y `away_team` no son el mismo equipo (se compara `team_id`). Si lo son, `SAME_TEAM`;
  - c) no hay dos partidos con el mismo local y visitante dentro del archivo. Si los hay, `DUPLICATE_MATCH`;
  - d) un equipo no aparece más de una vez en la misma fecha. Si aparece, `TEAM_REPEATED_IN_MATCHDAY`.
- **Criterio de aceptación:**
  - Un archivo donde "Boca Juniors" juega dos veces en la fecha 5 se rechaza con `TEAM_REPEATED_IN_MATCHDAY` y no se escribe ningún partido (pytest).
  - Un archivo con dos competiciones distintas se rechaza con `MIXED_MATCHDAY` (pytest).

### RF-05 · Guardar partidos de forma idempotente (UC-01)

- **Descripción:** la validación es todo o nada: si hay un error en cualquier fila, no se escribe ningún partido. Si el archivo es válido, cada partido se guarda con una escritura de tipo upsert (crea o reemplaza) usando `match_id` como clave. Las escrituras son idempotentes: si la ingesta falla a mitad, el reintento completa el trabajo sin duplicar nada.
- Subir una fecha ya cargada reemplaza los partidos que coinciden por `match_id`. Los partidos guardados que no vienen en el archivo nuevo **no se borran** en la v1 (ver R-13).
- **Criterio de aceptación:**
  - Subir dos veces el mismo archivo deja N partidos, no 2N (pytest).
  - Subir un archivo donde cambió un resultado (de 2-1 a 3-1) actualiza ese partido y no crea otro (pytest).
  - Un reintento de la ingesta tras un fallo simulado a mitad de las escrituras deja el mismo estado que una ejecución sin fallos (pytest con moto).

### RF-06 · Encolar un mensaje por partido que necesita resumen (UC-01, UC-04)

- **Descripción:** cada partido guarda `summary_data_hash`, que es el `data_hash` con el que se generó su último resumen. Después de escribir un partido, la ingesta envía un mensaje a SQS si `summary_data_hash` no coincide con `data_hash`. Eso pasa en tres casos: el partido es nuevo, cambió su resultado o fecha, o el envío anterior falló antes de que se generara el resumen.
- Cuando cambia el `data_hash` de un partido, la ingesta pone `summary_status = PENDING`.
- El formato del mensaje está en la sección 9.3.
- **Criterio de aceptación:**
  - Un archivo con 10 partidos nuevos encola 10 mensajes (pytest con moto).
  - Subir de nuevo el mismo archivo, con los resúmenes ya en `READY`, encola 0 mensajes (pytest).
  - Cambiar un resultado encola 1 mensaje y el partido pasa a `PENDING` (pytest).
  - Si el envío a SQS falla después de escribir el partido, un reintento de la ingesta vuelve a enviar el mensaje (pytest con un fallo simulado).

### RF-07 · Archivar el CSV según el resultado (UC-01)

- **Descripción:** S3 no tiene operación de mover. La ingesta copia el objeto y luego borra el original:
  - archivo válido: copia a `processed/<upload_id>.csv`;
  - archivo inválido: copia a `rejected/<upload_id>.csv`.
  - En los dos casos borra el original de `incoming/`.
- **Criterio de aceptación:**
  - Después de la ingesta, `incoming/` no tiene objetos del `upload_id` procesado (pytest con moto).
  - Un evento de S3 repetido para un objeto que ya no existe termina sin error y sin cambios en los datos (pytest).

### RF-08 · Generar el reporte de errores (UC-01)

- **Descripción:** todo archivo procesado genera `reports/<upload_id>.json` con: `upload_id`, `status` (`PROCESSED` o `REJECTED`), `rows_total`, `matches_written`, `messages_enqueued`, `warnings` y `errors`. Cada error tiene `line` (número de línea del archivo, con el encabezado en la línea 1), `column` (o `null`), `code` y `message` en español. El reporte guarda como máximo 50 errores. Si hay más, marca `errors_truncated: true`. El formato completo está en el anexo A.
- **Criterio de aceptación:**
  - Un archivo con dos filas inválidas genera un reporte con dos errores, con las líneas correctas (pytest).
  - Un archivo válido genera un reporte con `status: PROCESSED` y `errors: []` (pytest).

### RF-09 · Generar el resumen con plantilla (UC-04)

- **Descripción:** la Lambda de resúmenes consume un mensaje de SQS y hace lo siguiente:
  1. Lee el partido con su clave.
  2. Si el `data_hash` del partido no coincide con el del mensaje, descarta el mensaje: ya hay otro más nuevo en camino.
  3. Genera el texto con la plantilla según el resultado:
     - local gana: `Boca Juniors 2-1 River Plate: ganó el local (fecha 5).`
     - visitante gana: `Gimnasia 0-3 Estudiantes: ganó el visitante (fecha 5).`
     - empate: `Racing Club 0-0 Independiente: empate (fecha 5).`
  4. Escribe `summary`, `summary_status = READY`, `summary_source = template` y `summary_data_hash = data_hash`.
  - Si el mensaje falla en su último intento (`ApproximateReceiveCount` igual a `maxReceiveCount`), marca el partido con `summary_status = FAILED` antes de propagar el error, para que el mensaje quede en la DLQ.
- **Criterio de aceptación:**
  - Los tres textos de la plantilla se generan exactamente como en la descripción (pytest).
  - Un mensaje entregado dos veces deja el mismo estado y no cambia nada la segunda vez (pytest).
  - Un mensaje con un `data_hash` viejo no modifica el partido (pytest).
  - En el último intento fallido, el partido queda en `FAILED` y el mensaje va a la DLQ (pytest con un fallo simulado y la configuración de la cola).

### RF-10 · Generar el resumen con IA (solo etapa de IA; no entra en la v1)

- **Descripción:** decisión D-04: la v1 no incluye IA. Se documenta para la etapa siguiente. Si el parámetro de SSM `summary/mode` vale `ai`, la función pide el resumen a un modelo con los datos del partido (competición, temporada, fecha, equipos y goles) y nada más. La respuesta debe ser texto en español de hasta 300 caracteres, sin HTML ni saltos de línea. Si la respuesta no cumple la regla o el proveedor falla, se usa la plantilla y `summary_source = template`. Las llamadas tienen un límite diario (NFR-02).
- **Criterio de aceptación (para la etapa):**
  - Con `summary/mode = template`, no se hace ninguna llamada a un modelo (pytest con un cliente simulado).
  - Con el proveedor caído, el partido queda `READY` con texto de plantilla (pytest).
  - Una respuesta de más de 300 caracteres se descarta y se usa la plantilla (pytest).

### RF-11 · Reintentos, DLQ y alarma (UC-01, UC-04, UC-05)

- **Descripción:**
  - **Cola de resúmenes (SQS):** visibilidad de 180 segundos, `maxReceiveCount` de 3 y retención de 4 días. Al superar el máximo, el mensaje va a la DLQ.
  - **Lambdas invocadas de forma asíncrona** (ingesta por S3 y recálculo por EventBridge): AWS reintenta automáticamente (por defecto, 2 veces). Si el último intento falla, el evento va a la DLQ como destino de fallo.
  - **DLQ única** (`estadisticas-dlq`): retención de 14 días. Una alarma de CloudWatch pasa a `ALARM` cuando hay al menos 1 mensaje visible. La alarma notifica a un topic de SNS con suscripción por email (propuesta, ver sección 2.2).
  - **Errores de validación no son fallas técnicas:** un CSV inválido no reintenta ni va a la DLQ. Se resuelve con el reporte (RF-07 y RF-08).
- **Criterio de aceptación:**
  - Un mensaje que hace fallar el handler tres veces termina en la DLQ (pytest con la configuración de la cola; AWS real para el flujo completo).
  - La alarma pasa a `ALARM` en el siguiente período de evaluación (1 minuto) después de que llega un mensaje a la DLQ (AWS real).
  - Un CSV inválido no deja mensajes en la DLQ (AWS real).

### RF-12 · Consultar partidos (UC-02)

- **Descripción:** `GET /partidos` con los parámetros de la sección 8.3. Devuelve los partidos con su resumen y su estado (`summary_status`), aunque el resumen todavía no esté listo. Si se envía `matchday`, la respuesta trae todos los partidos de esa fecha (no pagina) ordenados por `match_date` y luego por `home_team`.
- **Criterio de aceptación:**
  - `GET /partidos?competition=liga-profesional&season=2026&matchday=5` devuelve todos los partidos de la fecha 5, en orden de fecha (pytest con datos cargados).
  - Sin `matchday`, con `limit=5`, devuelve 5 partidos y un `next_cursor`. Si ese cursor se envía en la siguiente llamada, devuelve los siguientes partidos sin repetir ninguno (pytest).
  - Un `cursor` alterado o inválido responde 400 `VALIDATION_ERROR` (pytest).

### RF-13 · Consultar la tabla (UC-03)

- **Descripción:** `GET /tabla` con los parámetros de la sección 8.4. Devuelve los equipos ordenados por posición. Reglas de la tabla: victoria 3 puntos, empate 1, derrota 0. Desempate en este orden: 1) puntos, 2) diferencia de goles, 3) goles a favor, 4) `team_id` en orden alfabético. Los desempates por enfrentamientos directos quedan fuera de la v1.
- Si la competición y la temporada no tienen tabla, responde 404 `SEASON_NOT_FOUND`.
- **Criterio de aceptación:**
  - Con el fixture de prueba (sección 11.2), la tabla devuelta coincide exactamente con la tabla esperada, incluidas las posiciones de los empates (pytest).
  - Una temporada sin datos responde 404 `SEASON_NOT_FOUND` (pytest).

### RF-14 · Recalcular la tabla (UC-05)

- **Descripción:** la función recorre todas las competiciones y temporadas que tienen partidos, calcula la tabla con las reglas de RF-13 y la escribe en la tabla de posiciones. Escribe los equipos actuales y borra los que ya no están en la tabla. Corre una vez por día con EventBridge a las 03:00 de Argentina (06:00 UTC). También se puede invocar a mano (sección 11.7).
- **Criterio de aceptación:**
  - La tabla calculada coincide con la tabla esperada del fixture (pytest).
  - Dos ejecuciones seguidas dejan el mismo resultado (pytest).
  - Una invocación manual en AWS real termina en menos de 10 segundos para 30 equipos (AWS real).

### RF-15 · Contrato OpenAPI publicado y validado (sección 8)

- **Descripción:** el repositorio incluye `docs/openapi.yaml` con las tres rutas, sus parámetros, sus esquemas de respuesta y sus códigos de error.
- **Criterio de aceptación:**
  - El archivo es un OpenAPI 3 válido (pytest con un validador).
  - Un test verifica que cada ruta definida en CDK aparece en el archivo y viceversa (pytest).

### RF-16 · Smoke test de la demo (sección 11.6)

- **Descripción:** el script `scripts/smoke_test.py` recibe la URL de la API y hace lo siguiente: pide una URL de subida, sube `tests/fixtures/fecha-05-valida.csv`, espera hasta 3 minutos a que los partidos aparezcan en `GET /partidos`, verifica que sus resúmenes estén en `READY`, y consulta `GET /tabla`. Devuelve código 0 si todo se cumple y un mensaje claro si algo falla.
- **Criterio de aceptación:**
  - Después de un despliegue limpio, el script termina con código 0 (AWS real).
  - Con una URL incorrecta, el script termina con código distinto de 0 y un mensaje que dice qué falló (pytest con la URL simulada).

## 5. Requisitos no funcionales

| ID | Atributo | Requisito | Cómo se verifica |
|---|---|---|---|
| NFR-01 | Costo | El gasto facturado con el uso de demo debe ser menor a USD 1 al mes (C-07). | Cost Explorer al cierre de cada mes de demo. |
| NFR-02 | Control de gasto | Presupuesto de AWS Budgets con alerta por email al llegar a USD 0,80 de gasto real y al pronóstico de USD 1 para el mes. Límites: concurrencia reservada de 2 para la ingesta; máximo 2 mensajes en paralelo para la cola de resúmenes; límite de tasa en la API de 5 solicitudes por segundo con ráfaga de 10 por ruta; cuota de 20 subidas por día (contador en DynamoDB). Si se activa la etapa de IA, máximo 50 llamadas por día. | Test de CDK sobre los límites; prueba manual de la cuota con AWS real. |
| NFR-03 | Tamaño | Máximo 1.048.576 bytes (1 MB) por archivo y 500 filas de partidos por archivo. Nombre de archivo de hasta 100 caracteres. Body de `POST /uploads` de hasta 1 KB. | RF-01, RF-02 y pytest. |
| NFR-04 | Tiempo de respuesta de la API (demo) | `GET /partidos` y `GET /tabla`: p95 de 500 ms con la Lambda ya iniciada, y hasta 3 s en arranque en frío. `POST /uploads`: p95 de 800 ms. | 50 llamadas seguidas con curl o un script contra la demo. |
| NFR-05 | Tiempo de procesamiento (demo) | Desde la subida hasta que los partidos aparecen en `GET /partidos`: menos de 60 segundos para un archivo de hasta 20 partidos. Resúmenes en `READY` en menos de 2 minutos para esos 20 partidos. | Tiempos de la demo con `scripts/smoke_test.py`. |
| NFR-06 | Seguridad | Mínimo privilegio: un rol IAM por función (sección 10.2). Ninguna política del proyecto usa `Resource: "*"` salvo las excepciones listadas en la sección 10.2. Sin secretos en el código. TLS obligatorio. | Test de CDK sobre las políticas y el bucket (sección 11.2). |
| NFR-07 | Observabilidad | Logs JSON por evento con `timestamp`, `level`, `function`, `event` y, según el caso, `upload_id`, `match_id`, `request_id`, `duration_ms` o `error_code`. Retención de logs de 7 días en todos los grupos (C-06). Alarmas: DLQ con mensajes visibles, errores de cada Lambda y errores 5xx de la API. | Test de CDK sobre retención y alarmas. Revisión de un log de ingesta real. |
| NFR-08 | Disponibilidad y tolerancia a fallos | No hay SLA. La demo debe estar disponible durante las presentaciones. Las escrituras son idempotentes (RF-05, RF-06, RF-09, RF-14). Ninguna función guarda estado entre invocaciones. | Pruebas de reintento y de mensajes duplicados (pytest con moto). |
| NFR-09 | Calidad y mantenibilidad | `ruff` sin errores. Tipado en el código de dominio. Cobertura de pytest de al menos 85 % en validación, normalización, tabla e IDs, y de 70 % en el total. Dependencias con versión fija. | `ruff check` y `pytest --cov` en la CI. |
| NFR-10 | Reproducibilidad | Todo recurso se crea con CDK. No hay cambios manuales en la consola, salvo el bootstrap de CDK y, si se usa IA, la habilitación del modelo en el proveedor (si lo requiere). Un despliegue en una cuenta limpia no necesita pasos manuales adicionales. | `cdk synth` dos veces da la misma plantilla. `cdk diff` sin cambios después de un despliegue. |
| NFR-11 | Privacidad | Los datos son estadísticas públicas de partidos. El sistema no pide ni guarda datos personales. No se habilitan los logs de acceso de API Gateway en la v1. | Revisión del modelo de datos y de la configuración de logs. |
| NFR-12 | Idioma | Mensajes de error, reportes y resúmenes en español. Identificadores, recursos y campos en inglés. | Revisión manual de las respuestas de ejemplo. |

## 6. Arquitectura

### 6.1 Diagrama

```
                  ┌──────────────── API Gateway (HTTP API) ────────────────┐
Operador  ───────►│ POST /uploads  ─► Lambda upload_url_handler ──► DynamoDB matches (cuota)
(pide la URL)     │ GET  /partidos ─► Lambda matches_handler    ──► DynamoDB matches (lectura)
Consumidor ──────►│ GET  /tabla    ─► Lambda standings_handler  ──► DynamoDB standings (lectura)
                  └─────────────────────────────────────────────────────────┘

Operador (sube el CSV con la URL firmada)
        │
        ▼
S3 bucket  incoming/<upload_id>.csv  ──(ObjectCreated)──►  Lambda ingest_handler
                                                              │
                  ┌───────────────────────────────────────────┼──────────────────────────┐
                  ▼                                           ▼                          ▼
        DynamoDB matches                          SQS estadisticas-summary      S3: processed/ | rejected/ | reports/
        (upsert de partidos)                      (un mensaje por partido)
                                                              │
                                                              ▼
                                                  Lambda summary_handler ──► DynamoDB matches (summary_*)
                                                              │  (tras 3 intentos fallidos)
                                                              ▼
                                         SQS estadisticas-dlq  ◄──  destino de fallo de Lambda ingest y standings
                                                              │
                                                              ▼
                                         Alarma CloudWatch ──► SNS (propuesto) ──► email

EventBridge (diario, 06:00 UTC) ──► Lambda standings_recalc_handler ──► lee DynamoDB matches, escribe DynamoDB standings

Todas las Lambdas ──► CloudWatch Logs (retención de 7 días)
```

### 6.2 Rol de cada componente

| Componente | Rol | Lee | Escribe | Disparado por |
|---|---|---|---|---|
| API Gateway (HTTP API) | Recibe las solicitudes HTTP, valida la ruta y aplica límites de tasa. | No | No | Solicitudes HTTP |
| `upload_url_handler` | Genera la URL firmada, aplica la cuota diaria y lee su límite de SSM. | SSM, cuota | Cuota en `matches` | `POST /uploads` |
| `matches_handler` | Devuelve partidos con su resumen. | `matches` | No | `GET /partidos` |
| `standings_handler` | Devuelve la tabla ordenada por posición. | `standings` | No | `GET /tabla` |
| S3 `incoming/` | Recibe el CSV subido. | No | CSV (por el operador) | Operador, con la URL firmada |
| `ingest_handler` | Valida, normaliza, guarda partidos, encola trabajos, archiva el CSV y escribe el reporte. | S3 (`incoming/`) | `matches`, SQS, S3 (`processed/`, `rejected/`, `reports/`) | Evento ObjectCreated |
| `summary_handler` | Genera el resumen de cada partido con la plantilla. | `matches` | `matches` (campos `summary_*`) | Mensajes de SQS |
| `standings_recalc_handler` | Recalcula la tabla de cada temporada. | `matches`, `SYSTEM#SEASONS` | `standings` | EventBridge (diario) y manual |
| SQS `estadisticas-summary` | Cola de trabajos de resumen. | No | No | `ingest_handler` |
| SQS `estadisticas-dlq` | Recibe los mensajes y eventos que fallaron definitivamente. | No | No | Redrive de la cola de resúmenes y destinos de fallo de Lambda |
| CloudWatch Logs | Guarda los logs de todas las Lambdas. | No | Logs | Lambdas |
| CloudWatch Alarms | Avisa de DLQ con mensajes, errores de Lambda y errores 5xx. | Métricas | Estado de alarma | Métricas |
| SSM Parameter Store | Guarda la configuración (sección 10.5). | Handlers, con caché de 5 minutos | No | Operador (carga manual de valores) |

### 6.3 Flujo de la ingesta

1. S3 emite `ObjectCreated` para `incoming/<upload_id>.csv`.
2. `ingest_handler` lee el objeto. Si ya no existe, termina sin error (RF-07).
3. Valida tamaño, encoding, encabezado y cantidad de filas (RF-02).
4. Normaliza cada fila (RF-03) y valida la consistencia del archivo (RF-04).
5. Si hay errores: escribe el reporte con `status: REJECTED` (RF-08), copia el archivo a `rejected/`, borra `incoming/` y termina. No escribe partidos.
6. Si es válido: hace el upsert de cada partido (RF-05) y registra la temporada en `SYSTEM#SEASONS`.
7. Encola un mensaje por cada partido cuyo resumen no corresponde a sus datos actuales (RF-06).
8. Escribe el reporte con `status: PROCESSED`, copia el archivo a `processed/` y borra `incoming/` (RF-07 y RF-08).

El orden importa: los pasos 6 y 7 se hacen antes de archivar. Si la ingesta falla después de escribir, el reintento vuelve a correr todo y el resultado es el mismo (NFR-08).

### 6.4 Funciones Lambda

| Función | Disparador | Memoria | Timeout | Concurrencia | Destino de fallo |
|---|---|---|---|---|---|
| `upload_url_handler` | `POST /uploads` | 256 MB | 10 s | Sin reservar | No aplica (respuesta síncrona) |
| `matches_handler` | `GET /partidos` | 256 MB | 10 s | Sin reservar | No aplica (respuesta síncrona) |
| `standings_handler` | `GET /tabla` | 256 MB | 10 s | Sin reservar | No aplica (respuesta síncrona) |
| `ingest_handler` | S3, prefijo `incoming/` y sufijo `.csv` | 256 MB | 60 s | Reservada: 2 | DLQ `estadisticas-dlq` |
| `summary_handler` | SQS `estadisticas-summary`, lote de 1 | 256 MB | 30 s | Máximo 2 en paralelo | Redrive a DLQ después de 3 intentos |
| `standings_recalc_handler` | EventBridge (cron) y manual | 256 MB | 60 s | Reservada: 1 | DLQ `estadisticas-dlq` |

Notas:
- Runtime: Python 3.12 o 3.13 (S-07). Los valores de memoria y timeout se ajustan con mediciones en la demo.
- El lote de 1 mensaje simplifica los reintentos: un mensaje que falla no afecta a otros.
- La concurrencia reservada depende de la cuota de Lambda de la cuenta (R-17).
- Las funciones de la API no comparten rol con las funciones que escriben (sección 10.2).
- Nombre en AWS: `estadisticas-` seguido del nombre sin el sufijo `_handler`. Por ejemplo, `estadisticas-ingest`, `estadisticas-summary`, `estadisticas-standings-recalc`, `estadisticas-upload-url`, `estadisticas-matches` y `estadisticas-standings`.

### 6.5 Recursos

| Recurso | Nombre de ejemplo | Configuración |
|---|---|---|
| Bucket S3 de CSV | `estadisticas-uploads-<account>-<region>` | Bloqueo total de acceso público. Cifrado SSE-S3. Solo TLS. Sin versionado. Reglas de ciclo de vida: `incoming/` a 1 día; `processed/`, `rejected/` y `reports/` a 30 días. |
| Tabla de partidos | `estadisticas-matches` | Clave `pk` (S) y `sk` (S). Modo on-demand. TTL sobre `expires_at`. Sin recuperación a un punto en el tiempo (ver R-10). |
| Tabla de posiciones | `estadisticas-standings` | Clave `pk` (S) y `sk` (S). Modo on-demand. |
| Cola de resúmenes | `estadisticas-summary` | Visibilidad de 180 s. Retención de 4 días. Redrive a la DLQ con `maxReceiveCount` de 3. |
| Cola de mensajes muertos | `estadisticas-dlq` | Retención de 14 días. Alarma por mensajes visibles. |
| Regla de EventBridge | `estadisticas-daily-standings` | `cron(0 6 * * ? *)`, que equivale a las 03:00 de Argentina. |
| Grupos de logs | `/aws/lambda/estadisticas-<función>` | Creados en CDK. Retención de 7 días. Se eliminan con `cdk destroy`. |
| Alarmas | `estadisticas-dlq-visible`, `estadisticas-<función>-errors`, `estadisticas-api-5xx` | DLQ: período de 1 minuto. Errores y 5xx: período de 5 minutos. |
| Topic de SNS (propuesto) | `estadisticas-alerts` | Suscripción por email del operador. |
| Presupuesto (propuesto) | `estadisticas-monthly-budget` | USD 1 al mes, con las alertas de NFR-02. |
| Parámetros de SSM | `/estadisticas/upload/daily-limit` = `20`; `/estadisticas/summary/mode` = `template` | Tipo String. Sin SecureString en la v1. |
| Rol de despliegue de GitHub | `estadisticas-github-deploy` | Asumido por OIDC (sección 10.6). |
| Proveedor OIDC de GitHub | `token.actions.githubusercontent.com` | Se crea una vez por cuenta, en un stack propio (sección 11.5). |

## 7. Modelo de datos en DynamoDB

La v1 usa dos tablas. Las dos usan modo on-demand y las claves `pk` y `sk` (ambas de tipo string). La tabla de partidos también guarda la cuota diaria y la lista de temporadas, con su propio prefijo de `pk`.

### 7.1 Tabla `estadisticas-matches`

**Claves de los partidos:**

- `pk = SEASON#<competition>#<season>`. Ejemplo: `SEASON#liga-profesional#2026`.
- `sk = MATCHDAY#<matchday con dos dígitos>#<match_id>`. Ejemplo: `MATCHDAY#05#3f9c1a0b2d4e5f60`.

**Otros registros de la misma tabla:**

- Cuota diaria: `pk = SYSTEM#QUOTA`, `sk = UPLOADS#<AAAA-MM-DD>`, con el campo `count` y `expires_at` (TTL de 2 días).
- Temporadas conocidas: `pk = SYSTEM#SEASONS`, `sk = SEASON#<competition>#<season>`, con `competition`, `season` y `updated_at`. Lo escribe la ingesta y lo lee el recálculo, así el recálculo no necesita un Scan.

**Atributos de un partido:**

| Atributo | Tipo | Ejemplo | Descripción |
|---|---|---|---|
| `match_id` | S | `3f9c1a0b2d4e5f60` | Identificador estable (sección 7.4). |
| `competition` | S | `liga-profesional` | Slug de la competición. |
| `season` | N | `2026` | Temporada. |
| `matchday` | N | `5` | Número de fecha. |
| `match_date` | S | `2026-03-14` | Fecha del partido en formato ISO. |
| `home_team_id` / `home_team` | S / S | `boca-juniors` / `Boca Juniors` | Local: slug y nombre normalizado. |
| `away_team_id` / `away_team` | S / S | `river-plate` / `River Plate` | Visitante: slug y nombre normalizado. |
| `home_goals` / `away_goals` | N / N | `2` / `1` | Goles. |
| `data_hash` | S | `9b1fe2a7c4d0...` | Hash de los datos normalizados (sección 7.4). |
| `summary_data_hash` | S | `9b1fe2a7c4d0...` | `data_hash` con el que se generó el último resumen. Puede faltar si nunca hubo resumen. |
| `summary` | S | `Boca Juniors 2-1 River Plate: ganó el local (fecha 5).` | Texto del resumen. Puede faltar si no está listo. |
| `summary_status` | S | `READY` | `PENDING`, `READY` o `FAILED`. |
| `summary_source` | S | `template` | `template` o `ai` (la etapa de IA usa `ai`). |
| `upload_id` | S | `5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e` | Último archivo que escribió este partido. |
| `updated_at` | S | `2026-03-15T12:00:00Z` | Última escritura, en UTC. |

**Ejemplo de partido** (los hashes están acortados):

```json
{
  "pk": "SEASON#liga-profesional#2026",
  "sk": "MATCHDAY#05#3f9c1a0b2d4e5f60",
  "match_id": "3f9c1a0b2d4e5f60",
  "competition": "liga-profesional",
  "season": 2026,
  "matchday": 5,
  "match_date": "2026-03-14",
  "home_team_id": "boca-juniors",
  "home_team": "Boca Juniors",
  "away_team_id": "river-plate",
  "away_team": "River Plate",
  "home_goals": 2,
  "away_goals": 1,
  "data_hash": "9b1fe2a7c4d0...",
  "summary_data_hash": "9b1fe2a7c4d0...",
  "summary": "Boca Juniors 2-1 River Plate: ganó el local (fecha 5).",
  "summary_status": "READY",
  "summary_source": "template",
  "upload_id": "5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e",
  "updated_at": "2026-03-15T12:00:00Z"
}
```

**Ejemplo de cuota diaria:**

```json
{
  "pk": "SYSTEM#QUOTA",
  "sk": "UPLOADS#2026-11-03",
  "count": 3,
  "expires_at": 1793836800
}
```

### 7.2 Tabla `estadisticas-standings`

- `pk = SEASON#<competition>#<season>`.
- `sk = TEAM#<team_id>`.

| Atributo | Tipo | Descripción |
|---|---|---|
| `team_id` | S | Slug del equipo. |
| `team` | S | Nombre normalizado para mostrar. |
| `position` | N | Posición calculada (1 es el primero). |
| `played`, `won`, `drawn`, `lost` | N | Partidos jugados, ganados, empatados y perdidos. |
| `goals_for`, `goals_against`, `goal_difference` | N | Goles a favor, en contra y diferencia. |
| `points` | N | Puntos (3, 1 y 0). |
| `computed_at` | S | Fecha y hora UTC del recálculo. |

**Ejemplo:**

```json
{
  "pk": "SEASON#liga-profesional#2026",
  "sk": "TEAM#boca-juniors",
  "team_id": "boca-juniors",
  "team": "Boca Juniors",
  "position": 1,
  "played": 5,
  "won": 3,
  "drawn": 1,
  "lost": 1,
  "goals_for": 9,
  "goals_against": 5,
  "goal_difference": 4,
  "points": 10,
  "computed_at": "2026-03-16T06:00:00Z"
}
```

### 7.3 Organización de S3

| Prefijo | Contenido | Quién escribe | Quién lee | Ciclo de vida |
|---|---|---|---|---|
| `incoming/<upload_id>.csv` | CSV recién subido, todavía sin procesar. | Operador (URL firmada) | `ingest_handler` | Se borra a 1 día (archivos que quedaron sin procesar). |
| `processed/<upload_id>.csv` | CSV válido ya procesado. | `ingest_handler` | Operador (manual) | 30 días. |
| `rejected/<upload_id>.csv` | CSV inválido. | `ingest_handler` | Operador (manual) | 30 días. |
| `reports/<upload_id>.json` | Reporte del procesamiento (RF-08). | `ingest_handler` | Operador (manual) | 30 días. |

### 7.4 Identificadores y hashes

- **`competition`**: slug de la competición (RF-03). Ejemplo: `Liga Profesional` → `liga-profesional`.
- **`team_id`**: slug del nombre del equipo, sin tildes. Ejemplo: `Vélez Sarsfield` → `velez-sarsfield`. Dos nombres que dan el mismo slug se consideran el mismo equipo.
- **`match_id`**: los primeros 16 caracteres hexadecimales del SHA-256 de la cadena `competition|season|matchday|home_team_id|away_team_id`. El orden de local y visitante importa.
- **`data_hash`**: SHA-256 en hexadecimal completo del JSON canónico (claves ordenadas, sin espacios) con `match_date`, `home_team`, `away_team`, `home_goals` y `away_goals`.
- **`upload_id`**: UUID v4 generado por `upload_url_handler`.

### 7.5 Patrones de acceso

| Operación | Clave o consulta | Tipo | Notas |
|---|---|---|---|
| Partidos de una fecha | `pk = SEASON#c#s` y `sk` empieza con `MATCHDAY#05#` | Query | Una fecha tiene como máximo 50 partidos en la v1 (no pagina). |
| Partidos de una temporada, paginado | `pk = SEASON#c#s` | Query con `Limit` y `ExclusiveStartKey` | El `next_cursor` es el `LastEvaluatedKey` codificado en base64url. |
| Escribir un partido | `pk` y `sk` | UpdateItem (upsert) con condición | Usa `ReturnValues = ALL_OLD` para comparar `summary_data_hash` (RF-06). |
| Leer un partido para su resumen | `pk` y `sk` | GetItem | El mensaje trae `competition`, `season` y `matchday` para armar la clave. |
| Marcar un resumen como listo | `pk` y `sk` | UpdateItem con condición `data_hash = :expected` | Evita pisar un dato más nuevo (RF-09). |
| Leer la tabla | `pk = SEASON#c#s` y `sk` empieza con `TEAM#` | Query | El handler ordena por `position`. |
| Listar temporadas | `pk = SYSTEM#SEASONS` | Query | Lo usa el recálculo para no hacer Scan. |
| Recalcular una temporada | Query de la partición de la temporada | Query | Escribe `standings` y borra los equipos que ya no están (RF-14). |
| Cuota diaria | `pk = SYSTEM#QUOTA` y `sk = UPLOADS#<fecha>` | UpdateItem con `ADD count :1` | Operación atómica. Límite en NFR-02. |

## 8. Contrato de la API

### 8.1 Convenciones

- **Base URL:** `https://<api-id>.execute-api.us-east-1.amazonaws.com`. Las rutas no tienen prefijo: `/uploads`, `/partidos` y `/tabla`.
- **Formato:** JSON en UTF-8. Las fechas de partido van en `YYYY-MM-DD`. Los momentos (`updated_at`, `computed_at`) van en ISO 8601 UTC.
- **Errores:** todas las respuestas de error de las funciones tienen este formato:

  ```json
  {"error": {"code": "VALIDATION_ERROR", "message": "El parámetro season debe ser un año entre 2000 y 2100.", "request_id": "c6af9ac6-7b61-11e6-9a41-93e8deadbeef"}}
  ```

  El mensaje va en español y nunca incluye trazas ni detalles internos. El mismo `request_id` va en el header `X-Request-Id`.
- **Autenticación:** `GET /partidos` y `GET /tabla` son públicas. `POST /uploads` exige firma IAM (SigV4) con permiso para invocar la API (sección 10.1).
- **Límite de tasa:** 5 solicitudes por segundo, con ráfaga de 10, en cada ruta (NFR-02).
- **Documentación:** la especificación completa está en `docs/openapi.yaml` (RF-15).

### 8.2 `POST /uploads`

**Request:**

```json
{"filename": "fecha-05.csv", "content_type": "text/csv"}
```

| Campo | Obligatorio | Regla |
|---|---|---|
| `filename` | Sí | Texto de 1 a 96 caracteres seguido de `.csv`. Solo letras, números, puntos, guiones y guiones bajos. |
| `content_type` | Sí | Debe ser `text/csv`. |

El body no puede pesar más de 1 KB. Cualquier campo que no esté en la tabla responde 400.

**Response 201:**

```json
{
  "upload_id": "5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e",
  "expires_in": 300,
  "upload": {
    "url": "https://estadisticas-uploads-123456789012-us-east-1.s3.amazonaws.com/",
    "fields": {
      "key": "incoming/5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e.csv",
      "Content-Type": "text/csv",
      "policy": "eyJleHBpcmF0aW9uIjogIi4uLiJ9...",
      "x-amz-algorithm": "AWS4-HMAC-SHA256",
      "x-amz-credential": "AKIA.../20261103/us-east-1/s3/aws4_request",
      "x-amz-date": "20261103T120000Z",
      "x-amz-signature": "3c9f..."
    }
  }
}
```

Para subir el archivo, el operador hace un POST `multipart/form-data` a `upload.url` con todos los `fields` como campos de formulario y, en último lugar, el archivo en el campo `file`:

```bash
curl -i -X POST "$UPLOAD_URL" \
  -F "key=$KEY" \
  -F "Content-Type=text/csv" \
  -F "policy=$POLICY" \
  -F "x-amz-algorithm=AWS4-HMAC-SHA256" \
  -F "x-amz-credential=$CREDENTIAL" \
  -F "x-amz-date=$DATE" \
  -F "x-amz-signature=$SIGNATURE" \
  -F "file=@fecha-05.csv"
```

S3 responde 204 si la subida fue aceptada. La URL vence a los 300 segundos.

**Errores:**

| HTTP | `error.code` | Cuándo |
|---|---|---|
| 400 | `VALIDATION_ERROR` | `filename` o `content_type` inválidos, o campos desconocidos. |
| 403 | No aplica (lo responde API Gateway) | Falta la firma IAM. |
| 413 | `PAYLOAD_TOO_LARGE` | El body pesa más de 1 KB. |
| 429 | `DAILY_QUOTA_EXCEEDED` | Se alcanzó la cuota diaria (20 subidas en la v1). |
| 500 | `INTERNAL_ERROR` | Falla no controlada. |

### 8.3 `GET /partidos`

**Parámetros:**

| Parámetro | Obligatorio | Formato | Por defecto | Descripción |
|---|---|---|---|---|
| `competition` | Sí | Slug de 2 a 40 caracteres: `^[a-z0-9]+(-[a-z0-9]+)*$` | Ninguno | Competición. |
| `season` | Sí | Entero entre 2000 y 2100 | Ninguno | Temporada. |
| `matchday` | No | Entero entre 1 y 99 | Ninguno | Si viene, devuelve toda la fecha sin paginar. |
| `limit` | No | Entero entre 1 y 50 | 20 | Cantidad de partidos por página. Solo sin `matchday`. |
| `cursor` | No | Texto base64url de hasta 512 caracteres | Ninguno | Viene de `next_cursor`. Solo sin `matchday`. |

**Response 200:**

```json
{
  "items": [
    {
      "match_id": "3f9c1a0b2d4e5f60",
      "competition": "liga-profesional",
      "season": 2026,
      "matchday": 5,
      "match_date": "2026-03-14",
      "home_team": "Boca Juniors",
      "away_team": "River Plate",
      "home_goals": 2,
      "away_goals": 1,
      "summary_status": "READY",
      "summary": "Boca Juniors 2-1 River Plate: ganó el local (fecha 5)."
    }
  ],
  "next_cursor": null
}
```

`summary` es `null` mientras `summary_status` no sea `READY`. `next_cursor` es `null` cuando no hay más páginas.

**Errores:** 400 `VALIDATION_ERROR` si un parámetro es inválido o el cursor no se puede decodificar. Una lista vacía responde 200.

### 8.4 `GET /tabla`

**Parámetros:** `competition` y `season`, con el mismo formato que en `GET /partidos`. Ambos son obligatorios.

**Response 200:**

```json
{
  "competition": "liga-profesional",
  "season": 2026,
  "computed_at": "2026-03-16T06:00:00Z",
  "items": [
    {"position": 1, "team": "Boca Juniors", "team_id": "boca-juniors", "played": 5, "won": 3, "drawn": 1, "lost": 1, "goals_for": 9, "goals_against": 5, "goal_difference": 4, "points": 10},
    {"position": 2, "team": "River Plate", "team_id": "river-plate", "played": 5, "won": 2, "drawn": 1, "lost": 2, "goals_for": 6, "goals_against": 7, "goal_difference": -1, "points": 7}
  ]
}
```

**Errores:**

| HTTP | `error.code` | Cuándo |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Parámetro obligatorio faltante o inválido. |
| 404 | `SEASON_NOT_FOUND` | No hay tabla para esa competición y temporada. |

### 8.5 Códigos de error en resumen

| Código | Significado |
|---|---|
| `VALIDATION_ERROR` | Un parámetro, un campo o un cursor no cumple el formato. |
| `SEASON_NOT_FOUND` | No hay tabla para la competición y la temporada pedidas. |
| `PAYLOAD_TOO_LARGE` | El body supera el tamaño permitido. |
| `DAILY_QUOTA_EXCEEDED` | Se alcanzó la cuota diaria de subidas. |
| `INTERNAL_ERROR` | Falla no controlada. Se registra con `request_id`. |

Los errores 403 (firma IAM) y 404 de ruta inexistente los responde API Gateway con su propio formato, y los 429 por límite de tasa también.

## 9. Eventos y mensajes

### 9.1 Disparador de S3

- **Evento:** `s3:ObjectCreated:*` sobre el bucket de CSV.
- **Filtro:** prefijo `incoming/` y sufijo `.csv`. Así, los objetos que la propia ingesta escribe en `processed/`, `rejected/` o `reports/` no disparan la función de nuevo.
- **Datos del evento usados:** `bucket.name`, `object.key` (de ahí sale el `upload_id`) y `object.size`.
- **Entrega:** S3 entrega al menos una vez. La ingesta tiene que ser idempotente (sección 9.6).
- **Reintentos:** al ser asíncrono, AWS reintenta 2 veces. Si el último intento falla, el evento va a la DLQ.

### 9.2 Disparador de EventBridge

- **Regla:** `estadisticas-daily-standings`.
- **Expresión:** `cron(0 6 * * ? *)`, que equivale a las 03:00 hora de Argentina (UTC-3). EventBridge trabaja en UTC.
- **Entrada:** `{}`. El recálculo siempre recorre todas las temporadas registradas en `SYSTEM#SEASONS`.
- **Reintentos:** igual que S3, de forma asíncrona. Si el último intento falla, el evento va a la DLQ.
- **Invocación manual:** la misma función, desde la línea de comandos (sección 11.7).

### 9.3 Mensaje de SQS (`estadisticas-summary`)

Cada mensaje pide el resumen de un partido. El cuerpo es un JSON pequeño, sin nombres de equipos: el consumidor los lee de la tabla.

```json
{
  "schema_version": 1,
  "type": "match.summary.requested",
  "match_id": "3f9c1a0b2d4e5f60",
  "competition": "liga-profesional",
  "season": 2026,
  "matchday": 5,
  "data_hash": "9b1fe2a7c4d0...",
  "upload_id": "5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e",
  "requested_at": "2026-03-15T12:00:00Z"
}
```

- **Tipo de cola:** estándar (no FIFO). El consumidor es idempotente (RF-09), así que el orden y los duplicados no rompen nada, y la cola es más barata y más simple.
- **Tamaño:** menos de 1 KB, muy por debajo del límite de SQS.
- **Validación:** `schema_version` debe ser 1 y `type` debe ser `match.summary.requested`. Un mensaje que no cumple eso lanza excepción: se reintenta, y tras 3 intentos va a la DLQ para que quede visible (sección 10.4).

### 9.4 Reintentos, DLQ y alarmas

| Origen | Reintentos automáticos | Destino después del último intento | Alarma |
|---|---|---|---|
| `summary_handler` (SQS) | 3 recepciones (`maxReceiveCount`), con visibilidad de 180 s entre intentos. | DLQ `estadisticas-dlq`. | `estadisticas-dlq-visible`: al menos 1 mensaje visible, período de 1 minuto. |
| `ingest_handler` (S3, asíncrono) | 2 reintentos de Lambda. | DLQ `estadisticas-dlq` (destino de fallo). | La misma alarma de la DLQ. |
| `standings_recalc_handler` (EventBridge, asíncrono) | 2 reintentos de Lambda. | DLQ `estadisticas-dlq` (destino de fallo). | La misma alarma de la DLQ. |
| Cualquier Lambda | No aplica. | No aplica. | `estadisticas-<función>-errors`: al menos 1 error en 5 minutos. |
| API Gateway | No aplica. | No aplica. | `estadisticas-api-5xx`: al menos 5 errores 5xx en 5 minutos. |

- **Notificación:** las alarmas publican en el topic `estadisticas-alerts` (propuesto), con suscripción por email del operador. Si no se aprueba SNS, las alarmas quedan visibles solo en la consola de CloudWatch. Eso no es recomendable: nadie se entera de un fallo.
- **Qué hacer cuando salta la alarma:** revisar la DLQ en la consola de SQS, leer el log de la función que falló (sección 11.7) y, si el problema se corrigió, reenviar el mensaje con el redrive de SQS.

### 9.5 Errores de validación frente a errores técnicos

| Tipo | Ejemplos | Qué hace el sistema |
|---|---|---|
| Validación | CSV con filas inválidas, parámetros de API fuera de rango, un cursor corrupto. | No lanza excepción. Responde 400 o escribe el reporte con `REJECTED`. No reintenta y no va a la DLQ. |
| Técnica transitoria | Throttling de DynamoDB, timeout de red, falla momentánea de S3 o SQS. | Lanza excepción. AWS reintenta (asíncrono o nueva recepción de SQS). Si persiste, va a la DLQ. |
| Técnica permanente | Bug en el código, esquema de mensaje no reconocido. | Lanza excepción. Se reintenta el máximo y va a la DLQ. La alarma avisa al operador. |
| Dato obsoleto | Mensaje de resumen con un `data_hash` que ya no coincide. | No es un error: se descarta y se registra con `event: summary_skipped_stale`. |

Regla para los handlers: un error de validación nunca se convierte en excepción; una falla técnica siempre se propaga.

### 9.6 Idempotencia por evento

| Evento | Riesgo | Cómo se resuelve |
|---|---|---|
| S3 entrega el mismo `ObjectCreated` dos veces. | Procesar el CSV dos veces. | El primer intento archiva el objeto; el segundo no encuentra el original y termina sin cambios (RF-07). Aun así, los upserts son idempotentes (RF-05). |
| SQS entrega el mismo mensaje dos veces. | Dos resúmenes del mismo partido. | El consumidor compara `data_hash` y usa una escritura condicional (RF-09). |
| La ingesta falla a mitad de las escrituras. | Partidos a medio guardar. | El reintento completa el trabajo: `match_id` es determinístico y el upsert no duplica (RF-05). |
| La ingesta escribe el partido, pero el envío a SQS falla. | Resumen que nunca se genera. | `summary_data_hash` no coincide, así que el reintento vuelve a enviar el mensaje (RF-06). |
| El recálculo corre dos veces. | Tabla duplicada o inconsistente. | El recálculo reemplaza la tabla completa; el resultado es el mismo (RF-14). |
| El cliente repite `POST /uploads`. | La cuota se consume más rápido. | Es el comportamiento esperado: la cuota cuenta solicitudes, no archivos. |

## 10. Seguridad

### 10.1 Autenticación y autorización de la API

- **`GET /partidos` y `GET /tabla`:** públicas. Solo leen datos públicos, y tienen límite de tasa (NFR-02).
- **`POST /uploads`:** requiere firma IAM (SigV4). La ruta usa autorización `AWS_IAM`. Solo la identidad del operador (un usuario o rol de IAM) tiene `execute-api:Invoke` sobre esa ruta.
- **Por qué IAM:** las HTTP API no soportan API keys. Un autorizador Lambda con un token suma una función y un secreto que hay que rotar. IAM no tiene costo extra y no deja secretos en el repo.
- **Criterio de aceptación:** una solicitud sin firma a `POST /uploads` responde 403. Una solicitud firmada con la identidad del operador responde 201 (AWS real).

### 10.2 Roles IAM por función

Cada función tiene su propio rol. Ningún rol comparte permisos con otro. Todas las funciones escriben logs solo en su propio grupo (`logs:CreateLogStream` y `logs:PutLogEvents` sobre ese grupo).

| Rol | Permisos | Recursos |
|---|---|---|
| `estadisticas-upload-url-role` | `dynamodb:UpdateItem` para la cuota diaria. `s3:PutObject` para firmar la subida. `ssm:GetParameter` para el límite diario. | Tabla `estadisticas-matches` con la condición `dynamodb:LeadingKeys = SYSTEM#QUOTA`. Bucket en `incoming/*`. Parámetros `/estadisticas/upload/*`. |
| `estadisticas-matches-role` | `dynamodb:Query`. | Tabla `estadisticas-matches`. |
| `estadisticas-standings-role` | `dynamodb:Query`. | Tabla `estadisticas-standings`. |
| `estadisticas-ingest-role` | `s3:GetObject` y `s3:DeleteObject` sobre `incoming/*`. `s3:PutObject` sobre `processed/*`, `rejected/*` y `reports/*`. `dynamodb:GetItem`, `dynamodb:UpdateItem` y `dynamodb:PutItem` sobre `estadisticas-matches` con `LeadingKeys` en `SEASON#*` y `SYSTEM#SEASONS` (GetItem para comparar el resumen, PutItem para registrar la temporada). `sqs:SendMessage` sobre la cola de resúmenes y sobre la DLQ (destino de fallo). | Bucket y prefijos indicados. Tabla de partidos. Cola `estadisticas-summary` y `estadisticas-dlq`. |
| `estadisticas-summary-role` | `dynamodb:GetItem` y `dynamodb:UpdateItem` sobre partidos. Recepción de mensajes de la cola (SQS la configura en el mapeo). | Tabla `estadisticas-matches`. Cola `estadisticas-summary`. |
| `estadisticas-standings-recalc-role` | `dynamodb:Query` sobre partidos y sobre `SYSTEM#SEASONS`. `dynamodb:Query` y `dynamodb:BatchWriteItem` sobre standings (el reemplazo de la tabla usa escrituras por lotes). `sqs:SendMessage` sobre la DLQ (destino de fallo). | Tablas `estadisticas-matches` y `estadisticas-standings`. DLQ. |
| `estadisticas-github-deploy` (fuera de las funciones) | `sts:AssumeRole` sobre los roles de bootstrap de CDK. | Roles `cdk-hnb659fds-*`. Ver sección 10.6. |

**Excepciones a `Resource: "*"`:** ninguna en la v1. Si se activa la etapa de IA con API externa, habrá una excepción: `kms:Decrypt` sobre la clave administrada `aws/ssm`, limitada con la condición `kms:ViaService = ssm.us-east-1.amazonaws.com` (sección 10.5).

**Limitación de IAM:** IAM no puede limitar qué atributos de un ítem se escriben. Por eso el `summary_handler` tiene `dynamodb:UpdateItem` sobre toda la tabla de partidos, pero el código solo escribe los campos `summary_*`. Eso se verifica con una prueba (pytest).

### 10.3 Datos y cifrado

- **S3:** bloqueo total de acceso público. Cifrado SSE-S3 (administrado por AWS). Una política de bucket rechaza cualquier solicitud sin TLS (`aws:SecureTransport` igual a `false`). Sin ACL públicas.
- **DynamoDB:** cifrado en reposo con la clave administrada por AWS. No se crean claves propias (C-04).
- **SQS:** cifrado administrado por AWS. No se crean claves propias.
- **URLs firmadas:** vencen a los 300 segundos y tienen condiciones de tamaño y tipo (RF-01). Los logs registran el `upload_id`, nunca la URL firmada.
- **Logs:** no contienen el contenido del CSV, las firmas ni los valores de los parámetros sensibles.
- **Variables de entorno de las funciones:** solo nombres de tablas, colas y parámetros. Ningún valor secreto.

### 10.4 Validación de entrada

| Entrada | Validación | Dónde se hace |
|---|---|---|
| Parámetros de query (`competition`, `season`, `matchday`, `limit`, `cursor`) | Formato con expresión regular y rangos. El cursor se decodifica con un límite de 512 caracteres y debe tener la forma esperada. | `matches_handler`, `standings_handler`. |
| Body de `POST /uploads` | Tamaño máximo de 1 KB, JSON válido, campos conocidos, `filename` con expresión regular, `content_type` fijo en `text/csv`. | `upload_url_handler`. |
| Archivo CSV | Tamaño, encoding, encabezado, cantidad de filas, reglas de negocio (RF-02 a RF-04), longitud de textos, rangos numéricos y de fecha. | `ingest_handler`. |
| Mensaje de SQS | `schema_version` y `type` (sección 9.3). | `summary_handler`. |

**Inyección en hojas de cálculo:** en la v1 los datos se guardan como texto y se devuelven como JSON. Ningún campo se interpreta como fórmula. Si en el futuro se exporta a CSV, los valores que empiezan con `=`, `+`, `-` o `@` hay que escaparlos.

### 10.5 Configuración y secretos

- **SSM Parameter Store, tipo String:** configuración no sensible, como el límite diario de subidas (`/estadisticas/upload/daily-limit`) y el modo del resumen (`/estadisticas/summary/mode`). Las funciones leen estos valores con una caché en memoria de 5 minutos.
- **SecureString, solo si se activa la etapa de IA con API externa:** la clave del proveedor va en SSM como SecureString, cifrada con la clave administrada `aws/ssm`. No se crea ninguna clave KMS propia (C-04). El valor nunca se escribe en un log.
- **Repositorio y CI:** ningún secreto en el código ni en el repositorio. El ARN del rol de despliegue y el ID de cuenta se guardan como variables de GitHub, porque no son secretos.

### 10.6 Despliegue seguro con GitHub OIDC

- **Proveedor OIDC:** `token.actions.githubusercontent.com`, creado una vez por cuenta en `EstadisticasBaseStack`.
- **Política de confianza del rol `estadisticas-github-deploy`:**
  - `token.actions.githubusercontent.com:aud` igual a `sts.amazonaws.com`.
  - `token.actions.githubusercontent.com:sub` igual a `repo:<owner>/<repo>:ref:refs/heads/main`. Solo la rama `main` puede asumir el rol.
- **Pull requests:** no asumen el rol. Solo corren pruebas y `cdk synth`, sin credenciales de AWS.
- **Permisos del rol:** solo `sts:AssumeRole` sobre los roles de bootstrap de CDK (`cdk-hnb659fds-*`).
- **Permisos del bootstrap:** por defecto, CDK asigna permisos de administrador al rol de ejecución de CloudFormation. Recomendado: usar `--cloudformation-execution-policies` con una política acotada a los servicios del proyecto (R-08).
- **Credenciales de larga duración:** ninguna. No hay `AWS_ACCESS_KEY_ID` ni `AWS_SECRET_ACCESS_KEY` en GitHub.
- **Criterio de aceptación:** la política de confianza contiene las dos condiciones (test de CDK). Un workflow que corre desde otra rama no puede asumir el rol (revisión manual con un intento fallido en una rama de prueba).

## 11. Pruebas y despliegue

### 11.1 Estrategia de pruebas

| Nivel | Qué prueba | Herramientas | Dónde corre |
|---|---|---|---|
| Unitarias | Validación, normalización, IDs y hashes, plantilla del resumen, cálculo de tabla, cursor, validación del body. | pytest | Local y CI. |
| Integración con AWS simulado | Ingesta completa (S3, DynamoDB, SQS, reportes). Consumidor de resúmenes. Recálculo de tabla. Handlers de la API con eventos de API Gateway HTTP v2. | pytest y moto. | Local y CI. |
| Infraestructura | Plantilla de CDK: sin recursos prohibidos, logs con 7 días, alarmas presentes, políticas sin `*` (salvo excepciones), bucket sin acceso público, condiciones del rol OIDC. | pytest y `aws_cdk.assertions`. | Local y CI. |
| Contrato | `docs/openapi.yaml` es válido y coincide con las rutas de CDK. | pytest y un validador de OpenAPI. | CI. |
| Calidad | Lint y formato. | ruff. | CI. |
| Dependencias | Vulnerabilidades conocidas. | pip-audit (recomendado). | CI. |
| Extremo a extremo | Smoke test contra la demo desplegada. | `scripts/smoke_test.py`. | Manual después del despliegue. |

**Límites de moto (R-14):** moto no valida firmas de presigned POST, no simula schedules de EventBridge ni los destinos de fallo de Lambda. Esas partes se prueban con pruebas de configuración (CDK) y en AWS real (smoke test y verificación manual).

### 11.2 Casos de prueba clave

| ID | Caso | Requisitos |
|---|---|---|
| T-01 | Archivo válido de 5 partidos (`tests/fixtures/fecha-05-valida.csv`): 5 partidos guardados, 5 mensajes encolados, reporte `PROCESSED` y archivo en `processed/`. | RF-02 a RF-08 |
| T-02 | Archivo sin la columna `away_goals`: `REJECTED` con `HEADER_MISSING_COLUMN`, 0 partidos. | RF-02, RF-08 |
| T-03 | Fecha `2026-3-14` en una fila: `DATE_INVALID` con la línea correcta. | RF-03, RF-08 |
| T-04 | Goles `3.0`: `GOALS_INVALID`. | RF-03 |
| T-05 | Dos competiciones en el mismo archivo: `MIXED_MATCHDAY`. | RF-04 |
| T-06 | Un equipo juega dos veces en la misma fecha: `TEAM_REPEATED_IN_MATCHDAY`. | RF-04 |
| T-07 | Subir dos veces el mismo archivo: la segunda vez no crea partidos ni mensajes. | RF-05, RF-06 |
| T-08 | Cambiar un resultado: 1 mensaje, el partido pasa a `PENDING` y después a `READY` con el texto nuevo. | RF-05, RF-06, RF-09 |
| T-09 | Evento S3 duplicado: termina sin error y sin cambios. | RF-07 |
| T-10 | Mensaje de resumen con un `data_hash` viejo: se descarta sin modificar el partido. | RF-09 |
| T-11 | Fallo permanente en `summary_handler`: 3 intentos, luego la DLQ, y el partido queda en `FAILED`. | RF-09, RF-11 |
| T-12 | Tabla de 4 equipos (`tests/fixtures/tabla/`, un archivo por fecha): posiciones esperadas, incluido el desempate por goles a favor. | RF-13, RF-14 |
| T-13 | Paginación de `GET /partidos` con `cursor`: ninguna página repite partidos. | RF-12 |
| T-14 | `GET /tabla` de una temporada inexistente: 404 `SEASON_NOT_FOUND`. | RF-13 |
| T-15 | `POST /uploads` con `filename` `fecha.txt`: 400 `VALIDATION_ERROR`. | RF-01 |
| T-16 | Plantilla de CDK: sin recursos prohibidos, logs con 7 días, alarma de la DLQ presente, bucket sin acceso público. | C-01, C-06, RF-11, NFR-06 |

### 11.3 Entornos y región

- **Un solo entorno, `demo`,** en la cuenta de AWS del operador. No hay entornos de desarrollo y producción separados, por costo y alcance.
- **Región:** `us-east-1` (S-02, R-09).
- **Stacks de CDK:**
  - `EstadisticasBaseStack`: proveedor OIDC, rol de despliegue y presupuesto. Se despliega una vez, a mano. Así, destruir la aplicación no rompe el pipeline.
  - `EstadisticasAppStack`: el resto de los recursos (API, Lambdas, tablas, colas, bucket, alarmas, topic de SNS, parámetros de SSM). Lo despliega el pipeline.
- **Pruebas sin AWS real:** las pruebas unitarias y de integración no usan credenciales ni recursos de AWS. Solo `cdk synth` (sin credenciales) y el smoke test usan AWS.

### 11.4 Pipeline de GitHub Actions

- **`ci.yml`** (pull requests y push a `main`): instala dependencias, corre `ruff check`, `pytest --cov` y `cdk synth`. No usa credenciales de AWS.
- **`deploy.yml`** (push a `main` o disparo manual): corre primero las pruebas de `ci.yml`. Después, con `permissions: id-token: write` y `contents: read`, asume el rol `estadisticas-github-deploy` por OIDC y ejecuta `cdk deploy EstadisticasAppStack --require-approval never`.
- **Reglas:** permisos mínimos por job, acciones fijadas por versión (recomendado: por SHA), y sin `pull_request_target`.

### 11.5 Primer despliegue

1. Crear la cuenta de AWS y verificar los créditos del plan gratuito de cuenta nueva.
2. Activar MFA en el usuario root. Crear un usuario o rol de operador con MFA, y usarlo para todo lo demás.
3. Revisar en la consola de Billing los créditos disponibles y la fecha en que termina el plan gratuito.
4. Instalar AWS CLI y CDK. Autenticarse con el operador (solo en la máquina local).
5. Hacer `cdk bootstrap` en `us-east-1`, con la política de ejecución acotada (sección 10.6).
6. Desplegar `EstadisticasBaseStack`. Crea el proveedor OIDC, el rol de despliegue y el presupuesto de AWS Budgets (propuesto). Conviene que el presupuesto exista antes de desplegar la aplicación.
7. Cargar en GitHub las variables `AWS_ACCOUNT_ID`, `AWS_REGION` y `AWS_DEPLOY_ROLE_ARN`.
8. Hacer push a `main`, para que `deploy.yml` despliegue `EstadisticasAppStack`.
9. Tomar la URL de la API de los outputs del stack y correr el smoke test (sección 11.6).
10. Revisar en la consola: alarmas en `OK`, grupos de logs con retención de 7 días y presupuesto activo.

### 11.6 Smoke test

```bash
python scripts/smoke_test.py --api-url "https://<api-id>.execute-api.us-east-1.amazonaws.com"
```

El script usa las credenciales del operador para firmar `POST /uploads` (SigV4). Hace lo descrito en RF-16 y muestra el tiempo de cada etapa. Si todo pasa, termina con código 0 y la línea `OK`.

### 11.7 Operación manual

- **Recalcular la tabla a mano:**

  ```bash
  aws lambda invoke --function-name estadisticas-standings-recalc --region us-east-1 salida.json
  ```

- **Ver los logs de una ingesta:**

  ```bash
  aws logs tail /aws/lambda/estadisticas-ingest --since 1h --region us-east-1
  ```

- **Ver el reporte de un archivo:**

  ```bash
  aws s3 cp s3://<bucket>/reports/<upload_id>.json - --region us-east-1
  ```

- **Reprocesar un archivo rechazado** (después de corregirlo, subirlo con el mismo `upload_id`): copiar el archivo a `incoming/`. El evento de S3 dispara la ingesta de nuevo, y como es idempotente, no duplica nada.

  ```bash
  aws s3 cp s3://<bucket>/rejected/<upload_id>.csv s3://<bucket>/incoming/<upload_id>.csv --region us-east-1
  ```

- **Revisar la DLQ:** en la consola de SQS, usar "Poll for messages" sobre `estadisticas-dlq`. Para reenviar mensajes a su cola de origen, usar el redrive de SQS desde la consola.

### 11.8 Cómo se borra todo

1. Destruir la aplicación: `cdk destroy EstadisticasAppStack`. Las tablas, el bucket y los grupos de logs se crean con política de borrado `DESTROY`, así que el stack los elimina. El bucket se vacía antes con `autoDeleteObjects`, que crea una función auxiliar de CDK de costo mínimo. Las colas, las Lambdas y la API se borran como parte del stack.
2. Si ya no hace falta el pipeline: `cdk destroy EstadisticasBaseStack`. El proveedor OIDC es de toda la cuenta: si otro proyecto lo usa, no lo borres.
3. Lo que CDK no borra: el stack `CDKToolkit` y su bucket de assets (`cdk-hnb659fds-assets-<cuenta>-us-east-1`). Vaciar el bucket y borrar el stack desde la consola de CloudFormation.
4. Revisar la consola en `us-east-1`: buckets de S3, tablas, colas, grupos de logs, alarmas, topic de SNS, parámetros de SSM, presupuesto y el rol de operador.
5. Revisar Cost Explorer al día siguiente. Los cargos aparecen con demora.
6. En GitHub, borrar las variables cargadas en el paso 7 de la sección 11.5 si el proyecto se cierra.

## 12. Costos y control de gasto

### 12.1 Objetivo

Menos de USD 1 al mes con el uso de demo (C-07 y NFR-01). El costo se controla con tres cosas: la capa gratuita de los servicios, los créditos de la cuenta nueva y un presupuesto con alertas. Mientras el plan gratuito de 6 meses esté vigente, la estimación es que el gasto facturado sea cercano a cero.

### 12.2 Datos verificados

| Dato | Valor | Estado |
|---|---|---|
| Plan gratuito de cuentas nuevas | Dura 6 meses. | [verificado, dato aportado en el pedido] |
| Créditos de cuenta nueva | USD 100 a 200. | [verificado, dato aportado en el pedido] |
| API Gateway HTTP API | 1 millón de llamadas gratis por mes durante 12 meses. | [verificado, dato aportado en el pedido] |
| Athena | USD 5 por TB escaneado. | [verificado, dato aportado en el pedido] |
| S3 Vectors | Disponible desde diciembre de 2025. | [verificado, dato aportado en el pedido] |

Antes de crear la cuenta, hay que confirmar estos datos en la página oficial de AWS, porque cambian con el tiempo.

### 12.3 Estimaciones (sin verificar)

Los precios de SQS, DynamoDB, CloudWatch y los demás servicios no están verificados. Todo lo que sigue es una estimación. Antes de implementar hay que cargar el uso previsto en la calculadora de precios de AWS.

| Servicio | Uso previsto en demo | Costo estimado | Nota |
|---|---|---|---|
| S3 | Menos de 1 MB por fecha, decenas de objetos al mes. | Cercano a cero [estimación] | Almacenamiento y solicitudes mínimos. |
| Lambda | Cientos de invocaciones al mes. | Cercano a cero [estimación] | Se espera que quede dentro de la capa gratuita. |
| SQS | Decenas de mensajes por fecha. | Cercano a cero [estimación] | Mensajes pequeños. |
| DynamoDB (on-demand) | Miles de lecturas y escrituras al mes. | Cercano a cero [estimación] | El upsert de partidos es la mayor parte del tráfico de escritura. |
| EventBridge | Una regla diaria (unas 30 invocaciones al mes). | Cercano a cero [estimación] | |
| CloudWatch Logs | Decenas de MB al mes con nivel INFO. | Bajo, pero es lo que más crece si los logs son verbosos [estimación] | Retención de 7 días (C-06). |
| CloudWatch Alarms | Entre 3 y 5 alarmas. | Centavos de dólar por alarma al mes [estimación] | Mantener el número bajo. |
| SNS (propuesto) | Pocos emails. | Cercano a cero [estimación] | |
| AWS Budgets (propuesto) | Un presupuesto. | Depende de la cantidad de presupuestos [estimación] | Verificar si el primer presupuesto tiene costo. |
| SSM Parameter Store | Dos parámetros estándar. | Sin costo en parámetros estándar [estimación] | Verificar. |
| CloudFormation y CDK | Stacks y bucket de assets de CDK. | Cercano a cero [estimación] | El bootstrap crea un bucket de assets. |
| Amazon Bedrock (etapa 2) | Pocas decenas de llamadas por fecha. | No se estima en la v1 | Se cobra por token. Requiere precio verificado. |
| Athena (si se suma, D-03) | Consultas sobre archivos de pocos MB. | Mínimo, pero con cargo por consulta [estimación] | Cobro de USD 5 por TB escaneado (dato verificado). |

### 12.4 Qué puede disparar la cuenta

| Causa | Efecto | Control |
|---|---|---|
| Subidas grandes o muchas subidas. | Costo de S3, de la ingesta y de los reintentos. | Límite de 1 MB en la firma, cuota de 20 subidas por día y límite de tasa (NFR-02 y NFR-03). |
| Bucle de eventos (S3 → Lambda → S3). | Invocaciones sin fin. | Filtro de prefijo `incoming/`, la ingesta escribe fuera de ese prefijo y concurrencia reservada de 2. |
| Reintentos sin fin en SQS. | Mensajes repetidos. | `maxReceiveCount` de 3 y DLQ con alarma. |
| Logs verbosos o con contenido grande. | Costo de CloudWatch. | Nivel INFO, retención de 7 días y ningún log con el CSV completo (NFR-07). |
| Alarmas o métricas personalizadas de más. | Costo fijo mensual. | Solo las alarmas de la sección 9.4. |
| Tráfico de la API. | Invocaciones y transferencia. | Límite de tasa de 5 por segundo con ráfaga de 10 por ruta. Sin logs de acceso de API Gateway. |
| Recursos olvidados después de la demo. | Costo continuo. | `cdk destroy` (sección 11.8) y revisión de Cost Explorer. |
| Vencimiento del plan gratuito o de los créditos. | Cargos reales. | Presupuesto con alertas (NFR-02) y fecha de vencimiento anotada al crear la cuenta. |
| NAT Gateway, EC2 o RDS agregados por error. | Cargos fijos altos. | Prohibidos por C-01. Test de infraestructura (T-16). |
| Bedrock sin límite (etapa 2). | Cargos por token. | Límite de 50 llamadas por día y modo `template` por defecto (RF-10 y NFR-02). |
| Athena sin acotar (si se suma). | Cargo por TB escaneado. | Consultas acotadas por partición y fecha. Ver D-03. |

### 12.5 Controles

- Presupuesto de AWS Budgets con alertas al llegar a USD 0,80 de gasto real y al pronóstico de USD 1 para el mes (NFR-02).
- Revisión mensual de Cost Explorer durante la demo (NFR-01).
- Etiquetas en todos los recursos: `project = estadisticas-serverless` y `env = demo`. Para que aparezcan en Cost Explorer hay que activarlas como etiquetas de asignación de costos en la consola de Billing.

### 12.6 Después de la capa gratuita

Cuando termine el plan de 6 meses o se agoten los créditos, el costo pasa a ser real. Con el uso de demo, la estimación es que el gasto siga por debajo de USD 1 al mes (NFR-01), pero hay que medirlo. Si no se cumple, las acciones son bajar la frecuencia de las pruebas manuales o destruir el stack (sección 11.8).

## 13. Riesgos y preguntas abiertas

### 13.1 Riesgos

| ID | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R-01 | Los créditos o el plan gratuito terminan. | Cargos reales. | Presupuesto y revisión mensual (sección 12). Destruir el stack si hace falta. |
| R-02 | Abuso de la API o de las subidas. | Costo y datos basura. | Firma IAM en `POST /uploads`, cuota diaria y límite de tasa. |
| R-03 | Logs de más. | Costo de CloudWatch. | Nivel INFO, retención de 7 días y sin contenido del CSV en los logs. |
| R-04 | Nombres de equipo inconsistentes ("River" y "River Plate"). | La tabla muestra equipos duplicados. | Los alias quedan fuera de la v1. El operador usa siempre el mismo nombre por equipo. |
| R-05 | El recálculo crece con el volumen. | Tiempo y lecturas de DynamoDB. | Una temporada de 30 equipos con una vuelta tiene 435 partidos. Para la demo no hay problema. Si crece, una tabla incremental sería una etapa aparte. |
| R-06 | S3 y SQS entregan eventos más de una vez. | Duplicados. | Idempotencia (sección 9.6). |
| R-07 | Nadie revisa la DLQ. | Fallos silenciosos. | Alarma por email (propuesta de SNS) y revisión durante la demo. |
| R-08 | El bootstrap de CDK da permisos de administrador por defecto. | Un error en el pipeline tendría alcance total en la cuenta. | Política de ejecución acotada (sección 10.6), OIDC con condiciones y deploy solo desde `main`. |
| R-09 | Región y precios: `us-east-1` es la propuesta. | Costo y latencia variables. | Medir la latencia desde Argentina en la demo (NFR-04). Verificar precios de la región antes de implementar. |
| R-10 | DynamoDB no tiene recuperación a un punto en el tiempo (PITR). | Pérdida de datos si se borra una tabla por error. | Aceptable en demo. Los CSV se conservan en `processed/` por 30 días, y el operador guarda una copia local para reprocesar después. |
| R-11 | La tabla se recalcula una vez por día. | Después de una carga, la tabla muestra datos viejos. | Recálculo manual antes de presentar (sección 11.7). Propuesta D-05. |
| R-12 | Costo y proveedor de la IA (etapa 2). | Costo variable y dependencia de un proveedor. | Límite de llamadas por día, modo `template` por defecto y decisión de proveedor antes de la etapa (D-04). |
| R-13 | Reemplazar una fecha no borra los partidos que ya no están. | Partidos viejos siguen apareciendo. | Documentado en RF-05. El borrado manual queda para una etapa aparte. |
| R-14 | moto no reproduce todo el comportamiento de AWS. | Pruebas que pasan y fallos reales en AWS. | Las partes que moto no cubre se prueban con pruebas de configuración y con el smoke test (sección 11.1). |
| R-15 | Arranque en frío de Lambda. | La primera consulta de la demo tarda más. | Aceptado en NFR-04 (hasta 3 segundos). Se puede calentar la función antes de presentar. |
| R-16 | `cdk bootstrap` deja recursos después de `cdk destroy`. | Costo residual mínimo y ruido en la cuenta. | Lista de limpieza en la sección 11.8. |
| R-17 | La cuota de concurrencia de Lambda de la cuenta puede ser baja. | Sin cuota suficiente no se puede reservar concurrencia (ingesta 2, recálculo 1, resúmenes 2), y el despliegue falla o queda más lento. | Revisar las cuotas de servicio antes del primer despliegue. Si no alcanzan, pedir un aumento o quitar las reservas y depender del límite de tasa y de la cuota diaria. |

### 13.2 Decisiones abiertas

| ID | Decisión | Estado | Consecuencia |
|---|---|---|---|
| D-01 | Dominio de la v1. | Resuelta el 2026-11-03: fútbol. | Si después se cambia a otro dominio, hay que parametrizar la regla de puntos 3-1-0 (RF-13). |
| D-02 | Nombre del proyecto. | Resuelta como nombre de trabajo: `estadisticas-serverless`. | Un nombre definitivo se puede elegir hasta el primer despliegue. Cambia los prefijos de los recursos y el nombre de la carpeta. |
| D-03 | Athena entra en la v1. | Resuelta el 2026-11-03: no entra. Es una etapa aparte. | La v1 no tiene catálogo Glue ni bucket de resultados. |
| D-04 | El resumen con IA entra en la v1, y con qué proveedor. | Resuelta el 2026-11-03: no entra en la v1. El proveedor queda pendiente para la etapa 2. | La v1 usa solo plantilla (RF-09). La recomendación para la etapa 2 es Amazon Bedrock, porque todo queda en AWS. La alternativa es una API externa, sin créditos y con los datos fuera de AWS. |
| D-05 | ¿Recalcular la tabla también al terminar cada ingesta válida, además del recálculo diario? | Propuesta, pendiente de aprobación. No bloquea la v1. | Si se aprueba, la ingesta invoca el recálculo de la temporada afectada al final (cambian 6.3 y RF-14). Evita el riesgo R-11. |

### 13.3 Decisiones propuestas por este documento

Estas decisiones las tomó el documento para cerrar detalles que no estaban en el pedido. Franco las aprueba junto con el ERS. Si alguna cambia, hay que actualizar las secciones indicadas.

| ID | Propuesta | Sección | Si no se aprueba |
|---|---|---|---|
| P-01 | Región `us-east-1`. | S-02 | Cambiar la región en CDK y revisar precios (R-09). |
| P-02 | `POST /uploads` con firma IAM (SigV4). | 10.1 | Se necesitaría un autorizador Lambda o JWT, con costo y piezas extra. |
| P-03 | Presigned POST con condiciones de tamaño y tipo. | RF-01 | Con presigned PUT, S3 no impone el tamaño de forma directa: solo lo controla la ingesta, después de que el archivo ya se subió. |
| P-04 | Cuota de 20 subidas por día y límite de tasa de 5 por segundo con ráfaga de 10. | NFR-02 | Sin cuota, un abuso podría generar costo. |
| P-05 | Límite de 1 MB y 500 filas por archivo. | NFR-03 | Cambiar los valores en RF-01, RF-02 y NFR-03. |
| P-06 | Dos servicios que no están en la lista original: SNS para avisos de alarmas y AWS Budgets para el control de gasto. | 2.2 y 12.5 | Las alarmas quedan solo en la consola, y el control de gasto es manual. |
| P-07 | Una sola DLQ para todos los fallos. | RF-11 | Una DLQ por origen, con una alarma por cada una. |
| P-08 | Dos stacks de CDK: uno de base (OIDC y presupuesto) y uno de aplicación. | 11.3 | Un solo stack, pero destruir la aplicación borraría también el pipeline. |
| P-09 | Bootstrap de CDK con política de ejecución acotada. | 10.6 | Queda el permiso de administrador por defecto (R-08). |
| P-10 | Desempate de la tabla sin enfrentamientos directos. | RF-13 | Habría que agregar esa regla y casos de prueba adicionales. |

### 13.4 Pendientes antes de implementar

1. Aprobar este ERS.
2. Aprobar o cambiar las decisiones D-05 y P-01 a P-10.
3. Definir de dónde sale el CSV de la primera fecha real. La v1 supone que el operador lo arma a mano a partir de resultados públicos. Este punto queda sin resolver y es necesario para la demo.
4. Crear el repositorio `estadisticas-serverless` en GitHub, con la rama `main`, separado de ChiquiMafias.
5. Confirmar los datos verificados y las estimaciones de precio (sección 12) antes de crear la cuenta de AWS.

## Anexo A. Formatos de entrada y salida

### A.1 CSV de entrada

```csv
competition,season,matchday,match_date,home_team,away_team,home_goals,away_goals
liga-profesional,2026,5,2026-03-14,Boca Juniors,River Plate,2,1
liga-profesional,2026,5,2026-03-14,Racing Club,Independiente,0,0
liga-profesional,2026,5,2026-03-15,Gimnasia,Estudiantes,0,3
```

| Columna | Obligatoria | Regla | Ejemplo |
|---|---|---|---|
| `competition` | Sí | Texto que se convierte a slug (RF-03). | `liga-profesional` |
| `season` | Sí | Entero entre 2000 y 2100. | `2026` |
| `matchday` | Sí | Entero entre 1 y 99. | `5` |
| `match_date` | Sí | Formato `YYYY-MM-DD`. | `2026-03-14` |
| `home_team` | Sí | Texto de 2 a 60 caracteres. | `Boca Juniors` |
| `away_team` | Sí | Texto de 2 a 60 caracteres, distinto de `home_team`. | `River Plate` |
| `home_goals` | Sí | Entero entre 0 y 30. | `2` |
| `away_goals` | Sí | Entero entre 0 y 30. | `1` |

### A.2 Códigos de validación

| Código | Tipo | Significado |
|---|---|---|
| `ENCODING_INVALID` | Error | El archivo no es UTF-8 válido. |
| `EMPTY_FILE` | Error | El archivo no tiene contenido. |
| `FILE_TOO_LARGE` | Error | El archivo supera 1 MB. |
| `HEADER_MISSING_COLUMN` | Error | Falta una columna obligatoria. |
| `ROW_FORMAT_INVALID` | Error | Una fila tiene distinta cantidad de campos que el encabezado. |
| `NO_DATA_ROWS` | Error | Hay encabezado, pero ninguna fila de datos. |
| `TOO_MANY_ROWS` | Error | Hay más de 500 filas de datos. |
| `FIELD_REQUIRED` | Error | Un campo obligatorio está vacío. |
| `FIELD_INVALID` | Error | Un campo no cumple el formato (competición, temporada o fecha de partido fuera de rango). |
| `DATE_INVALID` | Error | La fecha no existe o no tiene formato `YYYY-MM-DD`. |
| `GOALS_INVALID` | Error | Los goles no son un entero entre 0 y 30. |
| `TEAM_NAME_INVALID` | Error | El nombre de un equipo tiene menos de 2 o más de 60 caracteres. |
| `SAME_TEAM` | Error | Local y visitante son el mismo equipo. |
| `DUPLICATE_MATCH` | Error | El mismo par local y visitante aparece dos veces en el archivo. |
| `TEAM_REPEATED_IN_MATCHDAY` | Error | Un equipo juega dos veces en la misma fecha. |
| `MIXED_MATCHDAY` | Error | Las filas mezclan competición, temporada o fecha. |
| `EXTRA_COLUMN_IGNORED` | Advertencia | Hay una columna extra que se ignora. |

### A.3 Reporte de salida

Archivo `reports/<upload_id>.json`. Ejemplo de un archivo rechazado por una fecha mal escrita en la línea 3:

```json
{
  "upload_id": "5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e",
  "status": "REJECTED",
  "rows_total": 3,
  "matches_written": 0,
  "messages_enqueued": 0,
  "warnings": [
    {"line": 1, "column": "notes", "code": "EXTRA_COLUMN_IGNORED", "message": "La columna notes se ignora."}
  ],
  "errors": [
    {"line": 3, "column": "match_date", "code": "DATE_INVALID", "message": "La fecha 2026-3-14 no tiene formato YYYY-MM-DD."}
  ],
  "errors_truncated": false
}
```

### A.4 Fixtures del repositorio

| Archivo | Uso |
|---|---|
| `tests/fixtures/fecha-05-valida.csv` | Archivo válido de 5 partidos (T-01). |
| `tests/fixtures/fecha-05-sin-away-goals.csv` | Columna faltante (T-02). |
| `tests/fixtures/fecha-05-fecha-invalida.csv` | Fecha mal formada (T-03). |
| `tests/fixtures/tabla/fecha-1.csv`, `fecha-2.csv` y `fecha-3.csv`, más `tabla-esperada.json` | Tabla de 4 equipos, un archivo por fecha, con la posición esperada (T-12). |
| `docs/openapi.yaml` | Contrato de la API (RF-15). |

## Historial del documento

| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-11-03 | Borrador inicial para aprobación. Decisiones D-01 a D-04 resueltas con las respuestas de Franco. |
| 0.2 | 2026-11-03 | ERS aprobado por Franco. Implementación local: dominio (validación, tabla, resúmenes), handlers con moto, stacks de CDK y workflows de GitHub Actions. Ajustes respecto del texto: fixture de la tabla en tres archivos (S-05), nombres de columna sin distinguir mayúsculas, permisos de DynamoDB de ingesta y recálculo (10.2). Pendiente: despliegue en AWS, creación del repositorio y cuenta de AWS, y confirmar D-05 y el nombre de la cola (`estadisticas-summary`). |
