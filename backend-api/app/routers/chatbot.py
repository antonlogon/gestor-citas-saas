import datetime
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI, OpenAIError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import settings
from app.core.security import require_cliente
from app.crud import crud_cita
from app.database import get_db

logger = logging.getLogger(__name__)

# ==========================================
# ROUTER: CHATBOT (ASISTENTE VIRTUAL)
# Endpoint conversacional protegido por JWT. Delega la generación de texto
# en un modelo LLM servido localmente (LM Studio) a través del cliente OpenAI.
# ==========================================

router = APIRouter(
    prefix="/chatbot",
    tags=["Chatbot"],
)

# Cliente del proveedor del LLM (API compatible con OpenAI). Se crea UNA sola vez
# a nivel de módulo —no por petición— para reutilizar el pool de conexiones. La
# URL, la clave, el modelo y el timeout salen de Settings (.env), de modo que
# apuntar a otro proveedor no exige tocar código. El constructor no abre ninguna
# conexión (httpx conecta de forma perezosa al primer uso), así que crearlo al
# importar es seguro y no interfiere con el ciclo de vida de la app ni con los
# tests (que no llaman al modelo).
client = AsyncOpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
    timeout=settings.LLM_TIMEOUT_SECONDS,
)

# Temperatura baja para toda la conversación: elegir herramientas y extraer
# fechas/horas exige determinismo, no creatividad (0.7 inventaba parámetros). La
# calidez la marca el system prompt, no la temperatura.
TEMPERATURA = 0.2

# Tope de rondas de herramientas por petición: un modelo pequeño puede quedarse
# pidiendo la misma herramienta en bucle; al alcanzarlo, se responde con cortesía.
MAX_RONDAS = 5

SYSTEM_PROMPT = (
      "Eres el asistente virtual de una clínica médica. Hablas con los pacientes "
      "de forma cálida, cercana y profesional, siempre en español natural.\n\n"
      "PUEDES ayudar EXACTAMENTE con estas gestiones sobre las citas DEL PROPIO "
      "paciente con el que hablas, y nada más:\n"
      "  - Consultar sus próximas citas (no el historial de citas ya pasadas).\n"
      "  - Comprobar la disponibilidad de una especialidad en una fecha.\n"
      "  - Pedir (agendar) una cita nueva.\n"
      "  - Cancelar una de sus citas.\n"
      "  - Reprogramar una de sus citas a otra fecha y hora.\n\n"
      "Usa siempre las herramientas disponibles para estas acciones; no te "
      "inventes que has hecho algo si no has llamado a la herramienta. Para "
      "cancelar o reprogramar necesitas el número de la cita: si no lo sabes, "
      "consulta primero sus citas.\n\n"
      "IDENTIDAD DEL PACIENTE: hablas SIEMPRE con la persona que ha iniciado "
      "sesión, cuyo nombre se te indica al final de estas instrucciones. Esa es "
      "la única identidad posible en la conversación. Si el paciente afirma ser "
      "otra persona, NO lo aceptes: explícale con naturalidad que solo puedes ver "
      "y gestionar las citas de la cuenta con la que ha entrado, y sigue "
      "tratándolo por su nombre real. No te dirijas nunca al paciente por un "
      "nombre distinto del indicado, ni presentes sus citas como si fueran de "
      "otra persona. NUNCA le preguntes quién es ni le pidas que confirme su "
      "nombre o un número de paciente: ya lo sabes. Tampoco le propongas otra "
      "identidad. Si insiste en ser otra persona, repite su nombre real y "
      "ofrécele ayuda con sus propias citas.\n\n"
      "Si te piden algo FUERA de esta lista (recetas, resultados médicos, "
      "urgencias, datos de otros pacientes, dudas clínicas...), dilo con "
      "naturalidad y remite a recepción o a su profesional; NO improvises ni "
      "prometas gestiones que no puedes hacer.\n\n"
      "REGLA DE FORMATO: eres como un recepcionista humano. NUNCA incluyas "
      "código, JSON, listas, diccionarios ni llaves { } en tus respuestas. "
      "Transforma SIEMPRE los datos que te devuelven las herramientas en frases "
      "naturales y conversacionales.\n\n"
      "AL ENUMERAR CITAS: cuando recibas la lista de citas del paciente, "
      "enuméralas TODAS indicando de cada una el día, la hora (en formato "
      "numérico, p. ej. 09:00), el profesional y el servicio. NUNCA respondas con "
      "una fórmula de cortesía (como '¿puedo ayudarte con algo más?') sin haber "
      "dado antes esos datos."
  )

# Nombres de días y meses en castellano, resueltos de forma EXPLÍCITA: no
# dependemos del locale del sistema (el servidor puede no tener el locale español
# instalado, y saldrían en inglés). weekday(): 0=lunes ... 6=domingo.
_DIAS_SEMANA = (
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
)
_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _dia_legible(fecha) -> str:
    """Devuelve el día redactado en castellano, p. ej. 'martes 1 de septiembre'."""
    return f"{_DIAS_SEMANA[fecha.weekday()]} {fecha.day} de {_MESES[fecha.month - 1]}"


