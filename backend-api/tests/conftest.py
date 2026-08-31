"""Infraestructura común de los tests (fixtures de pytest).

DECISIONES CLAVE (ver README, sección de tests):

- BASE DE DATOS: un ESQUEMA APARTE (``gestor_citas_saas_test``) del MISMO
  contenedor MySQL. Nada de SQLite: el ``SELECT ... FOR UPDATE`` de
  ``crud_cita.verificar_disponibilidad`` es un no-op fuera de InnoDB, así que un
  test de concurrencia sobre SQLite pasaría en verde sin ejercitar nada.

- EL ENGINE SE CONSTRUYE AL IMPORTAR ``app.database`` (engine a nivel de módulo,
  a partir de ``settings.DATABASE_URL``). Por eso, ANTES de importar nada de
  ``app``, este módulo fija ``os.environ["DATABASE_URL"]`` apuntando al esquema
  de test. pytest importa ``conftest`` antes que los tests, y pydantic-settings
  da precedencia a la variable de entorno sobre el ``.env``, de modo que el
  engine nace ya apuntando a la BD de test. Además, un GUARD aborta la suite si
  el nombre de la BD no acaba en ``_test``: es imposible tocar la BD de trabajo.

- ESQUEMA CREADO CON ALEMBIC (no ``create_all``): se recrea desde cero con
  ``alembic upgrade head`` en cada sesión, validando de paso las migraciones.

- AISLAMIENTO ENTRE TESTS por TRUNCATE (no una transacción con rollback): varios
  tests (solapamiento, concurrencia) necesitan commits reales.
"""
import os

from sqlalchemy.engine import make_url

# ---------------------------------------------------------------------------
# 1) Redirección de la URL a la BD de test ANTES de importar la app.
# ---------------------------------------------------------------------------
# URL de desarrollo: del entorno o del .env (sin exponerla aún como settings).
from dotenv import dotenv_values  # noqa: E402  (python-dotenv ya es dependencia)

_ruta_env = os.path.join(os.path.dirname(__file__), "..", ".env")
_url_dev = os.environ.get("DATABASE_URL") or dotenv_values(_ruta_env).get("DATABASE_URL")
if _url_dev is None:
    raise RuntimeError(
        "No se encontró DATABASE_URL (ni en el entorno ni en backend-api/.env); "
        "los tests necesitan la URL de MySQL para derivar el esquema de test."
    )

# El esquema de test es el de desarrollo con el sufijo _test en el nombre de BD.
_url_dev_obj = make_url(_url_dev)
_url_test_obj = _url_dev_obj.set(database=f"{_url_dev_obj.database}_test")
NOMBRE_BD_TEST = _url_test_obj.database

# GUARD: el esquema de test debe ser DISTINTO del de desarrollo. Protege frente
# a que la URL de partida ya apuntara al esquema de test (o a uno sin nombre de
# BD), en cuyo caso operaríamos —y haríamos DROP— sobre la base de trabajo. La
# otra garantía, contra el fallo de orden de importación, es el assert de
# engine.url.database en preparar_esquema.
if NOMBRE_BD_TEST == _url_dev_obj.database:
    raise RuntimeError(
        f"Salvaguarda de seguridad: la BD de test '{NOMBRE_BD_TEST}' coincide con "
        "la de desarrollo. Se aborta para no tocar por error la base de trabajo."
    )

# A partir de aquí, cualquier import de app.* usará la URL de test.
os.environ["DATABASE_URL"] = _url_test_obj.render_as_string(hide_password=False)

# ---------------------------------------------------------------------------
# 2) Ya con la URL redirigida, importamos la app y sus piezas.
# ---------------------------------------------------------------------------
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import models  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

# Tablas de datos (todas menos alembic_version), en orden irrelevante porque se
# vacían con las comprobaciones de clave foránea desactivadas.
_TABLAS = ("citas", "servicios", "empleados", "clientes", "empresas")

# Contraseña común de los usuarios sembrados, para los tests que hacen login.
PASSWORD_TEST = "password123"


