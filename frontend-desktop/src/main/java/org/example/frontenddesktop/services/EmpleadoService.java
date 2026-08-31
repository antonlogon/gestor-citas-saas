package org.example.frontenddesktop.services;

import org.example.frontenddesktop.models.Empleado;
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
 * Servicio HTTP para el recurso de empleados. Se usa para poblar el desplegable
 * de profesionales al crear una cita. Sigue el patrón de {@link ClienteService}.
 */
public class EmpleadoService {

    private static final String BASE_URL = "http://127.0.0.1:8000";

    // Tamaño de página del backend (limit por defecto). Se pagina hasta agotar.
    private static final int TAMANO_PAGINA = 100;

    private final HttpClient client = HttpClient.newHttpClient();

    /**
     * Recupera TODOS los empleados ACTIVOS de la empresa, recorriendo todas las
     * páginas.
     *
     * <p>Dos decisiones deliberadas frente a un simple {@code GET /empleados/}:
     * <ul>
     *   <li>{@code solo_activos=true}: el parámetro vale false por defecto, así
     *       que sin él recepción podría asignar una cita a alguien dado de baja.</li>
     *   <li>Paginación completa (skip/limit en bucle): el backend aplica
     *       limit=100 por defecto; una sola petición omitiría en silencio a los
     *       profesionales a partir del número 100. Se recorren todas las páginas
     *       en vez de fijar un límite alto que volvería a mentir por encima.</li>
     * </ul>
     *
     * @return lista de empleados activos (posiblemente vacía)
     * @throws EmpleadoException si no hay sesión, falla la red o la API responde con error
     */
    public List<Empleado> listarActivos() throws EmpleadoException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new EmpleadoException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }

        List<Empleado> acumulado = new ArrayList<>();
        int skip = 0;
        while (true) {
            String url = BASE_URL + "/empleados/?solo_activos=true&skip=" + skip
                    + "&limit=" + TAMANO_PAGINA;
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Authorization", authorization)
                    .header("Accept", "application/json")
                    .GET()
                    .build();

            HttpResponse<String> response;
            try {
                response = client.send(request, HttpResponse.BodyHandlers.ofString());
            } catch (Exception e) {
                throw new EmpleadoException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
            }

            int status = response.statusCode();
            if (status == 401 || status == 403) {
                throw new EmpleadoException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
            }
            if (status != 200) {
                throw new EmpleadoException("Error inesperado del servidor (código " + status + ").");
            }

            List<Empleado> pagina = parseEmpleados(response.body());
            acumulado.addAll(pagina);
            // Página incompleta -> era la última.
            if (pagina.size() < TAMANO_PAGINA) {
                break;
            }
            skip += TAMANO_PAGINA;
        }
        return acumulado;
    }

    /** Convierte el cuerpo JSON (array de objetos) en una lista de {@link Empleado}. */
    private List<Empleado> parseEmpleados(String body) throws EmpleadoException {
        Object root;
        try {
            root = SimpleJson.parse(body);
        } catch (RuntimeException e) {
            throw new EmpleadoException("La respuesta del servidor no es un JSON válido.", e);
        }
        if (!(root instanceof List<?> array)) {
            throw new EmpleadoException("La respuesta del servidor no contenía una lista de empleados.");
        }
        List<Empleado> empleados = new ArrayList<>();
        for (Object element : array) {
            if (element instanceof Map<?, ?> map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> json = (Map<String, Object>) map;
                empleados.add(Empleado.fromJson(json));
            }
        }
        return empleados;
    }

    /**
     * Excepción de dominio para transportar mensajes de error legibles hacia la interfaz.
     */
    public static class EmpleadoException extends Exception {
        public EmpleadoException(String message) {
            super(message);
        }

        public EmpleadoException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