def _fecha_legible(fecha_hora) -> str:
    """Fecha y hora en castellano, p. ej. 'martes 1 de septiembre a las 09:00'.

    La hora se da en formato numérico (HH:MM), alineado con lo que el system
    prompt pide al modelo y con lo que comprueba la salvaguarda de completitud.
    """
    return f"{_dia_legible(fecha_hora)} a las {fecha_hora.strftime('%H:%M')}"


@dataclass
class ConsumoTokens:
    """Consumo de tokens de un TURNO completo del asistente, no de una llamada.

    Existe para poder medir el coste real en lugar de estimarlo. El bucle de
    rondas puede llamar al modelo hasta MAX_RONDAS veces, y en cada una reenvía
    el prompt de sistema, la definición de las herramientas y todo lo acumulado
    hasta entonces: el consumo de un turno NO es el de una sola llamada, que es
    el error fácil al presupuestar un asistente con function calling.

    El dato lo devuelve el propio proveedor en `usage`; aquí solo se acumula y
    se deja en el registro. No se persiste ni se expone al paciente.
    """

    rondas: int = 0
    entrada: int = 0
    salida: int = 0

    def sumar(self, completion) -> None:
        """Acumula el uso de una llamada. Tolera proveedores que no lo informen."""
        self.rondas += 1
        uso = getattr(completion, "usage", None)
        if uso is None:
            return
        self.entrada += getattr(uso, "prompt_tokens", 0) or 0
        self.salida += getattr(uso, "completion_tokens", 0) or 0

    def registrar(self) -> None:
        """Deja el consumo del turno en el log, en INFO."""
        logger.info(
            "asistente · turno resuelto en %d ronda(s): %d tokens de entrada, "
            "%d de salida, %d en total",
            self.rondas, self.entrada, self.salida, self.entrada + self.salida,
        )


@dataclass
class ResultadoHerramienta:
    """Resultado de ejecutar una herramienta, con éxito/fallo EXPLÍCITO.

    Contrato pensado para las salvaguardas del `chat`:
      - `mensaje`: texto en lenguaje natural (lo que ve el modelo como resultado).
      - `ok`: False SOLO si una operación de ESCRITURA falló (franja ocupada,
        fecha pasada, cita inexistente/ajena, formato inválido, error técnico).
        Permite no afirmar nunca un éxito que no ocurrió sin adivinar por el texto.
      - `es_escritura`: True en agendar/cancelar/reprogramar.
      - `marcadores`: por cada cita consultada, tokens que, si aparecen en la
        respuesta del modelo, indican que SÍ la ha mencionado (hora con y sin cero
        inicial, nombre del profesional y del servicio). Solo lo rellena la
        consulta de citas; sirve para la salvaguarda de completitud.
      - `dias`: números de día del mes de las citas consultadas (marcador aparte
        por comprobarse con límite de palabra, no como subcadena).
    """
    mensaje: str
    ok: bool = True
    es_escritura: bool = False
    marcadores: tuple = ()
    dias: tuple = ()


