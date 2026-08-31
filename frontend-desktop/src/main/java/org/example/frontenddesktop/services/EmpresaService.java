package org.example.frontenddesktop.services;

import org.example.frontenddesktop.models.HorarioApertura;
import org.example.frontenddesktop.utils.SessionManager;
import org.example.frontenddesktop.utils.SimpleJson;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;

/**
 * Servicio HTTP para el recurso de empresas. Consume {@code GET /empresas/} (que
 * devuelve únicamente la empresa del usuario autenticado) para leer el HORARIO DE
 * APERTURA del tenant, con el que el formulario de citas evita ofrecer huecos
 * fuera de horario.
 *
 * <p>El horario no cambia durante la sesión, así que quien lo consuma debe
 * cachearlo (ver {@link SessionManager}) en lugar de pedirlo en cada apertura del
 * diálogo.
 */
public class EmpresaService {

    private static final String BASE_URL = "http://127.0.0.1:8000";

    private final HttpClient client = HttpClient.newHttpClient();

    /**
     * Recupera el horario de apertura de la empresa del usuario autenticado.
     *
     * @return el horario parseado, o {@code null} si no se puede obtener o
     *         interpretar (el formulario degrada a "sin restricción"; el backend
     *         valida igualmente)
     * @throws EmpresaException si no hay sesión, falla la red o la API responde
     *                          con error
     */
    public HorarioApertura obtenerHorario() throws EmpresaException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new EmpresaException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/empresas/"))
                .header("Authorization", authorization)
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response;
        try {
            response = client.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new EmpresaException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
        }

        int status = response.statusCode();
        if (status == 401 || status == 403) {
            throw new EmpresaException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
        }
        if (status != 200) {
            throw new EmpresaException("Error inesperado del servidor (código " + status + ").");
        }
        return parseHorario(response.body());
    }

    /**
     * Extrae {@code horario_apertura} de la primera (y única) empresa del cuerpo.
     * Devuelve {@code null} si el cuerpo no es la lista esperada o el horario no es
     * interpretable: es un dato "de ayuda" para la UI, no un error que deba
     * interrumpir el flujo.
     */
    private HorarioApertura parseHorario(String body) throws EmpresaException {
        Object root;
        try {
            root = SimpleJson.parse(body);
        } catch (RuntimeException e) {
            throw new EmpresaException("La respuesta del servidor no es un JSON válido.", e);
        }
        if (!(root instanceof List<?> array) || array.isEmpty()) {
            return null;
        }
        if (!(array.get(0) instanceof Map<?, ?> empresa)) {
            return null;
        }
        return HorarioApertura.fromJson(empresa.get("horario_apertura"));
    }

    /**
     * Excepción de dominio para transportar mensajes de error legibles hacia la interfaz.
     */
    public static class EmpresaException extends Exception {
        public EmpresaException(String message) {
            super(message);
        }

        public EmpresaException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
