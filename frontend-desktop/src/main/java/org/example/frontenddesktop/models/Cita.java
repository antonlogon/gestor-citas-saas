package org.example.frontenddesktop.models;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Map;

/**
 * Modelo de datos de una cita. Refleja el esquema de salida de la API de FastAPI
 * (Pydantic {@code schemas.Cita}) para el recurso {@code /citas/}. Es inmutable:
 * se construye a partir del JSON recibido mediante {@link #fromJson(Map)}.
 *
 * <p>Campos que devuelve la API: {@code id}, {@code empresa_id}, {@code cliente_id},
 * {@code empleado_id}, {@code servicio_id}, {@code fecha_hora}, {@code estado}
 * (PENDIENTE / CONFIRMADA / CANCELADA), {@code notas_ia} y los nombres "aplanados"
 * de las relaciones ({@code cliente_nombre}, {@code empleado_nombre},
 * {@code servicio_nombre}) que evitan tener que resolver los IDs en el cliente.
 */
public class Cita {

    // Locale español: hace que DateTimeFormatter genere los meses abreviados
    // en castellano ("ago", "sep"...) en lugar de en el idioma del sistema.
    private static final Locale LOCALE_ES = Locale.forLanguageTag("es-ES");

    // Formato legible para el usuario, p. ej. "20 ago 2026 · 12:10".
    private static final DateTimeFormatter FORMATO_LEGIBLE =
            DateTimeFormatter.ofPattern("d MMM yyyy · HH:mm", LOCALE_ES);

    private final Integer id;
    private final Integer empresaId;
    private final Integer clienteId;
    private final Integer empleadoId;
    private final Integer servicioId;
    private final String fechaHora;
    private final String estado;
    private final String notasIa;
    private final String clienteNombre;
    private final String empleadoNombre;
    private final String servicioNombre;

    public Cita(Integer id, Integer empresaId, Integer clienteId, Integer empleadoId,
                Integer servicioId, String fechaHora, String estado, String notasIa,
                String clienteNombre, String empleadoNombre, String servicioNombre) {
        this.id = id;
        this.empresaId = empresaId;
        this.clienteId = clienteId;
        this.empleadoId = empleadoId;
        this.servicioId = servicioId;
        this.fechaHora = fechaHora;
        this.estado = estado;
        this.notasIa = notasIa;
        this.clienteNombre = clienteNombre;
        this.empleadoNombre = empleadoNombre;
        this.servicioNombre = servicioNombre;
    }

    /**
     * Construye una {@link Cita} a partir de un objeto JSON ya parseado (mapa
     * clave/valor). Las claves coinciden exactamente con las que devuelve la API;
     * las ausentes u opcionales (como {@code notas_ia}) quedan como {@code null}.
     */
    public static Cita fromJson(Map<String, Object> json) {
        return new Cita(
                asInt(json.get("id")),
                asInt(json.get("empresa_id")),
                asInt(json.get("cliente_id")),
                asInt(json.get("empleado_id")),
                asInt(json.get("servicio_id")),
                asString(json.get("fecha_hora")),
                asString(json.get("estado")),
                asString(json.get("notas_ia")),
                asString(json.get("cliente_nombre")),
                asString(json.get("empleado_nombre")),
                asString(json.get("servicio_nombre"))
        );
    }

    public Integer getId() {
        return id;
    }

    public Integer getEmpresaId() {
        return empresaId;
    }

    public Integer getClienteId() {
        return clienteId;
    }

    public Integer getEmpleadoId() {
        return empleadoId;
    }

    public Integer getServicioId() {
        return servicioId;
    }

    public String getFechaHora() {
        return fechaHora;
    }

    /**
     * Fecha y hora formateadas en español para mostrar en la interfaz
     * (p. ej. "20 ago 2026 · 12:10"). Si la API devuelve una fecha ISO no
     * parseable o {@code null}, se devuelve el valor original tal cual para no
     * perder información.
     */
    public String getFechaHoraLegible() {
        if (fechaHora == null || fechaHora.isBlank()) {
            return "";
        }
        try {
            // La API entrega ISO-8601 (p. ej. "2026-08-20T12:10:34"); los
            // segundos son opcionales y LocalDateTime los admite.
            return LocalDateTime.parse(fechaHora).format(FORMATO_LEGIBLE);
        } catch (DateTimeParseException e) {
            return fechaHora;
        }
    }

    public String getEstado() {
        return estado;
    }

    public String getNotasIa() {
        return notasIa;
    }

    /** Nombre del paciente (relación aplanada por la API); {@code null} si no viene. */
    public String getClienteNombre() {
        return clienteNombre;
    }

    /** Nombre del empleado que atiende (relación aplanada por la API). */
    public String getEmpleadoNombre() {
        return empleadoNombre;
    }

    /** Nombre del servicio de la cita (relación aplanada por la API). */
    public String getServicioNombre() {
        return servicioNombre;
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