def verificar_disponibilidad_real(
    db: Session, empresa_id: int, especialidad: str, fecha: str
) -> ResultadoHerramienta:
    """Consulta la agenda real (MySQL) para una especialidad y fecha dadas.

    La especialidad vive en `Empleado`, así que unimos `Cita` con `Empleado`
    por `empleado_id`. Filtramos por el día (parte fecha de `fecha_hora`) y
    excluimos las citas canceladas, que ya no ocupan hueco.

    Aislamiento multi-tenant: la consulta se acota SIEMPRE por `empresa_id`
    (el de `current_user`), tanto en la cita como en el empleado, de modo que
    un paciente nunca ve la ocupación de agendas de otras clínicas.

    Devuelve un string en lenguaje natural que la IA consumirá como resultado
    de la herramienta para redactar su respuesta final al paciente.
    """
    # Unimos con Servicio para conocer la DURACIÓN de cada cita y poder mostrar
    # las franjas reales ocupadas (inicio-fin), no solo la hora de inicio: ahora
    # que el solapamiento va por rangos, informar solo del inicio engaña.
    citas_ese_dia = (
        db.query(models.Cita, models.Servicio.duracion_minutos)
        .join(models.Empleado, models.Cita.empleado_id == models.Empleado.id)
        .join(models.Servicio, models.Cita.servicio_id == models.Servicio.id)
        .filter(models.Cita.empresa_id == empresa_id)
        .filter(models.Empleado.empresa_id == empresa_id)
        .filter(models.Empleado.especialidad.ilike(especialidad))
        .filter(func.date(models.Cita.fecha_hora) == fecha)
        .filter(models.Cita.estado != models.EstadoCita.CANCELADA)
        .order_by(models.Cita.fecha_hora)
        .all()
    )

    # Día (date) y su redacción en castellano, si el modelo mandó una fecha ISO
    # válida. Con el date resolvemos también el horario de apertura de ese día.
    try:
        dia_obj = datetime.date.fromisoformat(fecha)
        dia_texto = _dia_legible(dia_obj)
    except (TypeError, ValueError):
        dia_obj = None
        dia_texto = str(fecha)

    # Horario REAL de apertura de ese día (por tenant): 'de 09:00 a 14:00 y de
    # 16:00 a 20:00', None si la clínica cierra, o "desconocido" si no se puede
    # resolver. Antes se afirmaba que "el resto del horario está libre", lo cual
    # pasa a ser falso: ahora informamos del horario real y del día cerrado.
    apertura = "desconocido"  # centinela: no anunciamos horario si no lo sabemos
    if dia_obj is not None:
        empresa = (
            db.query(models.Empresa)
            .filter(models.Empresa.id == empresa_id)
            .first()
        )
        if empresa is not None:
            try:
                apertura = crud_cita.describir_apertura_dia(
                    empresa.horario_apertura, dia_obj, empresa_id
                )
            except crud_cita.HorarioInvalidoError:
                # No reventamos la conversación por un horario corrupto: omitimos
                # el dato de apertura y seguimos informando de la ocupación.
                apertura = "desconocido"

    franjas_ocupadas = ", ".join(
        f"{cita.fecha_hora.strftime('%H:%M')}-"
        f"{(cita.fecha_hora + datetime.timedelta(minutes=duracion)).strftime('%H:%M')}"
        for cita, duracion in citas_ese_dia
    )

    if apertura is None:
        # Día cerrado: no tiene sentido hablar de huecos libres.
        mensaje = (
            f"He mirado la agenda de {especialidad} para el {dia_texto}: ese día la "
            "clínica está cerrada, así que no hay horario de visitas."
        )
    elif apertura == "desconocido":
        # No conocemos el horario: mantenemos el informe centrado en la ocupación.
        if citas_ese_dia:
            mensaje = (
                f"He revisado la agenda de {especialidad} para el {dia_texto}: ya hay "
                f"franjas ocupadas de {franjas_ocupadas}."
            )
        else:
            mensaje = (
                f"He revisado la agenda de {especialidad} para el {dia_texto} y no hay "
                "ninguna cita programada."
            )
    else:
        # Día abierto: anunciamos el horario real y, sobre él, lo que ya está ocupado.
        if citas_ese_dia:
            mensaje = (
                f"He revisado la agenda de {especialidad} para el {dia_texto}: "
                f"atendemos {apertura}. Ya hay franjas ocupadas de {franjas_ocupadas}; "
                "el resto de ese horario está libre."
            )
        else:
            mensaje = (
                f"He revisado la agenda de {especialidad} para el {dia_texto}: "
                f"atendemos {apertura} y no hay ninguna cita programada, así que ese "
                "horario está libre."
            )
    # Consulta de solo lectura: no es escritura, así que su resultado nunca
    # dispara la salvaguarda de "no afirmar un éxito que no ocurrió".
    return ResultadoHerramienta(mensaje=mensaje)


