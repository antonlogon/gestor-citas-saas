package org.example.frontenddesktop.models;

import java.util.Map;

/**
 * Modelo de datos de un paciente. En el backend corresponde al recurso
 * {@code clientes} (FastAPI, esquema de salida {@code schemas.Cliente}). Es
 * inmutable: se construye a partir del JSON recibido mediante {@link #fromJson(Map)}.
 *
 * <p>Campos que devuelve la API: {@code id}, {@code empresa_id}, {@code nombre},
 * {@code email} y {@code telefono}.
 */
public class Cliente {

    private final Integer id;
    private final Integer empresaId;
    private final String nombre;
    private final String email;
    private final String telefono;

    public Cliente(Integer id, Integer empresaId, String nombre, String email, String telefono) {
        this.id = id;
        this.empresaId = empresaId;
        this.nombre = nombre;
        this.email = email;
        this.telefono = telefono;
    }

    /**
     * Construye un {@link Cliente} a partir de un objeto JSON ya parseado (mapa
     * clave/valor). Las claves coinciden con las que devuelve la API; las
     * ausentes quedan como {@code null}.
     */
    public static Cliente fromJson(Map<String, Object> json) {
        return new Cliente(
                asInt(json.get("id")),
                asInt(json.get("empresa_id")),
                asString(json.get("nombre")),
                asString(json.get("email")),
                asString(json.get("telefono"))
        );
    }

    public Integer getId() {
        return id;
    }

    public Integer getEmpresaId() {
        return empresaId;
    }

    public String getNombre() {
        return nombre;
    }

    public String getEmail() {
        return email;
    }

    public String getTelefono() {
        return telefono;
    }

    // --- Utilidades de conversión desde el JSON parseado ---

    private static Integer asInt(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            return Integer.valueOf(value.toString().trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String asString(Object value) {
        return value == null ? null : value.toString();
    }
}
