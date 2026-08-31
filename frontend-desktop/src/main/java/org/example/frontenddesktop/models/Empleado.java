package org.example.frontenddesktop.models;

import java.util.Map;

/**
 * Modelo de datos de un empleado (profesional). Refleja el esquema de salida de
 * la API de FastAPI ({@code schemas.Empleado}) para el recurso {@code /empleados/}.
 * Es inmutable: se construye a partir del JSON recibido mediante
 * {@link #fromJson(Map)}. Sigue el mismo patrón que {@link Cliente}.
 *
 * <p>Campos que devuelve la API: {@code id}, {@code empresa_id}, {@code nombre},
 * {@code email}, {@code especialidad}, {@code activo} y {@code rol}.
 */
public class Empleado {

    private final Integer id;
    private final Integer empresaId;
    private final String nombre;
    private final String email;
    private final String especialidad;
    private final Boolean activo;
    private final String rol;

    public Empleado(Integer id, Integer empresaId, String nombre, String email,
                    String especialidad, Boolean activo, String rol) {
        this.id = id;
        this.empresaId = empresaId;
        this.nombre = nombre;
        this.email = email;
        this.especialidad = especialidad;
        this.activo = activo;
        this.rol = rol;
    }

    /**
     * Construye un {@link Empleado} a partir de un objeto JSON ya parseado. Las
     * claves coinciden con las que devuelve la API; las ausentes quedan nulas.
     */
    public static Empleado fromJson(Map<String, Object> json) {
        return new Empleado(
                asInt(json.get("id")),
                asInt(json.get("empresa_id")),
                asString(json.get("nombre")),
                asString(json.get("email")),
                asString(json.get("especialidad")),
                asBool(json.get("activo")),
                asString(json.get("rol"))
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

    public String getEspecialidad() {
        return especialidad;
    }

    public Boolean getActivo() {
        return activo;
    }

    public String getRol() {
        return rol;
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

    private static Boolean asBool(Object value) {
        if (value instanceof Boolean b) {
            return b;
        }
        return value == null ? null : Boolean.valueOf(value.toString());
    }

    private static String asString(Object value) {
        return value == null ? null : value.toString();
    }
}
