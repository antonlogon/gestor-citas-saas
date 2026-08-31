"""BLOQUE H: listado de citas — orden cronológico y filtro de "próximas".

Dos comportamientos que consume directamente la pantalla principal del móvil:

1. El listado sale ordenado por fecha. Sin ``ORDER BY`` el motor devolvía las
   filas en orden de clave primaria, así que el paciente veía sus citas en el
   orden en que se habían creado y no en el que le tocan.
2. ``?proximas=true`` recorta el listado a partir de ahora. Es un corte
   PURAMENTE TEMPORAL: una cancelación futura sigue apareciendo, con su
   distintivo, porque el paciente necesita enterarse de ella.

El filtro es OPT-IN a propósito: el escritorio de la clínica necesita seguir
viendo el histórico completo, y eso también se prueba aquí.
"""
from datetime import datetime, timedelta

from app import models
from app.database import SessionLocal


def _insertar(datos, fecha, estado=models.EstadoCita.PENDIENTE):
    """Inserta una cita directamente por sesión y devuelve su id.

    No se usa la API a propósito: parte de los casos son citas pasadas, que la
    API rechaza por diseño, y otras nacen ya canceladas. Aquí se prueba el
    LISTADO, no la creación, así que interesa poder construir cualquier
    escenario sin pelearse con las invariantes de escritura.
    """
    db = SessionLocal()
    try:
        cita = models.Cita(
            empresa_id=datos.a.empresa_id,
            cliente_id=datos.a.cliente_id,
            empleado_id=datos.a.admin_id,
            servicio_id=datos.a.servicio_id,
            fecha_hora=fecha.replace(microsecond=0),
            estado=estado,
        )
        db.add(cita)
        db.commit()
        db.refresh(cita)
        return cita.id
    finally:
        db.close()


def _ids(respuesta):
    return [c["id"] for c in respuesta.json()]


# --- H1: el listado sale por fecha, no por id -------------------------------
def test_listado_en_orden_cronologico(client, auth, datos_base):
    ahora = datetime.now()
    # Se insertan DESORDENADAS a propósito: si el endpoint no ordenara, saldrían
    # por id, que aquí es justo el orden contrario al cronológico. Un test que
    # las insertara ya ordenadas pasaría igual sin ORDER BY y no probaría nada.
    tercera = _insertar(datos_base, ahora + timedelta(days=3))
    primera = _insertar(datos_base, ahora + timedelta(days=1))
    segunda = _insertar(datos_base, ahora + timedelta(days=2))

    r = client.get("/citas/", headers=auth(datos_base.a.token_personal))
    assert r.status_code == 200, r.text
    assert _ids(r) == [primera, segunda, tercera]


# --- H2: proximas descarta lo que ya pasó -----------------------------------
def test_proximas_excluye_las_pasadas(client, auth, datos_base):
    ahora = datetime.now()
    _insertar(datos_base, ahora - timedelta(days=1))
    futura = _insertar(datos_base, ahora + timedelta(days=1))

    r = client.get("/citas/?proximas=true", headers=auth(datos_base.a.token_cliente))
    assert r.status_code == 200, r.text
    assert _ids(r) == [futura]


# --- H3: el corte es temporal, NO por estado --------------------------------
def test_proximas_conserva_las_canceladas_que_aun_no_han_llegado(
    client, auth, datos_base
):
    """Una cancelación futura debe seguir viéndose; una pasada, no.

    Es la distinción sobre la que se apoya toda la decisión: si la clínica
    cancela la cita del martes y la aplicación la borra, el paciente no recibe
    la noticia, recibe un hueco. Y un hueco es indistinguible de un fallo de
    carga o de un recuerdo equivocado. El distintivo "CANCELADA" de la interfaz
    existe precisamente para poder decir esto. Ocultarlas se evaluó y se
    descartó: el ruido de una cita tachada cuesta una línea, y no enterarse de
    una cancelación cuesta un viaje en balde.
    """
    ahora = datetime.now()
    _insertar(datos_base, ahora - timedelta(days=1), models.EstadoCita.CANCELADA)
    cancelada = _insertar(
        datos_base, ahora + timedelta(days=1), models.EstadoCita.CANCELADA
    )
    viva = _insertar(datos_base, ahora + timedelta(days=2))

    r = client.get("/citas/?proximas=true", headers=auth(datos_base.a.token_cliente))
    assert r.status_code == 200, r.text
    assert _ids(r) == [cancelada, viva]


# --- H4: guarda de regresión del escritorio ---------------------------------
def test_por_defecto_se_sigue_viendo_pasado_y_canceladas(client, auth, datos_base):
    """El filtro es opt-in: sin el parámetro, la agenda de la clínica no cambia.

    Si algún día se invirtiera el valor por defecto, el escritorio perdería el
    histórico y las canceladas sin que fallara ninguna otra prueba.
    """
    ahora = datetime.now()
    pasada = _insertar(datos_base, ahora - timedelta(days=1))
    cancelada = _insertar(
        datos_base, ahora + timedelta(days=1), models.EstadoCita.CANCELADA
    )
    viva = _insertar(datos_base, ahora + timedelta(days=2))

    r = client.get("/citas/", headers=auth(datos_base.a.token_personal))
    assert r.status_code == 200, r.text
    assert _ids(r) == [pasada, cancelada, viva]
