"""BLOQUE E: aislamiento multi-tenant (la afirmación central del producto).

Con dos empresas sembradas, un empleado de la empresa A no debe ver, consultar,
modificar, borrar ni referenciar recursos de la empresa B. Los accesos por id a
recursos de otro tenant devuelven 404 (no 403): no se revela ni la existencia
del recurso.
"""
DIA = "2030-02-01"


def _crear_cita_en_b(client, auth, datos):
    """Crea una cita en la empresa B (con su propio admin) y devuelve su id."""
    r = client.post(
        "/citas/",
        json={
            "fecha_hora": f"{DIA}T09:00:00",
            "cliente_id": datos.b.cliente_id,
            "empleado_id": datos.b.admin_id,
            "servicio_id": datos.b.servicio_id,
        },
        headers=auth(datos.b.token_admin),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- A no ve clientes, servicios ni citas de B al listar --------------------
def test_listados_no_incluyen_a_la_otra_empresa(client, auth, datos_base):
    cita_b = _crear_cita_en_b(client, auth, datos_base)
    cab = auth(datos_base.a.token_admin)

    clientes = client.get("/clientes/", headers=cab).json()
    assert all(c["empresa_id"] == datos_base.a.empresa_id for c in clientes)
    assert datos_base.b.cliente_id not in [c["id"] for c in clientes]

    servicios = client.get("/servicios/", headers=cab).json()
    assert all(s["empresa_id"] == datos_base.a.empresa_id for s in servicios)
    assert datos_base.b.servicio_id not in [s["id"] for s in servicios]

    citas = client.get("/citas/", headers=cab).json()
    assert cita_b not in [c["id"] for c in citas]


# --- Acceso por id a recursos de B -> 404 (no 403) --------------------------
def test_acceso_por_id_a_recursos_de_b_da_404(client, auth, datos_base):
    cita_b = _crear_cita_en_b(client, auth, datos_base)
    cab = auth(datos_base.a.token_admin)
    assert client.get(f"/clientes/{datos_base.b.cliente_id}", headers=cab).status_code == 404
    assert client.get(f"/servicios/{datos_base.b.servicio_id}", headers=cab).status_code == 404
    assert client.get(f"/citas/{cita_b}", headers=cab).status_code == 404


# --- A no puede modificar ni borrar recursos de B -> 404 --------------------
def test_no_puede_modificar_ni_borrar_recursos_de_b(client, auth, datos_base):
    cab = auth(datos_base.a.token_admin)
    assert client.put(
        f"/clientes/{datos_base.b.cliente_id}", json={"nombre": "Hackeado"}, headers=cab
    ).status_code == 404
    assert client.delete(
        f"/clientes/{datos_base.b.cliente_id}", headers=cab
    ).status_code == 404
    assert client.put(
        f"/servicios/{datos_base.b.servicio_id}", json={"precio": 1}, headers=cab
    ).status_code == 404
    assert client.delete(
        f"/empleados/{datos_base.b.admin_id}", headers=cab
    ).status_code == 404


# --- A no puede crear una cita que referencie a cliente/empleado de B -> 404 -
def test_no_puede_crear_cita_referenciando_a_b(client, auth, datos_base):
    cab = auth(datos_base.a.token_admin)
    base = {
        "fecha_hora": f"{DIA}T12:00:00",
        "cliente_id": datos_base.a.cliente_id,
        "empleado_id": datos_base.a.admin_id,
        "servicio_id": datos_base.a.servicio_id,
    }
    # Cliente de B en una cita de A -> el recurso "no existe" en el tenant A.
    r_cliente = client.post("/citas/", json={**base, "cliente_id": datos_base.b.cliente_id},
                            headers=cab)
    assert r_cliente.status_code == 404, r_cliente.text
    # Empleado de B en una cita de A -> 404.
    r_empleado = client.post("/citas/", json={**base, "empleado_id": datos_base.b.admin_id},
                             headers=cab)
    assert r_empleado.status_code == 404, r_empleado.text
