"""email unico en la plataforma

Convierte el email en la identidad única de login: añade UNIQUE(email) a
`clientes` y a `empleados`. La regla de producto es "una persona, una cuenta"
en TODA la plataforma; la unicidad CRUZADA entre ambas tablas no la puede
imponer la BD y se garantiza en la capa de aplicación (crud_usuario).

Antes de crear las restricciones se comprueba que no haya duplicados
preexistentes: hoy no los hay, pero la migración debe ser segura si se aplica
sobre otra base de datos, fallando con un mensaje claro en vez de reventar con
un error opaco de índice duplicado a mitad del ALTER.

Revision ID: b51ed9ad172a
Revises: b2f7a1c9d34e
Create Date: 2026-08-25 12:11:41.447124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b51ed9ad172a'
down_revision: Union[str, Sequence[str], None] = 'b2f7a1c9d34e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _abortar_si_hay_duplicados(conn) -> None:
    """Verifica la unicidad del email ANTES de crear las restricciones.

    Comprueba dos cosas y aborta la migración con un mensaje claro si falla:
    1) duplicados DENTRO de cada tabla, que impedirían crear el UNIQUE;
    2) duplicados CRUZADOS clientes<->empleados, que el UNIQUE por tabla no
       bloquea pero violan la identidad única de la plataforma.
    """
    for tabla in ("clientes", "empleados"):
        filas = conn.execute(sa.text(
            f"SELECT email FROM {tabla} GROUP BY email HAVING COUNT(*) > 1"
        )).fetchall()
        if filas:
            emails = ", ".join(f[0] for f in filas)
            raise RuntimeError(
                f"No se puede aplicar UNIQUE(email) sobre '{tabla}': existen "
                f"emails duplicados que hay que unificar antes: {emails}"
            )

    cruzados = conn.execute(sa.text(
        "SELECT c.email FROM clientes c JOIN empleados e ON c.email = e.email"
    )).fetchall()
    if cruzados:
        emails = ", ".join(f[0] for f in cruzados)
        raise RuntimeError(
            "Hay emails registrados a la vez como cliente y como empleado, lo "
            f"que viola la identidad única de la plataforma: {emails}"
        )


def upgrade() -> None:
    """Upgrade schema."""
    _abortar_si_hay_duplicados(op.get_bind())
    # Nombres None: MySQL bautiza la restricción como 'email' (primera columna).
    # Se deja tal cual lo genera autogenerate para que `alembic check` no
    # detecte diferencias; el downgrade las suelta por su nombre real.
    op.create_unique_constraint(None, 'clientes', ['email'])
    op.create_unique_constraint(None, 'empleados', ['email'])


def downgrade() -> None:
    """Downgrade schema."""
    # MySQL nombró ambas restricciones 'email' (autonombrado por columna).
    op.drop_constraint('email', 'empleados', type_='unique')
    op.drop_constraint('email', 'clientes', type_='unique')
