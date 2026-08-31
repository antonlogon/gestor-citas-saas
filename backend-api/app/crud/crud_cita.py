import re
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app import models, schemas

# ==========================================
# CAPA CRUD: CITA
# Lógica de acceso a datos. No conoce HTTP: devuelve objetos o None,
# y es el router quien decide qué código de estado responder.
# La validación de integridad (cliente/empleado/servicio existentes y
# del mismo tenant) se hace en el router antes de llamar a create_cita.
#
# AISLAMIENTO MULTI-TENANT: todas las operaciones exigen empresa_id y
# filtran por él.
#
# INVARIANTES DE AGENDA (viven AQUÍ, en el único punto de escritura por el que
# pasan los tres caminos —create_cita, update_cita y el chatbot vía ambos—, para
# que sean inevitables):
#   1. No solapamiento: un empleado no puede tener dos citas cuyos intervalos
#      [inicio, inicio+duracion) se pisen. Las canceladas NO ocupan hueco.
#      (verificar_disponibilidad)
#   2. No agendar ni MOVER citas al pasado (_validar_fecha_futura).
#   3. Dentro del horario de apertura del tenant: el intervalo COMPLETO de la
#      cita debe caber en un mismo tramo de apertura del día (_validar_dentro_horario).
# Las invariantes 2 y 3 comparten disparador al actualizar: solo se comprueban si
# la fecha DIFIERE de la almacenada, de modo que gestionar una cita antigua
# (cancelar, confirmar, anotar) sin tocar su fecha nunca se bloquea.
# ==========================================


# Margen de tolerancia para el rechazo de citas en el pasado. Absorbe la
# desincronización de relojes entre cliente y servidor (p. ej. agendar las 09:00
# cuando el servidor ya marca las 09:00:30): con la rejilla de 15 min del
# escritorio, ese es el caso realista, no un intento de agendar en el pasado.
MARGEN_PASADO = timedelta(minutes=2)


class CitaEnPasadoError(Exception):
    """La fecha/hora solicitada para la cita está en el pasado.

    Se usa tanto al crear como al MOVER la fecha de una cita (reprogramar).
    Transporta un mensaje en español listo para el 422 del router y para que el
    asistente conversacional lo reformule al paciente.
    """

    def __init__(self, fecha_hora: datetime):
        self.fecha_hora = fecha_hora
        self.mensaje = (
            "La fecha de la cita ya ha pasado: debe ser posterior al momento "
            f"actual (se pidió {fecha_hora.strftime('%Y-%m-%d %H:%M')})."
        )
        super().__init__(self.mensaje)


class CitaSolapadaError(Exception):
    """La franja solicitada se solapa con otra cita activa del mismo empleado.

    Transporta la cita en conflicto y un mensaje en español listo para mostrar
    (incluye profesional y hora), reutilizable tanto por el router (detalle del
    409) como por el chatbot (frase para el paciente).
    """

    def __init__(self, cita_conflictiva: models.Cita):
        self.cita = cita_conflictiva
        inicio = cita_conflictiva.fecha_hora
        profesional = (
            cita_conflictiva.empleado.nombre
            if cita_conflictiva.empleado is not None
            else "el profesional"
        )
        self.mensaje = (
            f"La franja solicitada se solapa con otra cita de {profesional} "
            f"el {inicio.strftime('%Y-%m-%d')} a las {inicio.strftime('%H:%M')}."
        )
        super().__init__(self.mensaje)


class ServicioNoResolubleError(Exception):
    """No se pudo resolver el servicio de una cita (y con él su duración).

    Es un error de programación o de integridad (el servicio debería existir y
    pertenecer al tenant), NO un caso a tolerar: sin duración no se puede calcular
    el solapamiento, y asumir 0 dejaría pasar una cita como si no ocupara tiempo.
    """