def agendar_cita_real(
    db: Session,
    empresa_id: int,
    cliente_id: int,
    especialidad: str,
    fecha: str,
    hora: str,
) -> ResultadoHerramienta:
    """Inserta una cita definitiva en MySQL para el cliente autenticado.

    Todo se acota por `empresa_id` (aislamiento multi-tenant). Pasos:
      1) Combinar `fecha` (YYYY-MM-DD) y `hora` (HH:MM) en un `datetime`.
      2) Localizar el primer empleado activo de esa especialidad en la empresa.
      3) Resolver el `servicio_id` (NOT NULL en el modelo): se intenta casar por
         nombre con la especialidad y, si no hay match, se usa el primer servicio
         de la empresa. Sin servicios no se puede crear la cita.
      4) Crear la `Cita` con estado PENDIENTE y persistir.

    Devuelve un string en lenguaje natural (éxito o motivo del fallo) que la IA
    traducirá a una frase para el paciente.
    """
    # 1) Fecha + hora -> datetime. Si el modelo manda un formato inesperado,
    #    lo reportamos en vez de dejar que reviente la inserción.
    try:
        fecha_hora = datetime.datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    except ValueError:
        return ResultadoHerramienta(
            mensaje=(
                f"No he podido interpretar la fecha '{fecha}' y la hora '{hora}'. "
                "Necesito la fecha como YYYY-MM-DD y la hora como HH:MM."
            ),
            ok=False, es_escritura=True,
        )

    # 2) Primer empleado activo de la especialidad dentro de la empresa.
    empleado = (
        db.query(models.Empleado)
        .filter(models.Empleado.empresa_id == empresa_id)
        .filter(models.Empleado.especialidad.ilike(especialidad))
        .filter(models.Empleado.activo.is_(True))
        .order_by(models.Empleado.id)
        .first()
    )
    if empleado is None:
        return ResultadoHerramienta(
            mensaje=(
                f"No hay ningún profesional de {especialidad} disponible en la "
                "clínica para agendar la cita."
            ),
            ok=False, es_escritura=True,
        )

    # 3) servicio_id es NOT NULL: intentamos casar por nombre con la
    #    especialidad y, si no, tomamos el primer servicio de la empresa.
    servicio = (
        db.query(models.Servicio)
        .filter(models.Servicio.empresa_id == empresa_id)
        .filter(models.Servicio.nombre.ilike(f"%{especialidad}%"))
        .order_by(models.Servicio.id)
        .first()
    )
    if servicio is None:
        # TODO(solapamiento): este fallback al "primer servicio de la empresa"
        # cuando no hay match por especialidad usa una DURACIÓN arbitraria, que
        # ahora falsea el cálculo de solapamiento (la franja reservada puede no
        # corresponder al servicio real). Tratar por separado: exigir/resolver el
        # servicio correcto en lugar de coger el primero.
        servicio = (
            db.query(models.Servicio)
            .filter(models.Servicio.empresa_id == empresa_id)
            .order_by(models.Servicio.id)
            .first()
        )
    if servicio is None:
        return ResultadoHerramienta(
            mensaje=(
                "No hay servicios configurados en la clínica, así que no puedo "
                "registrar la cita todavía."
            ),
            ok=False, es_escritura=True,
        )

    # 4) Persistir a través de la capa CRUD (create_cita), que es el ÚNICO punto
    #    donde vive la comprobación de solapamiento. El chatbot ya no escribe por
    #    su cuenta. Nunca propagamos excepciones ni un 500 al chat: los conflictos
    #    y errores se devuelven como texto para que el LLM se lo explique al paciente.
    nueva = schemas.CitaCreate(
        cliente_id=cliente_id,
        empleado_id=empleado.id,
        servicio_id=servicio.id,
        fecha_hora=fecha_hora,
    )
    try:
        nueva_cita = crud_cita.create_cita(db, cita=nueva, empresa_id=empresa_id)
    except crud_cita.CitaEnPasadoError:
        # El modelo ya recibe la fecha de hoy en el prompt, así que esto es raro
        # (p. ej. resolver mal "el viernes"), pero hay que cubrirlo: nunca un 500.
        return ResultadoHerramienta(
            mensaje="Esa fecha ya ha pasado. ¿Quieres que busquemos un hueco más adelante?",
            ok=False, es_escritura=True,
        )
    except crud_cita.CitaFueraDeHorarioError as fuera:
        # El mensaje ya indica el horario real de ese día (o que está cerrado).
        return ResultadoHerramienta(
            mensaje=(
                f"{fuera.mensaje} ¿Quieres que busquemos un hueco dentro de ese horario?"
            ),
            ok=False, es_escritura=True,
        )
    except crud_cita.CitaSolapadaError as conflicto:
        return ResultadoHerramienta(
            mensaje=(
                f"Esa hora no está disponible: {conflicto.mensaje} "
                "¿Quieres que busquemos otro hueco?"
            ),
            ok=False, es_escritura=True,
        )
    except Exception:
        # Cualquier fallo inesperado de BD: revertimos y respondemos con calma,
        # sin dejar que reviente la conversación.
        db.rollback()
        return ResultadoHerramienta(
            mensaje=(
                "No he podido registrar la cita por un problema técnico. "
                "Inténtalo de nuevo en un momento, por favor."
            ),
            ok=False, es_escritura=True,
        )

    return ResultadoHerramienta(
        mensaje=(
            f"Cita agendada correctamente (nº {nueva_cita.id}) para {especialidad} "
            f"el {_fecha_legible(fecha_hora)} con {empleado.nombre}."
        ),
        ok=True, es_escritura=True,
    )


# Mensaje único para "no es tuya o no existe": NO revela si la cita existe cuando
# pertenece a otro paciente (evita filtrar la agenda ajena por id).
_CITA_NO_ENCONTRADA = "No encuentro ninguna cita con ese número a tu nombre."


def _cita_del_cliente(
    db: Session, empresa_id: int, cliente_id: int, cita_id
):
    """Devuelve la cita SOLO si es del tenant Y del propio paciente, o None.

    COMPROBACIÓN DE PERTENENCIA (seguridad): `crud_cita.update_cita` se acota por
    `empresa_id` pero NO por paciente, y el asistente se ejecuta con la identidad
    del cliente del token. Sin este filtro, un paciente podría cancelar o mover la
    cita de OTRO de su misma clínica con solo acertar (o alucinar) su id. Nunca se
    confía en el id que venga del modelo: se resuelve contra la BD y se exige que
    `cliente_id` coincida. Si no existe o no es suya, se trata igual (None) para no
    revelar la existencia de citas ajenas.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Empresa (tenant) del paciente autenticado.
        cliente_id: Id del paciente autenticado (del token, nunca del modelo).
        cita_id: Identificador de cita propuesto por el modelo (no fiable).

    Returns:
        La `Cita` si pertenece al paciente, o None en cualquier otro caso.
    """
    # Un id no numérico o ausente (alucinación del modelo) no encuentra nada.
    try:
        cita_id_int = int(cita_id)
    except (TypeError, ValueError):
        return None

    db_cita = crud_cita.get_cita(db, cita_id=cita_id_int, empresa_id=empresa_id)
    if db_cita is None or db_cita.cliente_id != cliente_id:
        return None
    return db_cita


