# Backend API — NexaCita

API REST (FastAPI + SQLAlchemy + MySQL 8) multi-tenant con JWT/RBAC. El esquema
de base de datos lo gestiona **Alembic** como única fuente de verdad: los cambios
se hacen en `app/models.py` y se propagan con migraciones versionadas.

## Roles y permisos (RBAC)

La autorización tiene dos niveles:

1. **Tipo de usuario** (claim `tipo` del JWT): `cliente` (acceso a su perfil, al
   catálogo y a sus citas) vs `empleado` (personal de la empresa).
2. **Rol del empleado** dentro del tenant (columna `empleados.rol`, enum
   `RolEmpleado`), que se lee **de la base de datos en cada petición**, nunca del
   token: así degradar o desactivar a alguien surte efecto de inmediato.

| Rol        | Puede |
|------------|-------|
| `ADMIN`    | Todo lo de PERSONAL **+** gestionar la empresa (`POST/PUT/DELETE /empresas`), el personal (`POST/PUT/DELETE /empleados`, incluido cambiar roles) y el catálogo (`POST/PUT/DELETE /servicios`, que incluye precios). |
| `PERSONAL` | Trabajo diario: recurso completo de `/clientes` y `/citas`, lectura de `/empresas`, `/empleados` y `/servicios`. |

Empleados nuevos se crean como `PERSONAL` (mínimo privilegio) salvo que se
indique lo contrario. **Salvaguarda:** no se permite dejar a una empresa sin
ningún administrador activo; borrar, degradar o desactivar al último ADMIN
activo devuelve `409 CONFLICT`.

## Identidad y login (email único en la plataforma)

El **email identifica a una persona en TODA la plataforma**: es único entre
clientes, entre empleados y de forma cruzada entre ambas tablas. Esto se
garantiza con `UNIQUE(email)` en `clientes` y `empleados` (a nivel de BD) más
una comprobación de unicidad **cruzada** en la capa de aplicación
(`app/crud/crud_usuario.py`), que la BD no puede imponer por sí sola entre dos
tablas distintas. Todos los caminos de alta o cambio de email (`POST /registro/`,
`POST /clientes/`, `POST /empleados/` y `PUT /clientes/{id}`) pasan por ese guard
y devuelven `409 CONFLICT` si el correo ya está en uso.

Gracias a esta regla, el login (`/login`) resuelve la identidad **sin
ambigüedad**: busca el email primero en clientes y luego en empleados, y como a
lo sumo existe una cuenta con ese correo, no hay duda de a quién autentica.

**Limitación asumida (decisión de alcance, no un descuido):** una misma persona
**no** puede darse de alta en dos clínicas distintas con el mismo correo (p. ej.
un profesional que además es paciente en otro centro). Se acepta a cambio de un
login inequívoco y de no tener que tocar los frontends.

**Vía de evolución** si en el futuro hiciera falta soportar cuentas compartidas
entre clínicas: separar **identidad** de **pertenencia**. Es decir, una tabla
`usuarios` global (email + contraseña, la identidad) y una tabla de pertenencia
que la relacione con cada empresa y su rol. Es el modelo habitual de las
plataformas multi-tenant con cuentas compartidas; hoy el email vive en
`clientes`/`empleados`, no en una entidad de identidad propia.

## Requisitos

- Docker (para MySQL 8) y Python 3.9+.
- MySQL escucha en el puerto **3307** (ver `.env`).

## Puesta en marcha desde cero

```bash
# 1) Levantar MySQL (crea la base de datos VACÍA 'gestor_citas_saas').
cd database
docker compose up -d

# 2) Entorno de Python e instalación de dependencias.
cd ../backend-api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3) Configuración: copia el ejemplo y rellena DATABASE_URL y SECRET_KEY.
cp .env.example .env
#   (genera una clave con: python -c "import secrets; print(secrets.token_hex(32))")

# 4) Crear el esquema con Alembic.  <-- PASO OBLIGATORIO
alembic upgrade head

# 5) Cargar datos de prueba (empresas, usuarios demo, etc.).
python seed.py

# 6) Arrancar la API.
uvicorn app.main:app --reload
```

### Alta de una clínica (onboarding)

El alta de un tenant **ya no requiere `seed.py`** ni tocar la base de datos a
mano: existe un endpoint **público** de registro que crea la empresa y su primer
administrador (rol `ADMIN`) en una sola transacción y devuelve un token JWT
listo para usar.