class HorarioInvalidoError(Exception):
    """El horario de apertura de la empresa no se puede interpretar.

    MISMO CRITERIO que ServicioNoResolubleError: un horario corrupto (sin 7 días,
    con horas mal formadas o con fin <= inicio) es un invariante ROTO de los
    datos, no un caso a tolerar. Sin un horario interpretable no se puede decidir
    la regla, y tragárselo dejaría pasar la cita desactivando la invariante en
    silencio. Falla de forma ruidosa (el router la deja subir a 500) en vez de
    aceptar la cita a ciegas.
    """


# Días de la semana EN PLURAL y en castellano, resueltos de forma explícita (sin
# depender del locale del sistema). Índice = datetime.weekday() (0=lunes).
_DIAS_SEMANA_PLURAL = (
    "los lunes", "los martes", "los miércoles", "los jueves", "los viernes",
    "los sábados", "los domingos",
)

# Una hora válida en 24h "HH:MM" (00:00–23:59). Se valida con regex para
# rechazar de forma ruidosa cualquier hora mal formada del horario.
_HORA_REGEX = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _a_minutos(hhmm: object) -> int:
    """Convierte una hora "HH:MM" (24h) a minutos desde medianoche.

    Raises:
        ValueError: si no es una cadena "HH:MM" válida (lo captura el validador
            del horario para relanzarlo como HorarioInvalidoError).
    """
    if not isinstance(hhmm, str) or not _HORA_REGEX.match(hhmm):
        raise ValueError(f"hora inválida: {hhmm!r}")
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


def _franjas_texto(tramos: list) -> str:
    """Redacta los tramos de un día: 'de 09:00 a 14:00 y de 16:00 a 20:00'.

    Se usa tanto en el mensaje de CitaFueraDeHorarioError como en el informe de
    disponibilidad del asistente, para que ambos hablen del horario real.
    """
    return "de " + " y de ".join(f"{t['inicio']} a {t['fin']}" for t in tramos)


class CitaFueraDeHorarioError(Exception):
    """La cita no cabe dentro de ningún tramo de apertura de ese día.

    Excepción PROPIA (distinta de solape y de fecha pasada) para que el router y
    el asistente puedan diferenciarla. El mensaje indica el horario REAL del día
    ("los martes atendemos de 09:00 a 14:00 y de 16:00 a 20:00") o que está
    cerrado, en lugar de un genérico "fuera de horario".
    """

    def __init__(self, fecha_hora: datetime, tramos_dia: list):
        self.fecha_hora = fecha_hora
        dia = _DIAS_SEMANA_PLURAL[fecha_hora.weekday()]
        if not tramos_dia:
            self.mensaje = (
                f"La cita queda fuera del horario de apertura: {dia} la clínica "
                "permanece cerrada."
            )
        else:
            self.mensaje = (
                f"La cita queda fuera del horario de apertura: {dia} atendemos "
                f"{_franjas_texto(tramos_dia)}."
            )
        super().__init__(self.mensaje)


def _tramos_en_minutos(horario: object, empresa_id: Optional[int] = None) -> List[list]:
    """Valida el horario del tenant y lo traduce a minutos desde medianoche.

    Falla RUIDOSAMENTE con HorarioInvalidoError ante cualquier dato corrupto
    (menos de 7 días, elemento que no es lista, tramo mal formado, hora inválida
    o fin <= inicio): ver la nota de esa excepción.

    Returns:
        7 listas (índice 0=lunes ... 6=domingo) de tuplas (inicio_min, fin_min).
    """
    referencia = f" de la empresa {empresa_id}" if empresa_id is not None else ""
    if not isinstance(horario, list) or len(horario) != 7:
        raise HorarioInvalidoError(
            f"El horario de apertura{referencia} no es una lista de 7 días: {horario!r}."
        )

    semana: List[list] = []
    for indice, tramos in enumerate(horario):
        if not isinstance(tramos, list):
            raise HorarioInvalidoError(
                f"El día {indice} del horario{referencia} no es una lista de tramos: "
                f"{tramos!r}."
            )
        dia_en_minutos = []
        for tramo in tramos:
            try:
                inicio = _a_minutos(tramo["inicio"])
                fin = _a_minutos(tramo["fin"])
            except (TypeError, KeyError, ValueError) as exc:
                raise HorarioInvalidoError(
                    f"Tramo mal formado en el día {indice} del horario{referencia}: "
                    f"{tramo!r} ({exc})."
                ) from exc
            if fin <= inicio:
                raise HorarioInvalidoError(
                    f"Tramo con fin <= inicio en el día {indice} del horario"
                    f"{referencia}: {tramo!r}."
                )
            dia_en_minutos.append((inicio, fin))
        semana.append(dia_en_minutos)
    return semana