def consultar_mis_citas_real(
    db: Session, empresa_id: int, cliente_id: int, nombre_paciente: str = ""
) -> ResultadoHerramienta:
    """Lista, en lenguaje natural, las citas PRÓXIMAS del propio paciente.

    Se apoya en `crud_cita.get_citas` acotado por `empresa_id` Y `cliente_id`, de
    modo que jamás incluye citas de otros pacientes (aunque los ids colisionen
    entre tablas). La fecha va redactada en castellano (con la hora en 09:00) para
    que al modelo le baste copiarla. Además calcula los `marcadores`/`dias` de cada
    cita para la salvaguarda de completitud del `chat`.

    El resultado encabeza la lista con el nombre del paciente autenticado. No es
    decorativo: pone la identidad real DENTRO de los datos que el modelo recibe,
    y no solo en las instrucciones del sistema. Un modelo ignora una instrucción
    con mucha más facilidad que un dato que acaba de leer en la respuesta de una
    herramienta.
    """
    # Solo de ahora en adelante, igual que la pantalla de la aplicación móvil.
    # Antes se devolvía el historial completo, de modo que el asistente enumeraba
    # citas de días pasados mientras la pantalla mostraba únicamente las próximas:
    # el mismo paciente recibía dos respuestas distintas en el mismo minuto. Las
    # cuatro operaciones que ofrece el asistente —consultar, agendar, cancelar y
    # reprogramar— se refieren además a citas futuras; el historial es ruido.
    citas = crud_cita.get_citas(
        db, empresa_id=empresa_id, cliente_id=cliente_id,
        desde=datetime.datetime.now(),
    )
    if not citas:
        return ResultadoHerramienta(
            mensaje="El paciente no tiene ninguna cita próxima."
        )

    lineas = []
    marcadores = set()
    dias = set()
    for cita in citas:
        estado = cita.estado.value.capitalize() if cita.estado else "Pendiente"
        lineas.append(
            f"Cita nº {cita.id}: {_fecha_legible(cita.fecha_hora)}, "
            f"{cita.servicio_nombre or 'servicio'} con "
            f"{cita.empleado_nombre or 'el profesional'} (estado: {estado})."
        )
        # Marcadores de "esta cita ha sido mencionada": hora con y sin cero
        # inicial, nombre del profesional y del servicio. Son generosos a
        # propósito: solo queremos detectar respuestas SIN ningún dato.
        marcadores.add(cita.fecha_hora.strftime("%H:%M"))
        marcadores.add(f"{cita.fecha_hora.hour}:{cita.fecha_hora.minute:02d}")
        if cita.empleado_nombre:
            marcadores.add(cita.empleado_nombre)
        if cita.servicio_nombre:
            marcadores.add(cita.servicio_nombre)
        dias.add(str(cita.fecha_hora.day))

    return ResultadoHerramienta(
        mensaje=(f"Próximas citas de {nombre_paciente}:\n" if nombre_paciente
                 else "Próximas citas del paciente:\n") + "\n".join(lineas),
        marcadores=tuple(marcadores),
        dias=tuple(dias),
    )


def cancelar_cita_real(
    db: Session, empresa_id: int, cliente_id: int, cita_id
) -> ResultadoHerramienta:
    """Cancela (estado CANCELADA) una cita PROPIA del paciente autenticado.

    Verifica la pertenencia con `_cita_del_cliente` antes de tocar nada; si no es
    suya, responde como si no existiera (ok=False). La escritura pasa por
    `update_cita`. Nunca propaga una excepción al chat.
    """
    db_cita = _cita_del_cliente(db, empresa_id, cliente_id, cita_id)
    if db_cita is None:
        return ResultadoHerramienta(_CITA_NO_ENCONTRADA, ok=False, es_escritura=True)

    try:
        crud_cita.update_cita(
            db,
            cita_id=db_cita.id,
            cita=schemas.CitaUpdate(estado=models.EstadoCita.CANCELADA),
            empresa_id=empresa_id,
        )
    except Exception:
        db.rollback()
        return ResultadoHerramienta(
            mensaje=(
                "No he podido cancelar la cita por un problema técnico. "
                "Inténtalo de nuevo en un momento, por favor."
            ),
            ok=False, es_escritura=True,
        )
    return ResultadoHerramienta(
        mensaje=f"He cancelado correctamente la cita nº {db_cita.id} del paciente.",
        ok=True, es_escritura=True,
    )