# ---------------------------------------------------------------------------
# 3) Preparación del esquema: una vez por sesión, con Alembic.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def preparar_esquema():
    """Recrea el esquema de test desde cero aplicando las migraciones.

    DROP + CREATE del esquema y ``alembic upgrade head``: así cada ejecución
    valida que las migraciones producen un esquema correcto (lo que init.sql
    dejó de garantizar en su día). El engine de la app ya apunta a esta BD.
    """
    # Segunda barrera del guard, justo antes de una operación destructiva.
    assert engine.url.database == NOMBRE_BD_TEST and NOMBRE_BD_TEST.endswith("_test")

    # Conexión al esquema de sistema 'mysql' (siempre existe) para poder
    # (re)crear la BD de test. Nota: URL.set(database=None) NO limpia el nombre,
    # así que se apunta explícitamente a un esquema existente.
    url_servidor = _url_test_obj.set(database="mysql")
    motor_servidor = create_engine(url_servidor)
    with motor_servidor.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{NOMBRE_BD_TEST}`"))
        conn.execute(
            text(f"CREATE DATABASE `{NOMBRE_BD_TEST}` CHARACTER SET utf8mb4")
        )
        conn.commit()
    motor_servidor.dispose()

    # Migraciones: env.py lee settings.DATABASE_URL (ya = test).
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.upgrade(cfg, "head")

    yield
    # El esquema se deja creado (se recrea al inicio de la próxima sesión).


def _truncar_todo() -> None:
    """Vacía todas las tablas de datos (deja el esquema intacto)."""
    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for tabla in _TABLAS:
            conn.execute(text(f"TRUNCATE TABLE `{tabla}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        conn.commit()


@pytest.fixture(autouse=True)
def limpiar_bd():
    """Parte de un estado limpio en CADA test (TRUNCATE, no rollback).

    Se limpia ANTES del test para que un fallo no contamine al siguiente y para
    que el estado final quede inspeccionable tras la ejecución.
    """
    _truncar_todo()
    yield


# ---------------------------------------------------------------------------
# 4) Cliente HTTP y datos de partida (dos empresas para el aislamiento).
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    """TestClient de FastAPI. Usa el get_db normal -> engine de test."""
    with TestClient(app) as c:
        yield c


def _token(usuario, tipo: str) -> str:
    """Emite un JWT con los mismos claims que /login (sub, tipo, id)."""
    return create_access_token(
        data={"sub": usuario.email, "tipo": tipo, "id": usuario.id}
    )


@pytest.fixture()
def datos_base(limpiar_bd):
    """Siembra DOS empresas con clientes, empleados y servicios, y sus tokens.

    Depende de ``limpiar_bd`` para garantizar el orden (primero se vacía, luego
    se siembra). Devuelve un ``SimpleNamespace`` con ``a`` y ``b`` (una por
    empresa), cada una con ids y tokens listos:

        datos.a.empresa_id / cliente_id / admin_id / personal_id / servicio_id
        datos.a.token_admin / token_personal / token_cliente
        datos.b.*  (empresa B: admin, cliente y servicio)

    El servicio dura 30 minutos: es la duración sobre la que se construyen los
    tests de solapamiento.
    """
    db = SessionLocal()
    try:
        def sembrar_empresa(nombre, slug, sufijo, con_personal):
            empresa = models.Empresa(nombre=nombre, slug=slug)
            db.add(empresa)
            db.flush()  # asigna empresa.id

            admin = models.Empleado(
                empresa_id=empresa.id, nombre=f"Admin {sufijo}",
                email=f"admin_{sufijo}@test.com", activo=True,
                rol=models.RolEmpleado.ADMIN,
                password_hash=hash_password(PASSWORD_TEST),
            )
            cliente = models.Cliente(
                empresa_id=empresa.id, nombre=f"Cliente {sufijo}",
                email=f"cliente_{sufijo}@test.com", telefono="600000000",
                password_hash=hash_password(PASSWORD_TEST),
            )
            servicio = models.Servicio(
                empresa_id=empresa.id, nombre=f"Servicio {sufijo}",
                duracion_minutos=30, precio=40,
            )
            db.add_all([admin, cliente, servicio])

            personal = None
            if con_personal:
                personal = models.Empleado(
                    empresa_id=empresa.id, nombre=f"Personal {sufijo}",
                    email=f"personal_{sufijo}@test.com", activo=True,
                    rol=models.RolEmpleado.PERSONAL,
                    password_hash=hash_password(PASSWORD_TEST),
                )
                db.add(personal)

            db.flush()
            ns = SimpleNamespace(
                empresa_id=empresa.id,
                admin_id=admin.id, cliente_id=cliente.id, servicio_id=servicio.id,
                admin_email=admin.email, cliente_email=cliente.email,
                token_admin=_token(admin, "empleado"),
                token_cliente=_token(cliente, "cliente"),
            )
            if personal is not None:
                ns.personal_id = personal.id
                ns.personal_email = personal.email
                ns.token_personal = _token(personal, "empleado")
            return ns

        # Empresa A: completa (admin + personal), para RBAC y solapamiento.
        a = sembrar_empresa("Clinica A", "clinica-a", "a", con_personal=True)
        # Empresa B: la "otra" clínica, para probar el aislamiento.
        b = sembrar_empresa("Clinica B", "clinica-b", "b", con_personal=False)
        db.commit()

        return SimpleNamespace(a=a, b=b)
    finally:
        db.close()


@pytest.fixture()
def auth():
    """Devuelve un helper ``auth(token)`` con la cabecera Bearer para el TestClient."""
    def _cabecera(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}
    return _cabecera