def _validar_dentro_horario(
    horario: object,
    fecha_hora: datetime,
    duracion_minutos: int,
    empresa_id: Optional[int] = None,
) -> None:
    """Exige que el intervalo COMPLETO de la cita quepa en un tramo de apertura.

    La cita [inicio, inicio+duracion] es válida si y solo si EXISTE un único
    tramo del día que la contenga entera: apertura <= inicio Y fin <= cierre. El
    cierre es INCLUSIVO (13:30 + 30 min = 14:00 vale), igual que en el solape una
    cita que empieza cuando otra acaba no solapa. Exigir un mismo tramo que
    contenga inicio Y fin resuelve de un golpe los tres casos sutiles: empezar
    dentro y terminar fuera (13:45 + 30 = 14:15), empezar antes de abrir o
    después de cerrar, y cruzar del tramo de mañana al de tarde.

    Raises:
        CitaFueraDeHorarioError: si la cita no cabe en ningún tramo (incluye el
            día cerrado).
        HorarioInvalidoError: si el horario del tenant está corrupto.
    """
    semana = _tramos_en_minutos(horario, empresa_id)
    tramos_dia = semana[fecha_hora.weekday()]

    inicio_min = fecha_hora.hour * 60 + fecha_hora.minute
    fin_min = inicio_min + duracion_minutos
    # Si la cita se sale del día (fin_min > 1440) ningún tramo puede contenerla,
    # así que cae de forma natural en el rechazo sin tratarlo aparte.
    cabe = any(ini <= inicio_min and fin_min <= fin for ini, fin in tramos_dia)
    if not cabe:
        # Se lanza con los tramos ORIGINALES (HH:MM) del día para redactar el
        # horario real en el mensaje.
        raise CitaFueraDeHorarioError(fecha_hora, horario[fecha_hora.weekday()])


def describir_apertura_dia(
    horario: object, fecha: date, empresa_id: Optional[int] = None
) -> Optional[str]:
    """Redacta el horario de apertura de ese día para el asistente.

    Devuelve 'de 09:00 a 14:00 y de 16:00 a 20:00' si abre, o None si ese día la
    clínica está cerrada. Valida el horario (HorarioInvalidoError si está roto),
    coherente con la comprobación de escritura. La usa el chatbot para informar
    del horario real en lugar de afirmar que "el resto del horario está libre".
    """
    _tramos_en_minutos(horario, empresa_id)  # valida la estructura
    tramos_dia = horario[fecha.weekday()]
    if not tramos_dia:
        return None
    return _franjas_texto(tramos_dia)


def get_empresa_horario(db: Session, empresa_id: int) -> object:
    """Devuelve el horario de apertura del tenant (o falla ruidosamente).

    La empresa DEBE existir (el empresa_id viene del token del usuario o de una
    cita ya persistida); si no está, es un invariante roto y no un caso a tolerar.
    """
    empresa = (
        db.query(models.Empresa).filter(models.Empresa.id == empresa_id).first()
    )
    if empresa is None:
        raise HorarioInvalidoError(
            f"No se encontró la empresa {empresa_id} para leer su horario de apertura."
        )
    return empresa.horario_apertura