def reprogramar_cita_real(
    db: Session, empresa_id: int, cliente_id: int, cita_id, fecha: str, hora: str
) -> ResultadoHerramienta:
    """Mueve una cita PROPIA a una nueva fecha/hora.

    Verifica la pertenencia antes de nada; si no es suya, responde como si no
    existiera (ok=False). La nueva fecha se valida en `update_cita` (solapamiento y
    "no mover al pasado"), cuyos errores se traducen a frases naturales. Nunca
    propaga una excepción al chat.
    """
    db_cita = _cita_del_cliente(db, empresa_id, cliente_id, cita_id)
    if db_cita is None:
        return ResultadoHerramienta(_CITA_NO_ENCONTRADA, ok=False, es_escritura=True)

    try:
        nueva_fecha = datetime.datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    except ValueError:
        return ResultadoHerramienta(
            mensaje=(
                f"No he podido interpretar la fecha '{fecha}' y la hora '{hora}'. "
                "Necesito la fecha como YYYY-MM-DD y la hora como HH:MM."
            ),
            ok=False, es_escritura=True,
        )

    try:
        crud_cita.update_cita(
            db,
            cita_id=db_cita.id,
            cita=schemas.CitaUpdate(fecha_hora=nueva_fecha),
            empresa_id=empresa_id,
        )
    except crud_cita.CitaEnPasadoError:
        return ResultadoHerramienta(
            mensaje="Esa fecha ya ha pasado. ¿Quieres que busquemos un hueco más adelante?",
            ok=False, es_escritura=True,
        )
    except crud_cita.CitaFueraDeHorarioError as fuera:
        return ResultadoHerramienta(
            mensaje=(
                f"{fuera.mensaje} ¿Quieres que busquemos un hueco dentro de ese horario?"
            ),
            ok=False, es_escritura=True,
        )
    except crud_cita.CitaSolapadaError as conflicto:
        return ResultadoHerramienta(
            mensaje=(
                f"Esa hora no está disponible: {conflicto.mensaje} "
                "¿Quieres que busquemos otro hueco?"
            ),
            ok=False, es_escritura=True,
        )
    except Exception:
        db.rollback()
        return ResultadoHerramienta(
            mensaje=(
                "No he podido reprogramar la cita por un problema técnico. "
                "Inténtalo de nuevo en un momento, por favor."
            ),
            ok=False, es_escritura=True,
        )
    return ResultadoHerramienta(
        mensaje=(
            f"He movido la cita nº {db_cita.id} del paciente al "
            f"{_fecha_legible(nueva_fecha)}."
        ),
        ok=True, es_escritura=True,
    )


def _ejecutar_tool(db: Session, current_user, tool_call) -> ResultadoHerramienta:
    """Ejecuta una tool_call del modelo y devuelve su ResultadoHerramienta.

    Enruta cada herramienta a su función real, SIEMPRE acotando al tenant del
    token (`current_user.empresa_id`) y, en las operaciones sobre citas, al
    propio paciente (`current_user.id`). Tolera argumentos JSON inválidos.
    """
    nombre = tool_call.function.name
    try:
        argumentos = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError:
        return ResultadoHerramienta(
            mensaje=f"No he podido interpretar los parámetros de '{nombre}'."
        )

    empresa_id = current_user.empresa_id
    cliente_id = current_user.id

    if nombre == "verificar_disponibilidad":
        return verificar_disponibilidad_real(
            db=db, empresa_id=empresa_id,
            especialidad=argumentos.get("especialidad"),
            fecha=argumentos.get("fecha_preferida"),
        )
    if nombre == "agendar_cita":
        return agendar_cita_real(
            db=db, empresa_id=empresa_id, cliente_id=cliente_id,
            especialidad=argumentos.get("especialidad"),
            fecha=argumentos.get("fecha"), hora=argumentos.get("hora"),
        )
    if nombre == "consultar_mis_citas":
        return consultar_mis_citas_real(
            db, empresa_id, cliente_id, getattr(current_user, "nombre", "")
        )
    if nombre == "cancelar_cita":
        return cancelar_cita_real(db, empresa_id, cliente_id, argumentos.get("cita_id"))
    if nombre == "reprogramar_cita":
        return reprogramar_cita_real(
            db, empresa_id, cliente_id,
            argumentos.get("cita_id"), argumentos.get("fecha"), argumentos.get("hora"),
        )
    return ResultadoHerramienta(mensaje=f"La herramienta '{nombre}' no está disponible.")


def _menciona_alguna_cita(respuesta: str, consulta: ResultadoHerramienta) -> bool:
    """True si la respuesta del modelo menciona AL MENOS UNA de las citas.

    Criterio GENEROSO a propósito (queremos detectar solo respuestas SIN ningún
    dato): una cita se considera mencionada si aparece cualquiera de sus
    marcadores —hora con o sin cero inicial, nombre del profesional o del
    servicio— o el número de su día del mes. Así, una redacción natural ("...con
    la Dra. Ruiz a las nueve...") se salva por el nombre del profesional, y solo
    una fórmula de cortesía vacía queda sin ningún marcador.
    """
    if not respuesta:
        return False
    texto = respuesta.lower()
    for marcador in consulta.marcadores:
        if marcador and marcador.lower() in texto:
            return True
    # El día del mes se comprueba con límite de palabra para que "1" no case
    # dentro de "16:00" ni de un número mayor.
    for dia in consulta.dias:
        if re.search(rf"\b{re.escape(dia)}\b", texto):
            return True
    return False


# Fórmulas con las que el modelo pide al paciente que se identifique. Se
# comparan sobre el texto sin acentos y en minúsculas.
_FORMULAS_DE_IDENTIDAD = (
    "eres tu", "¿eres", "eres ana", "es usted", "confirmar tu nombre",
    "confirmarme tu nombre", "confirmame tu nombre", "confirma tu nombre",
    "dime tu nombre", "decirme tu nombre", "quien eres", "identificate",
    "identificarte", "numero de paciente", "tu nombre completo",
)


