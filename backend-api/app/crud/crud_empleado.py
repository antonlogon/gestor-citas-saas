from typing import List, Optional

from sqlalchemy.orm import Session

from app import models, schemas
from app.core.security import hash_password

# ==========================================
# CAPA CRUD: EMPLEADO
# Lógica de acceso a datos. No conoce HTTP: devuelve objetos o None,
# y es el router quien decide qué código de estado responder.
#
# AISLAMIENTO MULTI-TENANT: salvo el lookup global de login, todas las
# operaciones exigen empresa_id y filtran por él.
# ==========================================


class UltimoAdminError(Exception):
    """La operación dejaría al tenant sin ningún administrador activo.

    Excepción de dominio (la capa CRUD no conoce HTTP): el router la traduce a
    un 409 CONFLICT. Se lanza al intentar borrar, degradar a PERSONAL o
    desactivar al único ADMIN activo de la empresa.
    """


def contar_admins_activos(
    db: Session, empresa_id: int, excluir_id: Optional[int] = None
) -> int:
    """Cuenta los empleados ADMIN y activos de una empresa.

    Es la comprobación base de las salvaguardas que impiden que un tenant se
    quede sin administrador. Se ejecuta en la MISMA sesión (y por tanto en la
    misma transacción) que la escritura que se está validando.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Empresa (tenant) del usuario autenticado.
        excluir_id: Empleado a excluir del recuento (el que se está borrando o
            modificando), para contar los OTROS admins activos que quedarían.

    Returns:
        Número de administradores activos de la empresa (excluyendo excluir_id).
    """
    query = db.query(models.Empleado).filter(
        models.Empleado.empresa_id == empresa_id,
        models.Empleado.rol == models.RolEmpleado.ADMIN,
        models.Empleado.activo.is_(True),
    )
    if excluir_id is not None:
        query = query.filter(models.Empleado.id != excluir_id)
    return query.count()


def get_empleado(
    db: Session, empleado_id: int, empresa_id: int
) -> Optional[models.Empleado]:
    """Recupera un empleado por su ID, restringido a su empresa.

    Args:
        db: Sesión de SQLAlchemy inyectada por dependencia.
        empleado_id: Identificador único del empleado.
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El empleado encontrado o None si no existe o es de otra empresa.
    """
    return (
        db.query(models.Empleado)
        .filter(
            models.Empleado.id == empleado_id,
            models.Empleado.empresa_id == empresa_id,
        )
        .first()
    )


def get_empleado_by_email(db: Session, email: str) -> Optional[models.Empleado]:
    """Busca un empleado por su email en toda la plataforma.

    USO EXCLUSIVO DEL LOGIN: es el único punto sin usuario autenticado del que
    derivar la empresa. El email es ÚNICO en toda la plataforma (UNIQUE en BD +
    unicidad cruzada en crud_usuario), así que a lo sumo hay una coincidencia y
    `.first()` la devuelve sin ambigüedad.

    Args:
        db: Sesión de SQLAlchemy.
        email: Correo electrónico a buscar.

    Returns:
        El empleado encontrado o None si no existe.
    """
    return db.query(models.Empleado).filter(models.Empleado.email == email).first()


def get_empleados(
    db: Session,
    empresa_id: int,
    skip: int = 0,
    limit: int = 100,
    solo_activos: bool = False,
) -> List[models.Empleado]:
    """Lista los empleados de una empresa con paginación y filtros.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Empresa (tenant) del usuario autenticado.
        skip: Número de registros a saltar (offset).
        limit: Número máximo de registros a devolver.
        solo_activos: Si es True, excluye a los empleados dados de baja.

    Returns:
        Lista de empleados de esa empresa (puede estar vacía).
    """
    query = db.query(models.Empleado).filter(
        models.Empleado.empresa_id == empresa_id
    )
    if solo_activos:
        query = query.filter(models.Empleado.activo.is_(True))
    return query.offset(skip).limit(limit).all()


