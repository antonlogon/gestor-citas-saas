"""BLOQUE D: email como identidad única en TODA la plataforma.

Una persona, una cuenta: el email no puede repetirse ni entre clientes, ni
entre empleados, ni de forma cruzada entre ambas tablas y entre empresas. La
unicidad cruzada la impone la capa de aplicación (crud_usuario) y debe dar 409,
nunca un 500 por IntegrityError. El único caso que NO debe chocar es actualizar
un cliente conservando su propio email.
"""


# --- Cliente con el email de un EMPLEADO de OTRA empresa -> 409 -------------
def test_cliente_con_email_de_empleado_otra_empresa(client, auth, datos_base):
    r = client.post(
        "/clientes/",
        json={"nombre": "Choque", "email": datos_base.b.admin_email,
              "telefono": "600999888", "password": "password123"},
        headers=auth(datos_base.a.token_admin),
    )
    assert r.status_code == 409, r.text


# --- Empleado con el email de un CLIENTE existente -> 409 -------------------
def test_empleado_con_email_de_cliente(client, auth, datos_base):
    r = client.post(
        "/empleados/",
        json={"nombre": "Choque", "email": datos_base.b.cliente_email,
              "password": "password123"},
        headers=auth(datos_base.a.token_admin),
    )
    assert r.status_code == 409, r.text


# --- Dos clientes con el mismo email en la MISMA empresa -> 409 -------------
def test_dos_clientes_mismo_email_misma_empresa(client, auth, datos_base):
    cab = auth(datos_base.a.token_admin)
    cuerpo = {"nombre": "Uno", "email": "repe@test.com",
              "telefono": "600111222", "password": "password123"}
    assert client.post("/clientes/", json=cuerpo, headers=cab).status_code == 201
    r = client.post("/clientes/", json={**cuerpo, "nombre": "Dos"}, headers=cab)
    assert r.status_code == 409, r.text


# --- Registro con un email ya usado -> 409 (no 500) -------------------------
def test_registro_email_ya_usado(client, datos_base):
    r = client.post(
        "/registro/",
        json={"empresa_nombre": "Otra", "slug": "otra-clinica",
              "admin_nombre": "X", "admin_email": datos_base.a.cliente_email,
              "admin_password": "password123"},
    )
    assert r.status_code == 409, r.text


# --- PUT de un cliente SIN cambiar su email -> 200 (no choca consigo mismo) --
def test_put_cliente_conservando_email(client, auth, datos_base):
    r = client.put(
        f"/clientes/{datos_base.a.cliente_id}",
        json={"nombre": "Renombrado", "email": datos_base.a.cliente_email},
        headers=auth(datos_base.a.token_admin),
    )
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Renombrado"
