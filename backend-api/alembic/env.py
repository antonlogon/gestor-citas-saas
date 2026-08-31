from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ==========================================================================
# Integración de Alembic con la aplicación.
# - La URL de conexión sale de app.core.config.settings.DATABASE_URL (que la
#   lee de .env / variables de entorno). NO se hardcodea en alembic.ini, que va
#   versionado.
# - target_metadata es app.database.Base.metadata. Importamos app.models por su
#   efecto secundario: registrar TODAS las tablas en esa metadata antes de que
#   autogenerate compare el esquema.
# ==========================================================================
from app.core.config import settings
from app.database import Base
from app import models  # noqa: F401  (registra las tablas en Base.metadata)

# Objeto de configuración de Alembic (accede a los valores de alembic.ini).
config = context.config

# Inyectamos la URL real en la configuración de Alembic, para que la usen tanto
# el modo online como el offline y los comandos de la CLI. Así la fuente de
# verdad de la conexión es el .env de la app, no el .ini versionado.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configuración del logging a partir del fichero .ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata objetivo para 'autogenerate': el esquema declarado en los modelos.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Ejecuta las migraciones en modo 'offline'.

    Configura el contexto solo con la URL (sin crear un Engine) y emite el SQL
    resultante, útil para generar scripts sin conectarse a la base de datos.
    """
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta las migraciones en modo 'online', conectando a la base de datos."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