def create_empleado(
    db: Session, empleado: schemas.EmpleadoCreate, empresa_id: int
) -> models.Empleado:
    """Crea un nuevo empleado en la empresa del usuario autenticado.

    Args:
        db: Sesión de SQLAlchemy.
        empleado: Datos validados del empleado a crear.
        empresa_id: Empresa (tenant) a la que se asigna el empleado.

    Returns:
        El empleado recién creado, con su ID asignado por la BD.
    """
    datos = empleado.model_dump(exclude={"password"})
    db_empleado = models.Empleado(
        **datos, empresa_id=empresa_id, password_hash=hash_password(empleado.password)
    )
    db.add(db_empleado)
    db.commit()
    db.refresh(db_empleado)
    return db_empleado


def update_empleado(
    db: Session, empleado_id: int, empleado: schemas.EmpleadoUpdate, empresa_id: int
) -> Optional[models.Empleado]:
    """Actualiza parcialmente un empleado de la propia empresa.

    Args:
        db: Sesión de SQLAlchemy.
        empleado_id: Identificador del empleado a actualizar.
        empleado: Campos a modificar (los no enviados se conservan).
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El empleado actualizado o None si no existe o es de otra empresa.

    Raises:
        UltimoAdminError: si el cambio (degradar a PERSONAL o desactivar)
            dejaría a la empresa sin ningún administrador activo.
    """
    db_empleado = get_empleado(db, empleado_id, empresa_id)
    if db_empleado is None:
        return None

    # exclude_unset=True ignora los campos que el cliente no envió
    datos = empleado.model_dump(exclude_unset=True)

    # SALVAGUARDA DEL ÚLTIMO ADMIN: cubre a la vez la degradación (rol=PERSONAL)
    # y la desactivación (activo=False), que son dos caminos hacia el mismo
    # agujero. Calculamos el estado RESULTANTE y, si el empleado deja de ser un
    # admin activo y no queda ningún otro, abortamos antes de tocar la fila.
    rol_final = datos.get("rol", db_empleado.rol)
    activo_final = datos.get("activo", db_empleado.activo)
    era_admin_activo = (
        db_empleado.rol == models.RolEmpleado.ADMIN and db_empleado.activo
    )
    sera_admin_activo = rol_final == models.RolEmpleado.ADMIN and activo_final
    if era_admin_activo and not sera_admin_activo:
        if contar_admins_activos(db, empresa_id, excluir_id=empleado_id) == 0:
            raise UltimoAdminError(
                "No se puede degradar ni desactivar al último administrador "
                "activo de la empresa: el tenant quedaría sin administración."
            )

    for campo, valor in datos.items():
        setattr(db_empleado, campo, valor)

    db.commit()
    db.refresh(db_empleado)
    return db_empleado


def delete_empleado(
    db: Session, empleado_id: int, empresa_id: int
) -> Optional[models.Empleado]:
    """Elimina un empleado de la propia empresa (y sus citas por cascada).

    Args:
        db: Sesión de SQLAlchemy.
        empleado_id: Identificador del empleado a eliminar.
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El empleado eliminado o None si no existía o es de otra empresa.

    Raises:
        UltimoAdminError: si borrarlo dejaría a la empresa sin ningún
            administrador activo.
    """
    db_empleado = get_empleado(db, empleado_id, empresa_id)
    if db_empleado is None:
        return None

    # SALVAGUARDA DEL ÚLTIMO ADMIN: si el empleado a borrar es un admin activo
    # y no queda ningún otro, abortamos. contar_admins_activos excluye la fila
    # y corre en la misma transacción que el delete.
    es_admin_activo = (
        db_empleado.rol == models.RolEmpleado.ADMIN and db_empleado.activo
    )
    if es_admin_activo and contar_admins_activos(
        db, empresa_id, excluir_id=empleado_id
    ) == 0:
        raise UltimoAdminError(
            "No se puede borrar al último administrador activo de la empresa: "
            "el tenant quedaría sin administración."
        )

    db.delete(db_empleado)
    db.commit()
    return db_empleado
