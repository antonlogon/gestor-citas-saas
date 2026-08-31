from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.security import es_empleado, get_current_user, require_empleado
from app.crud import crud_cita, crud_cliente, crud_empleado, crud_servicio
from app.database import get_db

# ==========================================
# ROUTER: CITAS
# Aislamiento por tenant (empresa_id del token) + autorización por rol:
#   - Empleado (personal): control total sobre todas las citas de su empresa.
#   - Cliente: solo puede LISTAR/VER/CREAR sus propias citas (no editar ni
#     borrar, ni ver las de otros clientes -> 403).
# ==========================================

router = APIRouter(
    prefix="/citas",
    tags=["Citas"],
)


def _validar_referencias_cita(
    db: Session, cita: schemas.CitaCreate, empresa_id: int
) -> None:
    """Comprueba que las entidades referenciadas existen y son del tenant.

    Cliente, empleado y servicio se buscan ya acotados a empresa_id: un
    recurso de otro tenant se trata como inexistente (404), evitando tanto
    filtrar datos entre clínicas como crear citas cruzadas.
    """
    db_cliente = crud_cliente.get_cliente(
        db, cliente_id=cita.cliente_id, empresa_id=empresa_id
    )
    if db_cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún cliente con id {cita.cliente_id} en esta empresa.",
        )

    db_empleado = crud_empleado.get_empleado(
        db, empleado_id=cita.empleado_id, empresa_id=empresa_id
    )
    if db_empleado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún empleado con id {cita.empleado_id} en esta empresa.",
        )

    db_servicio = crud_servicio.get_servicio(
        db, servicio_id=cita.servicio_id, empresa_id=empresa_id
    )
    if db_servicio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún servicio con id {cita.servicio_id} en esta empresa.",
        )


@router.post("/", response_model=schemas.Cita, status_code=status.HTTP_201_CREATED)
def crear_cita(
    cita: schemas.CitaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Crea una cita en la propia empresa.

    - Empleado: puede crearla para cualquier cliente de su empresa.
    - Cliente: solo puede crear citas para sí mismo (cliente_id propio).
    """
    if not es_empleado(current_user) and cita.cliente_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes crear citas a tu propio nombre.",
        )
    _validar_referencias_cita(db, cita, empresa_id=current_user.empresa_id)
    try:
        return crud_cita.create_cita(db, cita=cita, empresa_id=current_user.empresa_id)
    except crud_cita.CitaEnPasadoError as exc:
        # 422 (no 409): el 409 significa "solapamiento"; hay que poder distinguirlos.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.mensaje
        )
    except crud_cita.CitaFueraDeHorarioError as exc:
        # 422 como la fecha pasada (regla de negocio), no 409 (que es solape). La
        # clase distinta y el mensaje con el horario real permiten diferenciarla.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.mensaje
        )
    except crud_cita.CitaSolapadaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)


@router.get("/", response_model=List[schemas.Cita])
def listar_citas(
    skip: int = 0,
    limit: int = 100,
    cliente_id: Optional[int] = None,
    empleado_id: Optional[int] = None,
    estado: Optional[models.EstadoCita] = None,
    proximas: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista citas de la propia empresa.

    - Empleado: todas, con filtros opcionales (cliente, empleado, estado).
    - Cliente: se fuerza el filtro a sus propias citas.

    `proximas=true` recorta el listado a partir de ahora, descartando lo ya
    pasado. Es lo que consume la pantalla principal del móvil, cuyo rótulo es
    "Tus próximas citas".

    Es un corte PURAMENTE TEMPORAL: las canceladas que aún no han llegado SÍ se
    devuelven, y el cliente las muestra con su distintivo. Ocultarlas se
    consideró y se descartó: en una agenda médica, que una cita desaparezca sin
    más es peor que el ruido de verla tachada. El paciente no recibiría la
    noticia de la cancelación, recibiría un hueco, y un hueco es indistinguible
    de un fallo de carga o de un recuerdo equivocado.

    El corte se calcula AQUÍ y no en el cliente: la hora del servidor es la
    misma que valida las invariantes al crear y mover citas, mientras que el
    reloj de un móvil puede ir desviado y produciría un listado incoherente con
    lo que la API acepta.

    Por defecto es `false`, de modo que el escritorio sigue viendo la agenda
    completa: la clínica necesita también el histórico.
    """
    if not es_empleado(current_user):
        cliente_id = current_user.id  # el cliente solo ve lo suyo
    # Los nombres aplanados (cliente_nombre, empleado_nombre, servicio_nombre) los
    # expone el modelo como properties, precargadas aquí con joinedload (get_citas)
    # para evitar el N+1. Pydantic los serializa vía from_attributes.
    return crud_cita.get_citas(
        db,
        empresa_id=current_user.empresa_id,
        skip=skip,
        limit=limit,
        cliente_id=cliente_id,
        empleado_id=empleado_id,
        estado=estado,
        desde=datetime.now() if proximas else None,
    )


@router.get("/resumen", response_model=schemas.CitaResumen)
def resumen_citas(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Recuentos agregados de citas (KPIs), calculados en SQL sobre todo el tenant.

    - Empleado: recuentos de toda la empresa.
    - Cliente: se acotan a sus propias citas.

    IMPORTANTE: esta ruta se declara antes que "/{cita_id}" para que "resumen"
    no se interprete como un id de cita.
    """
    cliente_id = None if es_empleado(current_user) else current_user.id
    return crud_cita.get_resumen(
        db, empresa_id=current_user.empresa_id, cliente_id=cliente_id
    )


@router.get("/{cita_id}", response_model=schemas.Cita)
def obtener_cita(
    cita_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Recupera una cita de la propia empresa.

    - Empleado: cualquier cita de su empresa.
    - Cliente: solo si la cita es suya (si no, 403).
    """
    db_cita = crud_cita.get_cita(
        db, cita_id=cita_id, empresa_id=current_user.empresa_id
    )
    if db_cita is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna cita con id {cita_id}.",
        )
    if not es_empleado(current_user) and db_cita.cliente_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes consultar tus propias citas.",
        )
    return db_cita


@router.put("/{cita_id}", response_model=schemas.Cita)
def actualizar_cita(
    cita_id: int,
    cita: schemas.CitaUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Actualiza parcialmente una cita. Solo personal (empleados)."""
    try:
        db_cita = crud_cita.update_cita(
            db, cita_id=cita_id, cita=cita, empresa_id=current_user.empresa_id
        )
    except crud_cita.CitaEnPasadoError as exc:
        # 422 (no 409): reservamos el 409 para el solapamiento.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.mensaje
        )
    except crud_cita.CitaFueraDeHorarioError as exc:
        # 422 como la fecha pasada; la clase propia la distingue del solape.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.mensaje
        )
    except crud_cita.CitaSolapadaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.mensaje)
    if db_cita is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna cita con id {cita_id}.",
        )
    return db_cita


@router.delete("/{cita_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cita(
    cita_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Elimina una cita de la propia empresa. Solo personal (empleados)."""
    db_cita = crud_cita.delete_cita(
        db, cita_id=cita_id, empresa_id=current_user.empresa_id
    )
    if db_cita is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna cita con id {cita_id}.",
        )
