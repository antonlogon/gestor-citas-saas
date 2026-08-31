from sqlalchemy.orm import Session

from app import models, schemas
from app.core.security import hash_password

# ==========================================
# CAPA CRUD: REGISTRO (ONBOARDING DE TENANTS)
# Lógica de acceso a datos. No conoce HTTP: devuelve objetos o re-lanza la
# excepción de BD (tras deshacer la transacción), y es el router quien decide
# qué código de estado responder.
#
# A diferencia de crud_empresa.create_empresa / crud_empleado.create_empleado
# (que confirman cada uno por su cuenta), aquí la empresa y su administrador se
# crean en UNA ÚNICA TRANSACCIÓN: o se guardan ambos, o ninguno.
# ==========================================


def registrar_empresa_con_admin(
    db: Session, datos: schemas.RegistroRequest
) -> tuple[models.Empresa, models.Empleado]:
    """Crea la empresa y su primer empleado (rol ADMIN) de forma atómica.

    ATOMICIDAD: se añade la empresa, se hace `flush` para obtener su id sin
    cerrar la transacción, y solo tras añadir el empleado se emite UN ÚNICO
    `commit`. Si algo falla, `rollback` deshace ambos inserts, de modo que
    nunca queda una empresa huérfana sin administrador (que sería un tenant
    inaccesible e irreparable desde la API).

    Args:
        db: Sesión de SQLAlchemy inyectada por dependencia.
        datos: Datos validados de la empresa y de su administrador.

    Returns:
        La tupla (empresa, empleado) recién creada, con sus IDs asignados.

    Raises:
        Exception: re-lanza cualquier error de BD (p. ej. slug duplicado)
            después de deshacer la transacción; el router lo traduce a HTTP.
    """
    db_empresa = models.Empresa(
        nombre=datos.empresa_nombre,
        slug=datos.slug,
        configuracion_estilo=datos.configuracion_estilo,
    )
    db.add(db_empresa)
    try:
        # flush envía el INSERT de la empresa y asigna su id, pero SIN confirmar:
        # todo sigue dentro de la misma transacción.
        db.flush()

        db_empleado = models.Empleado(
            empresa_id=db_empresa.id,
            nombre=datos.admin_nombre,
            email=datos.admin_email,
            activo=True,
            rol=models.RolEmpleado.ADMIN,
            password_hash=hash_password(datos.admin_password),
        )
        db.add(db_empleado)

        # ÚNICO commit del flujo: confirma empresa y empleado a la vez.
        db.commit()
    except Exception:
        # Cualquier fallo (slug duplicado, dato inválido en el empleado, etc.)
        # deshace TAMBIÉN el insert de la empresa: sin tenants huérfanos.
        db.rollback()
        raise

    db.refresh(db_empresa)
    db.refresh(db_empleado)
    return db_empresa, db_empleado
