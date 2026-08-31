package org.example.frontenddesktop.models;

import java.util.Map;

/**
 * Modelo de datos de un servicio. Refleja el esquema de salida de la API de
 * FastAPI ({@code schemas.Servicio}) para el recurso {@code /servicios/}. Es
 * inmutable: se construye a partir del JSON recibido mediante {@link #fromJson(Map)}.
 *
 * <p>Campos que devuelve la API: {@code id}, {@code empresa_id}, {@code nombre},
 * {@code duracion_minutos} y {@code precio}. El precio se conserva como cadena
 * para no perder precisión (es un {@code Decimal} en el backend).
 */
public class Servicio {

    private final Integer id;
    private final Integer empresaId;
    private final String nombre;
    private final Integer duracionMinutos;
    private final String precio;

    public Servicio(Integer id, Integer empresaId, String nombre,
                    Integer duracionMinutos, String precio) {
        this.id = id;
        this.empresaId = empresaId;
        this.nombre = nombre;
        this.duracionMinutos = duracionMinutos;
        this.precio = precio;
    }

    /**
     * Construye un {@link Servicio} a partir de un objeto JSON ya parseado (mapa
     * clave/valor). Las claves coinciden con las que devuelve la API; las
     * ausentes quedan como {@code null}.
     */
    public static Servicio fromJson(Map<String, Object> json) {
        return new Servicio(
                asInt(json.get("id")),
                asInt(json.get("empresa_id")),
                asString(json.get("nombre")),
                asInt(json.get("duracion_minutos")),
                asString(json.get("precio"))
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

    public Integer getDuracionMinutos() {
        return duracionMinutos;
    }

    public String getPrecio() {
        return precio;
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
