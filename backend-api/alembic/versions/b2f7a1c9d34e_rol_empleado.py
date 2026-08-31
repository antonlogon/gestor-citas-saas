"""rol de empleado (RBAC)

Añade la columna `rol` (ENUM ADMIN/PERSONAL) a la tabla `empleados`, base del
control de acceso por rol dentro de cada tenant.

RELLENO DE DATOS — decisión deliberada:
    El default de APLICACIÓN para empleados NUEVOS es PERSONAL (mínimo
    privilegio; ver app/models.RolEmpleado y schemas.EmpleadoBase). Pero a los
    empleados YA EXISTENTES esta migración los marca como ADMIN, NO como
    PERSONAL. Motivo: hasta ahora cualquier empleado administraba su empresa
    (no había roles), así que son de facto los administradores actuales del
    tenant. Si los degradáramos a todos a PERSONAL de golpe, cada tenant vivo se
    quedaría sin NADIE capaz de dar de alta personal, promover admins o
    gestionar la empresa: un tenant sin administrador y sin forma de recuperarse
    por la API. Marcarlos ADMIN preserva el statu quo; un admin puede después
    degradar a quien proceda (con la salvaguarda del último admin activo).

Revision ID: b2f7a1c9d34e
Revises: 7103feea796b
Create Date: 2026-08-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f7a1c9d34e'
down_revision: Union[str, Sequence[str], None] = '7103feea796b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tipo ENUM reutilizado en upgrade. name='rolempleado' coincide con el que
# SQLAlchemy deriva de RolEmpleado (nombre de clase en minúsculas), igual que
# 'estadocita', para que autogenerate/`alembic check` no detecte diferencias.
rol_enum = sa.Enum('ADMIN', 'PERSONAL', name='rolempleado')


def upgrade() -> None:
    """Upgrade schema."""
    # 1) Se añade primero NULLABLE: no podemos poner NOT NULL de entrada porque
    #    las filas existentes aún no tienen valor.
    op.add_column('empleados', sa.Column('rol', rol_enum, nullable=True))

    # 2) Empleados EXISTENTES -> ADMIN (ver cabecera). Son los administradores
    #    actuales de facto de cada tenant; degradarlos dejaría clínicas sin
    #    administración.
    op.execute("UPDATE empleados SET rol = 'ADMIN' WHERE rol IS NULL")

    # 3) Ya sin nulos, fijamos NOT NULL para casar con el modelo. Los empleados
    #    NUEVOS reciben PERSONAL desde la capa de aplicación (default del schema).
    op.alter_column(
        'empleados', 'rol', existing_type=rol_enum, nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # En MySQL el ENUM es inline en la columna, así que basta con eliminarla.
    op.drop_column('empleados', 'rol')
