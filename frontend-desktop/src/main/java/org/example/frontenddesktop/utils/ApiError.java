package org.example.frontenddesktop.utils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Extrae de una respuesta de error de la API (FastAPI) un mensaje legible para
 * el usuario a partir del campo {@code detail}, que NO siempre tiene la misma
 * forma:
 *
 * <ul>
 *   <li><b>Errores de negocio</b> (400 / 403 / 409): {@code detail} es una
 *       CADENA ya redactada, p. ej. «El email 'x' ya está registrado…».</li>
 *   <li><b>Validación</b> (422): {@code detail} es una LISTA de objetos
 *       {@code {"loc": ["body","email"], "msg": "Field required", ...}}. Se
 *       compone un mensaje por campo del tipo «email: Field required» en lugar
 *       de volcar el JSON en crudo.</li>
 * </ul>
 *
 * Si no se puede extraer nada, se devuelve el mensaje por defecto que pase el
 * llamante (para no dejar nunca al usuario sin explicación).
 */
public final class ApiError {

    private ApiError() {
        // Clase de utilidad estática.
    }

    /**
     * Devuelve el mensaje de error legible contenido en el cuerpo, o
     * {@code porDefecto} si el cuerpo no es un error interpretable.
     *
     * @param body       cuerpo de la respuesta (JSON) tal cual lo devuelve la API
     * @param porDefecto mensaje a usar si no hay un {@code detail} aprovechable
     * @return un mensaje listo para mostrar al usuario
     */
    public static String detalle(String body, String porDefecto) {
        if (body == null || body.isBlank()) {
            return porDefecto;
        }
        Object root;
        try {
            root = SimpleJson.parse(body);
        } catch (RuntimeException e) {
            return porDefecto;
        }
        if (!(root instanceof Map<?, ?> map)) {
            return porDefecto;
        }

        Object detail = map.get("detail");
        // Caso cadena: 400 / 403 / 409 -> mensaje ya redactado por el backend.
        if (detail instanceof String texto && !texto.isBlank()) {
            return texto;
        }
        // Caso lista: 422 -> errores de validación campo a campo.
        if (detail instanceof List<?> lista) {
            String mensaje = componerValidacion(lista);
            if (!mensaje.isBlank()) {
                return mensaje;
            }
        }
        return porDefecto;
    }

    /** Compone «campo: mensaje» (uno por línea) a partir de la lista de errores 422. */
    private static String componerValidacion(List<?> lista) {
        List<String> lineas = new ArrayList<>();
        for (Object elemento : lista) {
            if (!(elemento instanceof Map<?, ?> error)) {
                continue;
            }
            String campo = nombreCampo(error.get("loc"));
            Object msg = error.get("msg");
            String texto = (msg == null) ? "dato inválido" : msg.toString();
            lineas.add(campo.isEmpty() ? texto : campo + ": " + texto);
        }
        return String.join("\n", lineas);
    }

    /**
     * Deriva el nombre del campo del array {@code loc}. FastAPI lo entrega como
     * {@code ["body", "email"]}; nos quedamos con el último segmento ("email"),
     * que es el nombre del campo con el que el usuario se relaciona.
     */
    private static String nombreCampo(Object loc) {
        if (loc instanceof List<?> segmentos && !segmentos.isEmpty()) {
            Object ultimo = segmentos.get(segmentos.size() - 1);
            return ultimo == null ? "" : ultimo.toString();
        }
        return "";
    }
}
