"""horario de apertura por empresa

Añade la columna `horario_apertura` (JSON) a la tabla `empresas`: el horario de
apertura semanal vive POR TENANT (el sistema es multi-inquilino), no como
constantes en el código.

FORMATO (ver app/models): lista de 7 posiciones indexadas como datetime.weekday()
(0=lunes ... 6=domingo); cada una es la lista de tramos {"inicio","fin"} de ese
día y una lista vacía significa CERRADO.

RELLENO DE DATOS: la columna es NOT NULL, pero las empresas YA EXISTENTES no
tienen valor. Se añade primero NULLABLE, se rellenan con el horario por defecto
(L-V mañana y tarde con cierre a mediodía, S-D cerrado) y luego se fija NOT NULL,
igual que hizo la migración del rol de empleado. El literal se inlina aquí (no se
importa de app.models) para que la migración sea autocontenida y no cambie si el
default de la aplicación evoluciona en el futuro.

Revision ID: c7d4e2f1a9b0
Revises: b51ed9ad172a
Create Date: 2026-08-26 10:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d4e2f1a9b0'
down_revision: Union[str, Sequence[str], None] = 'b51ed9ad172a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Horario por defecto para las empresas existentes (congelado en la migración).
_TRAMOS_LABORABLES = [
    {"inicio": "09:00", "fin": "14:00"},
    {"inicio": "16:00", "fin": "20:00"},
]
_HORARIO_POR_DEFECTO = [_TRAMOS_LABORABLES] * 5 + [[], []]  # L-V abiertos, S-D cerrados


def upgrade() -> None:
    """Upgrade schema."""
    # 1) Se añade NULLABLE: las filas existentes aún no tienen horario.
    op.add_column('empresas', sa.Column('horario_apertura', sa.JSON(), nullable=True))

    # 2) Empresas EXISTENTES -> horario por defecto. El default de la columna solo
    #    aplica a inserciones nuevas del ORM, no a las filas ya presentes.
    op.execute(
        sa.text(
            "UPDATE empresas SET horario_apertura = :horario "
            "WHERE horario_apertura IS NULL"
        ).bindparams(horario=json.dumps(_HORARIO_POR_DEFECTO))
    )

    # 3) Ya sin nulos, fijamos NOT NULL para casar con el modelo.
    op.alter_column(
        'empresas', 'horario_apertura', existing_type=sa.JSON(), nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('empresas', 'horario_apertura')