```bash
curl -X POST http://localhost:8000/registro/ -H "Content-Type: application/json" -d '{
  "empresa_nombre": "Clínica Sonrisas",
  "slug": "clinica-sonrisas",
  "admin_nombre": "Marta Admin",
  "admin_email": "marta@sonrisas.com",
  "admin_password": "password123"
}'
```

`seed.py` sigue existiendo solo para poblar datos de demostración (clientes,
servicios y citas de ejemplo), no como vía de alta.

> ⚠️ El registro es público y **sin protección anti-abuso** (ni límite de tasa
> ni verificación de email): cualquiera puede crear clínicas ilimitadas. Es una
> limitación conocida que debe resolverse antes de producción.

> ⚠️ **Cambio de flujo importante.** El esquema **ya no se crea al levantar el
> contenedor**. Antes, `database/init.sql` se montaba en el arranque de MySQL y
> creaba las tablas; ese fichero se ha **eliminado** (quedaba desincronizado con
> los modelos). Ahora la imagen de MySQL solo crea la base de datos **vacía**
> (vía `MYSQL_DATABASE`), y hay que ejecutar **`alembic upgrade head` antes de
> `seed.py`**. Si te saltas ese paso, `seed.py` fallará porque no existen tablas.

## Asistente virtual (modelo de lenguaje)

El chatbot habla con un proveedor de LLM con **API compatible con OpenAI**. Toda
su configuración vive en `Settings` (`.env`), no en el código:

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | Endpoint del proveedor. |
| `LLM_API_KEY` | `lm-studio` (inocuo en local) | Clave de API. **Es un secreto** con un proveedor real: ponla en `.env` (`CHANGE_ME` en el ejemplo). |
| `LLM_MODEL` | `meta-llama-3.1-8b-instruct` | Identificador del modelo. |
| `LLM_TIMEOUT_SECONDS` | `30` | Espera máxima por cada llamada al modelo. |

Los valores por defecto apuntan a **LM Studio** en local, así que en desarrollo
funciona sin definir nada. **Para usar un proveedor gestionado basta cambiar
estas variables en `.env`, sin tocar código.** Si el proveedor no responde (caído
o agotado el tiempo de espera), el paciente recibe una frase natural de "no
disponible", nunca un error.

## Tests

Los tests cubren las invariantes de negocio (solapamiento de citas con
concurrencia, RBAC, salvaguardas del último admin, atomicidad del registro,
unicidad de email y aislamiento multi-tenant).

**Requisito:** el contenedor de MySQL debe estar levantado (`cd database &&
docker compose up -d`). Los tests usan un **esquema aparte** en ese mismo
contenedor (`gestor_citas_saas_test`), que se **crea y migra con Alembic**
automáticamente; **nunca tocan la base de datos de desarrollo** (un guard aborta
la suite si la URL no apunta al esquema de test).

```bash
# Instalar las dependencias de test (una vez):
pip install -r requirements-dev.txt

# Ejecutar toda la suite:
pytest
```

Por qué MySQL y no SQLite: el test de concurrencia de citas depende de
`SELECT ... FOR UPDATE`, que es un no-op fuera de InnoDB; sobre SQLite pasaría
en verde sin validar nada. Ver `tests/conftest.py` para el detalle de la
estrategia (redirección de la URL antes de importar la app, y limpieza por
`TRUNCATE` entre tests para permitir los commits reales que la concurrencia
necesita).

## Migraciones (Alembic)

La fuente de verdad del esquema es `app/models.py`. La URL de conexión la toma
`alembic/env.py` de `app.core.config.settings.DATABASE_URL` (del `.env`), **no**
de `alembic.ini`.

```bash
# Tras cambiar app/models.py, generar la migración:
alembic revision --autogenerate -m "descripcion del cambio"

# Revisa el fichero generado en alembic/versions/ y aplícalo:
alembic upgrade head

# Utilidades:
alembic current      # revisión aplicada en la BD
alembic history      # historial de migraciones
alembic downgrade -1 # revertir la última
```

Comprobación de coherencia: `alembic revision --autogenerate -m "check"` debe
producir una migración **vacía**. Si detecta cambios, es que `models.py` y la BD
no coinciden; averigua por qué antes de continuar (y borra ese fichero "check").
