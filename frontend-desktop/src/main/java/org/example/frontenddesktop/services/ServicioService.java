package org.example.frontenddesktop.services;

import org.example.frontenddesktop.models.Servicio;
import org.example.frontenddesktop.utils.SessionManager;
import org.example.frontenddesktop.utils.SimpleJson;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Servicio HTTP para el recurso de servicios. Consume el endpoint autenticado
 * {@code GET /servicios/} de la API de FastAPI, adjuntando el JWT de la sesión
 * actual en la cabecera {@code Authorization: Bearer <token>}.
 */
public class ServicioService {

    private static final String BASE_URL = "http://127.0.0.1:8000";

    private final HttpClient client = HttpClient.newHttpClient();

    /**
     * Recupera todos los servicios del usuario autenticado.
     *
     * @return lista de servicios (posiblemente vacía)
     * @throws ServicioException si no hay sesión, falla la red o la API responde con error
     */
    public List<Servicio> listar() throws ServicioException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new ServicioException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/servicios/"))
                .header("Authorization", authorization)
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response;
        try {
            response = client.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new ServicioException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
        }

        int status = response.statusCode();
        if (status == 200) {
            return parseServicios(response.body());
        }

        if (status == 401 || status == 403) {
            throw new ServicioException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
        }

        throw new ServicioException("Error inesperado del servidor (código " + status + ").");
    }

    /**
     * Recupera TODOS los servicios recorriendo todas las páginas, para el
     * desplegable de selección de servicio al crear una cita. Como en los demás
     * desplegables, se pagina (skip/limit) para no omitir en silencio los
     * servicios a partir del número 100 (limit por defecto del backend).
     *
     * @return lista completa de servicios (posiblemente vacía)
     * @throws ServicioException si no hay sesión, falla la red o la API responde con error
     */
    public List<Servicio> listarTodos() throws ServicioException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new ServicioException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }

        List<Servicio> acumulado = new ArrayList<>();
        int skip = 0;
        final int limit = 100;
        while (true) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(BASE_URL + "/servicios/?skip=" + skip + "&limit=" + limit))
                    .header("Authorization", authorization)
                    .header("Accept", "application/json")
                    .GET()
                    .build();

            HttpResponse<String> response;
            try {
                response = client.send(request, HttpResponse.BodyHandlers.ofString());
            } catch (Exception e) {
                throw new ServicioException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
            }

            int status = response.statusCode();
            if (status == 401 || status == 403) {
                throw new ServicioException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
            }
            if (status != 200) {
                throw new ServicioException("Error inesperado del servidor (código " + status + ").");
            }

            List<Servicio> pagina = parseServicios(response.body());
            acumulado.addAll(pagina);
            if (pagina.size() < limit) {
                break;  // página incompleta -> última
            }
            skip += limit;
        }
        return acumulado;
    }

    /** Convierte el cuerpo JSON (array de objetos) en una lista de {@link Servicio}. */
    private List<Servicio> parseServicios(String body) throws ServicioException {
        Object root;
        try {
            root = SimpleJson.parse(body);
        } catch (RuntimeException e) {
            throw new ServicioException("La respuesta del servidor no es un JSON válido.", e);
        }

        if (!(root instanceof List<?> array)) {
            throw new ServicioException("La respuesta del servidor no contenía una lista de servicios.");
        }

        List<Servicio> servicios = new ArrayList<>();
        for (Object element : array) {
            if (element instanceof Map<?, ?> map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> json = (Map<String, Object>) map;
                servicios.add(Servicio.fromJson(json));
            }
        }
        return servicios;
    }

    /**
     * Excepción de dominio para transportar mensajes de error legibles hacia la interfaz.
     */
    public static class ServicioException extends Exception {
        public ServicioException(String message) {
            super(message);
        }

        public ServicioException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