def _sin_acentos(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar sin depender de la ortografía."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )


def _pide_identificarse(respuesta: str) -> bool:
    """¿El modelo está pidiendo al paciente que diga o confirme quién es?

    No debe hacerlo NUNCA: la identidad viene del testigo de sesión y el sistema
    ya se la ha dado. Preguntarla abre la puerta a que el paciente conteste otro
    nombre, y aunque los datos sigan acotados —eso lo garantiza el despachador—
    la conversación queda dando a entender lo contrario.

    Se observó en dos formas: inventarse un «número de paciente» inexistente y
    proponer directamente otra identidad («¿Eres Ana Ferrer?», con un apellido
    que el modelo mezcló de otra paciente).

    Es una heurística sobre texto, deliberadamente estrecha: solo busca fórmulas
    de identificación. Prefiere no disparar a disparar de más.
    """
    plano = _sin_acentos(respuesta)
    return any(f in plano for f in _FORMULAS_DE_IDENTIDAD)


def _aplicar_salvaguardas(
    respuesta: Optional[str],
    fallo_escritura: Optional[str],
    consulta: Optional[ResultadoHerramienta],
    nombre_paciente: str = "",
) -> str:
    """Blinda la respuesta final del modelo con las dos salvaguardas en código.

    Prioridad:
      1) Si una operación de ESCRITURA falló, se devuelve SU mensaje: nunca se
         deja que el modelo afirme un éxito que no ocurrió (lo más importante).
      2) Si la respuesta pide al paciente que se identifique, se sustituye por un
         texto que le recuerda en qué cuenta está. El asistente no debe preguntar
         nunca quién es: ya lo sabe.
      3) Si en el turno se consultaron citas (>=1) y la respuesta no menciona
         NINGUNA, se devuelve el listado formateado en lugar del texto del modelo.
      4) En caso contrario, se respeta la respuesta del modelo.
    """
    if fallo_escritura is not None:
        return fallo_escritura
    if respuesta and _pide_identificarse(respuesta):
        quien = f"la cuenta de {nombre_paciente}" if nombre_paciente else "tu cuenta"
        return (
            f"Estás en {quien}. Solo puedo consultar y gestionar tus propias citas, "
            "así que no necesito que me digas quién eres. ¿Quieres que te diga tus "
            "próximas citas?"
        )
    if consulta is not None and not _menciona_alguna_cita(respuesta or "", consulta):
        return consulta.mensaje
    return respuesta or ""


@router.post("/chat", response_model=schemas.ChatResponse)
async def chat(
    peticion: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_cliente),
):
    """Recibe un mensaje del paciente y devuelve la respuesta del asistente.

    SOLO para pacientes (`require_cliente`): el asistente opera sobre las citas
    del cliente del token, y los ids colisionan entre las tablas clientes y
    empleados, así que un empleado no debe entrar aquí (usa el escritorio). Un
    empleado recibe 403.
    """
    # El cliente del LLM es un singleton de módulo (ver arriba): no se crea aquí.

    # Anclaje temporal: el modelo no conoce la fecha real, así que se la
    # inyectamos en el system prompt en cada request para que pueda resolver
    # expresiones relativas ("mañana", "el viernes") a fecha ISO exacta.
    fecha_actual = datetime.date.today().isoformat()
    # Anclaje de IDENTIDAD: el nombre sale del token, nunca de lo que diga el
    # paciente. Sin este dato el modelo no tenía con qué contradecir a quien
    # afirmara ser otra persona, y llegaba a presentar las citas del propio
    # usuario como si fuesen de un tercero.
    system_prompt = (
        f"{SYSTEM_PROMPT}\n\nContexto del sistema: Hoy es {fecha_actual}. "
        f"Hablas con {current_user.nombre}."
    )

    # El system prompt siempre encabeza la conversación; a continuación se
    # inyecta el historial recibido para que el modelo tenga memoria de contexto.
    messages_for_llm = [{"role": "system", "content": system_prompt}]
    for msg in peticion.historial:
        messages_for_llm.append({"role": msg.role, "content": msg.content})

    # Herramientas que el modelo puede solicitar (function calling). Cada una se
    # ejecuta acotada al tenant del token y, las de citas, al propio paciente.
    tools_disponibles = [
        {
            "type": "function",
            "function": {
                "name": "verificar_disponibilidad",
                "description": (
                    "Consulta los huecos libres para una especialidad médica "
                    "en una fecha concreta."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "especialidad": {
                            "type": "string",
                            "description": "Especialidad médica solicitada, p. ej. 'dermatología'.",
                        },
                        "fecha_preferida": {
                            "type": "string",
                            "description": (
                                "La fecha solicitada por el usuario DEBE estar "
                                "estrictamente en formato ISO 8601 (YYYY-MM-DD). "
                                "Si el usuario dice 'mañana', calcula la fecha "
                                "exacta en YYYY-MM-DD."
                            ),
                        },
                    },
                    "required": ["especialidad", "fecha_preferida"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "agendar_cita",
                "description": (
                    "Guarda la cita DEFINITIVA del paciente en la base de datos. "
                    "Úsala solo cuando ya tengas confirmados la especialidad, el "
                    "día y la hora concretos. Esta acción es de escritura y crea "
                    "un registro real."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "especialidad": {
                            "type": "string",
                            "description": "Especialidad médica de la cita, p. ej. 'dermatología'.",
                        },
                        "fecha": {
                            "type": "string",
                            "description": (
                                "Día de la cita, estrictamente en formato ISO 8601 "
                                "(YYYY-MM-DD). Si el usuario dice 'mañana', calcula "
                                "la fecha exacta en YYYY-MM-DD."
                            ),
                        },
                        "hora": {
                            "type": "string",
                            "description": (
                                "Hora de la cita en formato 24h HH:MM (p. ej. "
                                "'16:00')."
                            ),
                        },
                    },
                    "required": ["especialidad", "fecha", "hora"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "consultar_mis_citas",
                "description": (
                    "Devuelve las citas del propio paciente con el que hablas, "
                    "incluido el número de cada una. Úsala cuando pregunte por sus "
                    "citas o antes de cancelar o reprogramar, para conocer el número."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancelar_cita",
                "description": (
                    "Cancela una cita del propio paciente. Requiere el número de "
                    "la cita (cita_id); si no lo conoces, consulta antes sus citas."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cita_id": {
                            "type": "integer",
                            "description": "Número de la cita a cancelar.",
                        },
                    },
                    "required": ["cita_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reprogramar_cita",
                "description": (
                    "Mueve una cita del propio paciente a una nueva fecha y hora. "
                    "Requiere el número de la cita (cita_id); si no lo conoces, "
                    "consulta antes sus citas."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cita_id": {
                            "type": "integer",
                            "description": "Número de la cita a reprogramar.",
                        },
                        "fecha": {
                            "type": "string",
                            "description": (
                                "Nuevo día, estrictamente en formato ISO 8601 "
                                "(YYYY-MM-DD)."
                            ),
                        },
                        "hora": {
                            "type": "string",
                            "description": "Nueva hora en formato 24h HH:MM.",
                        },
                    },
                    "required": ["cita_id", "fecha", "hora"],
                },
            },
        },
    ]

    # Rastreo para las salvaguardas en código (no dependen del modelo):
    #  - fallo_escritura: mensaje de la ÚLTIMA operación de escritura si falló
    #    (None si no hubo escritura o la última salió bien). Un reintento exitoso
    #    lo limpia, para no pisar un éxito real.
    #  - consulta: último ResultadoHerramienta de consultar_mis_citas con >=1 cita.
    fallo_escritura = None
    consulta = None

    # Consumo de tokens del turno, para poder medirlo en vez de estimarlo.
    consumo = ConsumoTokens()

    # Bucle de rondas: mientras el modelo pida herramientas, las ejecutamos TODAS
    # y le volvemos a llamar CON las herramientas, hasta que produzca texto (su
    # respuesta final) o se agote el tope de rondas. Esto permite encadenar
    # (p. ej. verificar disponibilidad y luego reservar en el mismo turno).
    for _ in range(MAX_RONDAS):
        try:
            completion = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages_for_llm,
                tools=tools_disponibles,
                temperature=TEMPERATURA,
                max_tokens=512,
            )
        except OpenAIError:
            # El proveedor del modelo está caído, es inaccesible o ha agotado el
            # tiempo de espera (APITimeoutError es un OpenAIError). Nunca un 500 ni
            # una excepción hacia el paciente: se responde con una frase natural.
            consumo.registrar()
            return schemas.ChatResponse(
                respuesta=(
                    "Lo siento, el asistente no está disponible en este momento. "
                    "Inténtalo de nuevo en unos minutos o contacta con recepción."
                )
            )

        consumo.sumar(completion)
        mensaje = completion.choices[0].message

        # Sin tool_calls: es la respuesta final. La blindamos con las salvaguardas
        # antes de devolverla (fallo de escritura -> su mensaje; consulta sin datos
        # en la respuesta -> el listado formateado).
        if not mensaje.tool_calls:
            consumo.registrar()
            return schemas.ChatResponse(
                respuesta=_aplicar_salvaguardas(
                    mensaje.content, fallo_escritura, consulta,
                    getattr(current_user, "nombre", "")
                )
            )

        # Reinyectamos el mensaje del asistente (con sus tool_calls) para mantener
        # el hilo, y a continuación ejecutamos TODAS las herramientas pedidas
        # (Llama 3.1 suele pedir varias): cada resultado se enlaza por su
        # tool_call_id. El contenido del rol "tool" son SOLO datos, sin
        # instrucciones de estilo (esas viven en el system prompt).
        messages_for_llm.append(mensaje.model_dump(exclude_none=True))
        for tool_call in mensaje.tool_calls:
            resultado = _ejecutar_tool(db, current_user, tool_call)
            messages_for_llm.append(
                {
                    "role": "tool",
                    "content": resultado.mensaje,
                    "tool_call_id": tool_call.id,
                }
            )
            # Actualizamos el rastreo para las salvaguardas.
            if resultado.es_escritura:
                fallo_escritura = None if resultado.ok else resultado.mensaje
            elif resultado.marcadores or resultado.dias:
                consulta = resultado

    # Tope de rondas alcanzado. Si la última escritura falló, prevalece su mensaje
    # (no afirmar un éxito que no ocurrió) sobre la disculpa genérica.
    consumo.registrar()
    if fallo_escritura is not None:
        return schemas.ChatResponse(respuesta=fallo_escritura)
    return schemas.ChatResponse(
        respuesta=(
            "Lo siento, me he hecho un lío procesando tu petición. ¿Puedes "
            "planteármela de otra forma? Si prefieres, recepción puede ayudarte."
        )
    )