def _validar_fecha_futura(fecha_hora: datetime) -> None:
    """Exige que la fecha/hora de una cita sea futura (con un pequeño margen).

    Usa `datetime.now()` (naive, hora local), la MISMA referencia que el resto
    del código y coherente con el DATETIME naive almacenado: comparar contra UTC
    introduciría un desfase de zona y rechazaría citas válidas de las próximas
    horas. Se tolera `MARGEN_PASADO` para no rechazar a quien agenda "para dentro
    de un minuto" por diferencias de reloj entre cliente y servidor.

    Args:
        fecha_hora: Inicio solicitado para la cita.

    Raises:
        CitaEnPasadoError: si `fecha_hora` es anterior a ahora menos el margen.
    """
    if fecha_hora < datetime.now() - MARGEN_PASADO:
        raise CitaEnPasadoError(fecha_hora)


def verificar_disponibilidad(
    db: Session,
    empresa_id: int,
    empleado_id: int,
    fecha_hora_inicio: datetime,
    duracion_minutos: int,
    excluir_cita_id: Optional[int] = None,
) -> Optional[models.Cita]:
    """Comprueba si una franja choca con otra cita activa del mismo empleado.

    Dos intervalos [inicio_a, fin_a) y [inicio_b, fin_b) se solapan cuando
    `inicio_a < fin_b AND inicio_b < fin_a` (semiabiertos: una cita que empieza
    justo cuando otra acaba NO solapa). La duración de cada cita existente se
    obtiene uniendo con `Servicio`.

    Concurrencia: la consulta usa `with_for_update` para BLOQUEAR las filas de
    las citas del empleado en esa ventana; combinada con hacer la comprobación
    y la escritura en la misma transacción, evita que dos peticiones simultáneas
    pasen ambas la comprobación y creen un solape.

    Ventana acotada por AMBOS extremos: la cota superior es `fecha_hora < fin_a`
    (una cita que empieza cuando la nueva ya terminó no puede solapar). La cota
    INFERIOR es imprescindible para no seleccionar —y BLOQUEAR con FOR UPDATE—
    toda la agenda histórica del empleado: una cita anterior solo puede alcanzar
    `fecha_hora_inicio` si empieza después de `inicio - su_duracion`. Como en el
    WHERE no conocemos la duración de cada una, usamos el margen MÁXIMO posible
    (el MAX de las duraciones de los servicios del tenant, derivado de los datos,
    no una constante). Así se bloquea solo la ventana relevante.

    Args:
        db: Sesión de SQLAlchemy (la transacción abierta debe usarse también
            para la escritura posterior, sin commit intermedio).
        empresa_id: Empresa (tenant) del usuario autenticado.
        empleado_id: Empleado cuya agenda se comprueba.
        fecha_hora_inicio: Inicio de la franja solicitada.
        duracion_minutos: Duración de la franja solicitada (del servicio).
        excluir_cita_id: Cita a ignorar (la propia, al actualizar).

    Returns:
        La primera cita en conflicto, o None si la franja está libre.
    """
    fin_a = fecha_hora_inicio + timedelta(minutes=duracion_minutos)

    # Margen inferior = duración máxima posible entre los servicios del tenant.
    # Ninguna cita que empiece antes de (inicio - ese margen) puede alcanzar la
    # franja nueva, así que quedan fuera de la ventana bloqueada.
    duracion_maxima = (
        db.query(func.max(models.Servicio.duracion_minutos))
        .filter(models.Servicio.empresa_id == empresa_id)
        .scalar()
    ) or 0
    inicio_ventana = fecha_hora_inicio - timedelta(minutes=duracion_maxima)

    # Candidatas: citas ACTIVAS del mismo empleado y tenant DENTRO de la ventana
    # [inicio_ventana, fin_a) (prefiltro que ya descarta las que no pueden
    # solapar). Traemos también la duración del servicio de cada una.
    query = (
        db.query(models.Cita, models.Servicio.duracion_minutos)
        .join(models.Servicio, models.Cita.servicio_id == models.Servicio.id)
        .filter(
            models.Cita.empresa_id == empresa_id,
            models.Cita.empleado_id == empleado_id,
            models.Cita.estado != models.EstadoCita.CANCELADA,
            models.Cita.fecha_hora >= inicio_ventana,
            models.Cita.fecha_hora < fin_a,
        )
    )
    if excluir_cita_id is not None:
        query = query.filter(models.Cita.id != excluir_cita_id)

    # Bloqueo de filas (FOR UPDATE) solo sobre las citas de la ventana: en
    # MySQL/InnoDB toma un lock exclusivo sobre esas filas hasta el commit, de
    # modo que otra transacción que quiera reservar la misma franja se bloquea
    # hasta que esta termine, evitando la carrera entre comprobación y escritura.
    for cita_existente, duracion_b in query.with_for_update(of=models.Cita).all():
        fin_b = cita_existente.fecha_hora + timedelta(minutes=duracion_b)
        if fecha_hora_inicio < fin_b and cita_existente.fecha_hora < fin_a:
            return cita_existente
    return None


