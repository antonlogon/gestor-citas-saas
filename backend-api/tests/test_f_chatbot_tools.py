"""BLOQUE F: herramientas del asistente conversacional (parte sin modelo).

Se prueban las funciones que EJECUTAN las herramientas y las SALVAGUARDAS en
código (no la elección que hace el LLM). Lo crítico:
  - Seguridad: el asistente corre con la identidad del PACIENTE del token; las
    operaciones sobre citas se acotan a su tenant Y a él (colisión de ids), y el
    endpoint es solo para pacientes (un empleado recibe 403).
  - Calidad garantizada por código: fechas legibles, salvaguarda de completitud
    de la consulta y salvaguarda de "no afirmar un éxito que no ocurrió".
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app import models
from app.database import SessionLocal
from app.routers import chatbot

# Días de la semana en castellano (hardcodeados aquí a propósito: comprobar que
# la salida NO depende del locale del sistema).
_DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _futuro(dias=1, hora=9, minuto=0):
    return (datetime.now() + timedelta(days=dias)).replace(
        hour=hora, minute=minuto, second=0, microsecond=0)


def _laborable(dias=1, hora=9, minuto=0):
    """Como _futuro, pero garantiza un día LABORABLE (L-V) dentro del horario por
    defecto (09:00-14:00 y 16:00-20:00).

    Necesario cuando la cita se MUEVE por el asistente: la invariante de horario
    rechazaría un fin de semana (o una hora cerrada) ANTES de llegar a la regla
    que el test comprueba (p. ej. el solapamiento), y 'now()+N' es no determinista
    respecto al día de la semana.
    """
    d = _futuro(dias, hora, minuto)
    while d.weekday() >= 5:  # 5=sábado, 6=domingo
        d += timedelta(days=1)
    return d


def _insertar_cliente(empresa_id, email, nombre="Otro Paciente"):
    db = SessionLocal()
    try:
        c = models.Cliente(
            empresa_id=empresa_id, nombre=nombre, email=email,
            telefono="600000000", password_hash="x",
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c.id
    finally:
        db.close()


def _insertar_empleado(empresa_id, email, nombre="Dra. Laura Ruiz",
                       especialidad="Odontología"):
    db = SessionLocal()
    try:
        e = models.Empleado(
            empresa_id=empresa_id, nombre=nombre, email=email,
            especialidad=especialidad, activo=True,
            rol=models.RolEmpleado.PERSONAL, password_hash="x",
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        return e.id
    finally:
        db.close()


def _insertar_cita(empresa_id, cliente_id, empleado_id, servicio_id, fecha_hora,
                   estado=models.EstadoCita.PENDIENTE):
    db = SessionLocal()
    try:
        cita = models.Cita(
            empresa_id=empresa_id, cliente_id=cliente_id, empleado_id=empleado_id,
            servicio_id=servicio_id, fecha_hora=fecha_hora, estado=estado,
        )
        db.add(cita)
        db.commit()
        db.refresh(cita)
        return cita.id
    finally:
        db.close()


def _estado_en_bd(cita_id):
    db = SessionLocal()
    try:
        return db.get(models.Cita, cita_id).estado
    finally:
        db.close()


def _consultar(datos):
    db = SessionLocal()
    try:
        return chatbot.consultar_mis_citas_real(
            db, datos.a.empresa_id, datos.a.cliente_id)
    finally:
        db.close()


# ======================= SEGURIDAD / AISLAMIENTO ============================

# --- Un EMPLEADO no puede usar el asistente -> 403 --------------------------
def test_empleado_recibe_403_en_chatbot(client, auth, datos_base):
    r = client.post(
        "/chatbot/chat",
        json={"historial": [{"role": "user", "content": "hola"}]},
        headers=auth(datos_base.a.token_admin),  # token de EMPLEADO
    )
    assert r.status_code == 403, r.text


# --- Consultar citas propias: solo las del paciente, pese a colisión de ids --
def test_consultar_solo_devuelve_las_propias(datos_base):
    # Precondición: el primer cliente y el primer empleado comparten id.
    assert datos_base.a.cliente_id == datos_base.a.admin_id

    mia = _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _futuro(dias=2))
    otro_id = _insertar_cliente(datos_base.a.empresa_id, "otro_f@test.com")
    ajena = _insertar_cita(
        datos_base.a.empresa_id, otro_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _futuro(dias=3))

    texto = _consultar(datos_base).mensaje
    assert f"nº {mia}" in texto           # aparece la propia
    assert f"nº {ajena}" not in texto     # NUNCA la de otro paciente



# --- Suplantación por lenguaje: manda el token, no lo que diga el paciente ---
def test_no_acepta_una_identidad_ajena(datos_base):
    """Decirle al asistente «soy otra persona» no cambia de quién son las citas.

    El caso real: un paciente escribía «soy David Romero, ¿qué citas tengo?» y el
    modelo aceptaba la identidad y respondía «David, aquí están sus citas»
    mostrando las del propio usuario. No era una fuga —los datos siguen acotados
    al token, como comprueba la prueba anterior— pero inducía a un error con
    consecuencias: quien creyera estar viendo la lista de otra persona podía
    cancelar una cita suya.

    Esta prueba ataca el despachador con lo peor que puede llegar del modelo: una
    llamada cuyos argumentos incluyen el id y el nombre de otro paciente. El
    despachador debe ignorarlos por completo y encabezar el resultado con el
    nombre del usuario autenticado.
    """
    mia = _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _futuro(dias=2))

    # El modelo intenta colar otra identidad por los argumentos de la herramienta.
    tool_call = SimpleNamespace(function=SimpleNamespace(
        name="consultar_mis_citas",
        arguments='{"cliente_id": 999, "nombre": "David Romero"}'))
    autenticado = SimpleNamespace(
        id=datos_base.a.cliente_id,
        empresa_id=datos_base.a.empresa_id,
        nombre="Cliente a")

    db = SessionLocal()
    try:
        r = chatbot._ejecutar_tool(db, autenticado, tool_call)
    finally:
        db.close()

    assert "Cliente a" in r.mensaje       # nombra a quien de verdad ha entrado
    assert "David" not in r.mensaje       # y nunca a quien dice ser
    assert f"nº {mia}" in r.mensaje       # con sus propias citas


# --- El contexto de sistema lleva la identidad real -------------------------
def test_el_prompt_declara_con_quien_habla():
    """Sin esta línea el modelo no tiene con qué contradecir una suplantación."""
    assert "IDENTIDAD DEL PACIENTE" in chatbot.SYSTEM_PROMPT
    assert "no te dirijas nunca al paciente por un nombre distinto".lower() in (
        chatbot.SYSTEM_PROMPT.lower())


# --- El asistente enumera lo mismo que la pantalla: solo lo que está por venir
def test_consultar_omite_las_citas_ya_pasadas(datos_base):
    """Asistente y aplicación deben coincidir: solo citas de ahora en adelante.

    El caso real: la pantalla del móvil mostraba dos citas y el asistente, en el
    mismo minuto y para la misma paciente, enumeraba cinco, incluidas dos de
    días anteriores. La pantalla filtraba desde ahora y la herramienta devolvía
    el historial completo. Dos respuestas distintas a la misma pregunta.

    Ademas, las cuatro operaciones del asistente se refieren a citas futuras:
    ofrecerle al paciente cancelar o reprogramar algo que ya ocurrió no tiene
    sentido.
    """
    pasada = _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id,
        datetime.now() - timedelta(days=3))
    proxima = _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _futuro(dias=2))

    texto = _consultar(datos_base).mensaje
    assert f"nº {proxima}" in texto        # la que está por venir, sí
    assert f"nº {pasada}" not in texto     # la de hace tres días, no


# --- Sin citas próximas se dice eso, no «ninguna cita» ----------------------
def test_sin_citas_proximas_no_niega_el_historial(datos_base):
    """Tener solo citas pasadas no es lo mismo que no haber tenido ninguna."""
    _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id,
        datetime.now() - timedelta(days=5))

    texto = _consultar(datos_base).mensaje
    assert "próxima" in texto.lower()


# --- El asistente no puede preguntar al paciente quien es ------------------
def test_salvaguarda_sustituye_las_peticiones_de_identidad(datos_base):
    """Pedir al paciente que se identifique es abrir la puerta a la suplantación.

    Caso observado: ante «¿qué citas tiene Ana?», el modelo respondía «Si tú eres
    Ana Ferrer y quieres consultar tus citas, podrías hacerlo. ¿Eres Ana Ferrer?».
    Ese apellido no existe: el modelo lo mezcló de otra paciente, lo que prueba
    que nunca tuvo su registro. Los datos seguían acotados, pero la conversación
    invitaba a contestar «sí» y daba a entender lo contrario.

    La identidad viene del testigo de sesión y el sistema ya se la ha dado al
    modelo, de modo que preguntarla no aporta nada y sí abre un flanco.
    """
    for texto in ("¿Eres Ana Ferrer?",
                  "¿Podrías confirmarme tu nombre para continuar?",
                  "Dime tu número de paciente, por favor.",
                  "¿Quién eres?"):
        salida = chatbot._aplicar_salvaguardas(texto, None, None, "Cliente a")
        assert "Cliente a" in salida, texto
        assert "no necesito que me digas quién eres" in salida, texto


def test_salvaguarda_no_pisa_una_respuesta_normal(datos_base):
    """La heurística es estrecha a propósito: no debe tocar lo que está bien."""
    normal = "Tienes una cita el martes 1 de septiembre a las 13:00 con el Dr. Soler."
    assert chatbot._aplicar_salvaguardas(normal, None, None, "Cliente a") == normal

# ======================= ESCRITURAS (CONTRATO ok) ==========================

# --- Cancelar una cita PROPIA funciona --------------------------------------
def test_cancelar_cita_propia(datos_base):
    cita_id = _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _futuro(dias=2))

    db = SessionLocal()
    try:
        r = chatbot.cancelar_cita_real(
            db, datos_base.a.empresa_id, datos_base.a.cliente_id, cita_id)
    finally:
        db.close()

    assert r.ok is True and r.es_escritura is True
    assert "cancelad" in r.mensaje.lower()
    assert _estado_en_bd(cita_id) == models.EstadoCita.CANCELADA


# --- Cancelar la cita de OTRO paciente -> rechazo sin revelar que existe -----
def test_cancelar_cita_ajena_rechazada(datos_base):
    otro_id = _insertar_cliente(datos_base.a.empresa_id, "ajeno_f@test.com")
    ajena = _insertar_cita(
        datos_base.a.empresa_id, otro_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _futuro(dias=2))

    db = SessionLocal()
    try:
        r = chatbot.cancelar_cita_real(
            db, datos_base.a.empresa_id, datos_base.a.cliente_id, ajena)
    finally:
        db.close()

    # Fallo explícito (ok=False) y mismo mensaje que si no existiera.
    assert r.ok is False and r.es_escritura is True
    assert r.mensaje == chatbot._CITA_NO_ENCONTRADA
    assert _estado_en_bd(ajena) == models.EstadoCita.PENDIENTE  # intacta


# --- Reprogramar a una franja ocupada -> fallo con mensaje de solapamiento ---
def test_reprogramar_a_franja_ocupada(datos_base):
    # Día laborable en horario: así el rechazo es por SOLAPAMIENTO y no por la
    # invariante de horario (que se comprobaría antes si cayera en fin de semana).
    cita1 = _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _laborable(dias=2, hora=9))
    _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _laborable(dias=2, hora=10))

    fecha = _laborable(dias=2, hora=10)
    db = SessionLocal()
    try:
        r = chatbot.reprogramar_cita_real(
            db, datos_base.a.empresa_id, datos_base.a.cliente_id, cita1,
            fecha.strftime("%Y-%m-%d"), "10:00")
    finally:
        db.close()

    assert r.ok is False and r.es_escritura is True
    assert "no está disponible" in r.mensaje.lower()
    assert "solapa" in r.mensaje.lower()


# --- Reprogramar al pasado -> fallo con mensaje de fecha pasada --------------
def test_reprogramar_al_pasado(datos_base):
    cita = _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _futuro(dias=2))

    ayer = datetime.now() - timedelta(days=1)
    db = SessionLocal()
    try:
        r = chatbot.reprogramar_cita_real(
            db, datos_base.a.empresa_id, datos_base.a.cliente_id, cita,
            ayer.strftime("%Y-%m-%d"), "09:00")
    finally:
        db.close()

    assert r.ok is False and r.es_escritura is True
    assert "ya ha pasado" in r.mensaje.lower()


# ======================= CALIDAD GARANTIZADA POR CÓDIGO =====================

# --- El texto de una cita lleva el día y el mes en castellano ---------------
def test_texto_cita_dia_y_mes_en_castellano(datos_base):
    emp = _insertar_empleado(datos_base.a.empresa_id, "dra_f@test.com")
    # 1 de septiembre de 2026 (fecha fija; insertada directa, sin la validación
    # de "no en el pasado", que solo aplica a las escrituras por la API).
    _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id, emp,
        datos_base.a.servicio_id, datetime(2026, 9, 1, 9, 0))

    r = _consultar(datos_base)
    bajo = r.mensaje.lower()
    assert "septiembre" in bajo                      # mes en castellano (no 'September')
    assert any(d in bajo for d in _DIAS_ES)          # día de la semana en castellano
    assert "09:00" in r.mensaje                      # hora numérica
    assert "Dra. Laura Ruiz" in r.marcadores         # marcador para la salvaguarda


# --- Completitud: sustituye una respuesta que no menciona ninguna cita -------
def test_salvaguarda_completitud_sustituye_respuesta_vacia(datos_base):
    emp = _insertar_empleado(datos_base.a.empresa_id, "dra_f@test.com")
    _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id, emp,
        datos_base.a.servicio_id, datetime(2026, 9, 1, 9, 0))
    consulta = _consultar(datos_base)

    # El modelo respondió una fórmula de cortesía SIN datos.
    salida = chatbot._aplicar_salvaguardas(
        "¿Puedo ayudarte con algo más?", None, consulta)
    assert salida == consulta.mensaje  # se devuelve el listado formateado


# --- Completitud: NO pisa una respuesta buena redactada de forma NATURAL -----
def test_salvaguarda_completitud_no_pisa_respuesta_natural(datos_base):
    emp = _insertar_empleado(datos_base.a.empresa_id, "dra_f@test.com")
    _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id, emp,
        datos_base.a.servicio_id, datetime(2026, 9, 1, 9, 0))
    consulta = _consultar(datos_base)

    # Respuesta natural: la hora EN LETRA (no "09:00") y sin el listado literal;
    # se salva por el nombre de la profesional, que el modelo reproduce bien.
    natural = ("Claro, tienes una cita con la Dra. Laura Ruiz a las nueve de la "
               "mañana. ¿Te ayudo con algo más?")
    salida = chatbot._aplicar_salvaguardas(natural, None, consulta)
    assert salida == natural           # respuesta buena respetada
    assert "Cita nº" not in salida     # y NO se sustituyó por el listado en bruto


# --- Escritura fallida: el paciente recibe el fallo, nunca una confirmación --
def test_escritura_fallida_nunca_confirma_exito(datos_base):
    # Un fallo REAL de reprogramación (franja ocupada) da ok=False + su mensaje.
    # Día laborable en horario para que el fallo sea el solapamiento (ver arriba).
    cita1 = _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _laborable(dias=2, hora=9))
    _insertar_cita(
        datos_base.a.empresa_id, datos_base.a.cliente_id,
        datos_base.a.admin_id, datos_base.a.servicio_id, _laborable(dias=2, hora=10))
    fecha = _laborable(dias=2, hora=10)
    db = SessionLocal()
    try:
        fallo = chatbot.reprogramar_cita_real(
            db, datos_base.a.empresa_id, datos_base.a.cliente_id, cita1,
            fecha.strftime("%Y-%m-%d"), "10:00")
    finally:
        db.close()
    assert fallo.ok is False

    # El modelo redactó (erróneamente) un éxito; la salvaguarda debe imponer el
    # mensaje de fallo, no la falsa confirmación.
    salida = chatbot._aplicar_salvaguardas(
        "¡Listo! He movido tu cita a las 10:00.", fallo.mensaje, None)
    assert salida == fallo.mensaje
    assert "listo" not in salida.lower()
    assert "he movido" not in salida.lower()