def get_cita(db: Session, cita_id: int, empresa_id: int) -> Optional[models.Cita]:
    """Recupera una cita por su ID, restringida a su empresa.

    Args:
        db: Sesión de SQLAlchemy inyectada por dependencia.
        cita_id: Identificador único de la cita.
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        La cita encontrada o None si no existe o es de otra empresa.
    """
    return (
        db.query(models.Cita)
        .filter(
            models.Cita.id == cita_id,
            models.Cita.empresa_id == empresa_id,
        )
        .first()
    )


def get_citas(
    db: Session,
    empresa_id: int,
    skip: int = 0,
    limit: int = 100,
    cliente_id: Optional[int] = None,
    empleado_id: Optional[int] = None,
    estado: Optional[models.EstadoCita] = None,
    desde: Optional[datetime] = None,
) -> List[models.Cita]:
    """Lista las citas de una empresa con paginación y filtros opcionales.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Empresa (tenant) del usuario autenticado.
        skip: Número de registros a saltar (offset).
        limit: Número máximo de registros a devolver.
        cliente_id: Si se indica, solo citas de ese cliente.
        empleado_id: Si se indica, solo citas de ese empleado.
        estado: Si se indica, solo citas en ese estado.
        desde: Si se indica, solo citas a partir de ese instante (inclusive).

    Returns:
        Lista de citas de esa empresa, de la más antigua a la más reciente
        (puede estar vacía).
    """
    # joinedload: carga cliente, empleado y servicio en la misma consulta (evita
    # el problema N+1 al acceder luego a sus nombres en el endpoint).
    query = (
        db.query(models.Cita)
        .options(
            joinedload(models.Cita.cliente),
            joinedload(models.Cita.empleado),
            joinedload(models.Cita.servicio),
        )
        .filter(models.Cita.empresa_id == empresa_id)
    )
    if cliente_id is not None:
        query = query.filter(models.Cita.cliente_id == cliente_id)
    if empleado_id is not None:
        query = query.filter(models.Cita.empleado_id == empleado_id)
    if estado is not None:
        query = query.filter(models.Cita.estado == estado)
    if desde is not None:
        query = query.filter(models.Cita.fecha_hora >= desde)
    # Orden cronologico explicito. El id como segundo criterio no es decorativo:
    # dos profesionales pueden atender a la misma hora (el solapamiento se
    # comprueba por empleado, no por empresa), y sin un desempate estable la
    # paginacion con skip/limit queda indefinida en SQL: una misma fila podria
    # repetirse en una pagina y faltar en la siguiente.
    return (
        query.order_by(models.Cita.fecha_hora, models.Cita.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_resumen(
    db: Session, empresa_id: int, cliente_id: Optional[int] = None
) -> dict:
    """Recuentos agregados de citas calculados en SQL (para los KPIs del panel).

    Se calcula sobre TODAS las citas del tenant (opcionalmente acotadas a un
    cliente), sin paginación, de modo que los indicadores reflejen el total real
    y no una página. "hoy" excluye las canceladas: una cita cancelada no ocupa
    agenda.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Empresa (tenant) del usuario autenticado.
        cliente_id: Si se indica, restringe los recuentos a ese cliente.

    Returns:
        dict con las claves: total, hoy, pendientes, confirmadas, canceladas.
    """
    base = db.query(models.Cita).filter(models.Cita.empresa_id == empresa_id)
    if cliente_id is not None:
        base = base.filter(models.Cita.cliente_id == cliente_id)

    total = base.count()

    # Recuento por estado en una sola consulta (COUNT ... GROUP BY estado).
    filas = (
        base.with_entities(models.Cita.estado, func.count(models.Cita.id))
        .group_by(models.Cita.estado)
        .all()
    )
    # Normalizamos la clave a su valor string ("PENDIENTE"...) por robustez.
    conteos = {
        (estado.value if hasattr(estado, "value") else str(estado)): cnt
        for estado, cnt in filas
    }

    # Citas de hoy, excluyendo las canceladas (rango [00:00, 23:59:59.999999]).
    inicio_dia = datetime.combine(date.today(), time.min)
    fin_dia = datetime.combine(date.today(), time.max)
    hoy = (
        base.filter(
            models.Cita.fecha_hora >= inicio_dia,
            models.Cita.fecha_hora <= fin_dia,
            models.Cita.estado != models.EstadoCita.CANCELADA,
        ).count()
    )

    return {
        "total": total,
        "hoy": hoy,
        "pendientes": conteos.get(models.EstadoCita.PENDIENTE.value, 0),
        "confirmadas": conteos.get(models.EstadoCita.CONFIRMADA.value, 0),
        "canceladas": conteos.get(models.EstadoCita.CANCELADA.value, 0),
    }


def create_cita(
    db: Session, cita: schemas.CitaCreate, empresa_id: int
) -> models.Cita:
    """Crea una nueva cita PENDIENTE en la empresa del usuario autenticado.

    Args:
        db: Sesión de SQLAlchemy.
        cita: Datos validados de la cita a crear.
        empresa_id: Empresa (tenant) a la que se asigna la cita.

    Returns:
        La cita recién creada, con su ID asignado por la BD.

    Raises:
        CitaEnPasadoError: si la fecha/hora solicitada está en el pasado.
        CitaFueraDeHorarioError: si la cita no cabe en un tramo de apertura.
        CitaSolapadaError: si la franja se solapa con otra cita activa del
            mismo empleado.
    """
    # Regla de agenda: no se pueden crear citas en el pasado. Se valida ANTES de
    # tocar la BD (sin bloqueos que revertir).
    _validar_fecha_futura(cita.fecha_hora)

    # Duración del servicio (acotada al tenant) para calcular la franja. Si no se
    # resuelve, es un invariante roto: fallamos claro en vez de asumir duración 0.
    servicio = (
        db.query(models.Servicio)
        .filter(
            models.Servicio.id == cita.servicio_id,
            models.Servicio.empresa_id == empresa_id,
        )
        .first()
    )
    if servicio is None:
        raise ServicioNoResolubleError(
            f"No se encontró el servicio id={cita.servicio_id} en la empresa "
            f"{empresa_id}: no se puede calcular la duración de la cita."
        )
    duracion = servicio.duracion_minutos

    # Regla de agenda: la cita debe caber en el horario de apertura del tenant. Se
    # valida ANTES del solapamiento (que toma locks FOR UPDATE), sin tocar la BD.
    empresa = get_empresa_horario(db, empresa_id)
    _validar_dentro_horario(empresa, cita.fecha_hora, duracion, empresa_id)

    # Comprobación de solapamiento en la misma transacción (con bloqueo de filas)
    # ANTES de insertar, para que create sea la puerta única de escritura.
    conflicto = verificar_disponibilidad(
        db,
        empresa_id=empresa_id,
        empleado_id=cita.empleado_id,
        fecha_hora_inicio=cita.fecha_hora,
        duracion_minutos=duracion,
    )
    if conflicto is not None:
        error = CitaSolapadaError(conflicto)  # lee atributos con la sesión viva
        db.rollback()                          # libera los locks del FOR UPDATE
        raise error

    db_cita = models.Cita(**cita.model_dump(), empresa_id=empresa_id)
    db.add(db_cita)
    db.commit()
    db.refresh(db_cita)
    return db_cita


def update_cita(
    db: Session, cita_id: int, cita: schemas.CitaUpdate, empresa_id: int
) -> Optional[models.Cita]:
    """Actualiza parcialmente una cita de la propia empresa.

    Args:
        db: Sesión de SQLAlchemy.
        cita_id: Identificador de la cita a actualizar.
        cita: Campos a modificar (los no enviados se conservan).
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        La cita actualizada o None si no existe o es de otra empresa.

    Raises:
        CitaEnPasadoError: si la petición MUEVE la cita a una fecha pasada.
        CitaFueraDeHorarioError: si la petición MUEVE la cita fuera del horario
            de apertura del tenant.
        CitaSolapadaError: si tras el cambio la cita queda activa y su franja se
            solapa con otra cita del mismo empleado (mover fecha, o reactivar una
            cita CANCELADA sobre un hueco ya ocupado).
    """
    db_cita = get_cita(db, cita_id, empresa_id)
    if db_cita is None:
        return None

    # exclude_unset=True ignora los campos que el cliente no envió
    datos = cita.model_dump(exclude_unset=True)

    # Estado y fecha EFECTIVOS tras aplicar el cambio (aún sin persistir).
    estado_efectivo = datos.get("estado", db_cita.estado)
    fecha_efectiva = datos.get("fecha_hora", db_cita.fecha_hora)

    # Reglas de agenda ligadas a la FECHA: no mover al pasado y no mover fuera de
    # horario. Ambas comparten disparador: solo se comprueban si la fecha CAMBIA
    # respecto a la almacenada. Reenviar la misma fecha (algunos clientes mandan
    # siempre fecha_hora aunque solo cambien estado o notas) no es mover la cita,
    # así que una cita antigua fuera de horario se puede seguir gestionando
    # (cancelar, confirmar, anotar) sin bloquear el historial.
    if fecha_efectiva != db_cita.fecha_hora:
        _validar_fecha_futura(fecha_efectiva)
        # Para comprobar el horario necesitamos la duración del servicio de la
        # cita; sin él es un invariante roto (igual que en el solape).
        if db_cita.servicio is None:
            raise ServicioNoResolubleError(
                f"La cita id={cita_id} no tiene un servicio resoluble: no se "
                "puede calcular la duración para comprobar el horario."
            )
        _validar_dentro_horario(
            get_empresa_horario(db, empresa_id),
            fecha_efectiva,
            db_cita.servicio.duracion_minutos,
            empresa_id,
        )

    # Solo comprobamos solape si la cita quedará ACTIVA: una cancelada no ocupa
    # hueco. Esto cubre tanto mover la fecha como reactivar desde CANCELADA.
    if estado_efectivo != models.EstadoCita.CANCELADA:
        if db_cita.servicio is None:
            raise ServicioNoResolubleError(
                f"La cita id={cita_id} no tiene un servicio resoluble: no se "
                "puede calcular la duración para comprobar el solapamiento."
            )
        duracion = db_cita.servicio.duracion_minutos
        conflicto = verificar_disponibilidad(
            db,
            empresa_id=empresa_id,
            empleado_id=db_cita.empleado_id,
            fecha_hora_inicio=fecha_efectiva,
            duracion_minutos=duracion,
            excluir_cita_id=cita_id,   # la propia cita no cuenta como conflicto
        )
        if conflicto is not None:
            error = CitaSolapadaError(conflicto)
            db.rollback()
            raise error

    for campo, valor in datos.items():
        setattr(db_cita, campo, valor)

    db.commit()
    db.refresh(db_cita)
    return db_cita


def delete_cita(db: Session, cita_id: int, empresa_id: int) -> Optional[models.Cita]:
    """Elimina una cita de la propia empresa.

    Args:
        db: Sesión de SQLAlchemy.
        cita_id: Identificador de la cita a eliminar.
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        La cita eliminada o None si no existía o es de otra empresa.
    """
    db_cita = get_cita(db, cita_id, empresa_id)
    if db_cita is None:
        return None

    db.delete(db_cita)
    db.commit()
    return db_cita
