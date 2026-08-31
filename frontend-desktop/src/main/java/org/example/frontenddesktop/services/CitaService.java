package org.example.frontenddesktop.services;

import org.example.frontenddesktop.models.Cita;
import org.example.frontenddesktop.utils.ApiError;
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
 * Servicio HTTP para el recurso de citas. Consume el endpoint autenticado
 * {@code GET /citas/} de la API de FastAPI, adjuntando el JWT de la sesión
 * actual en la cabecera {@code Authorization: Bearer <token>}.
 */
public class CitaService {

    private static final String BASE_URL = "http://127.0.0.1:8000";

    // Tamaño de página al recorrer el listado. Debe ser <= al límite máximo que
    // acepte el backend; con 100 coincide con su valor por defecto.
    private static final int TAMANO_PAGINA = 100;

    private final HttpClient client = HttpClient.newHttpClient();

    /**
     * Recupera todas las citas del usuario autenticado.
     *
     * @return lista de citas (posiblemente vacía)
     * @throws CitaException si no hay sesión, falla la red o la API responde con error
     */
    public List<Cita> listar() throws CitaException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new CitaException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }

        List<Cita> acumulado = new ArrayList<>();
        int skip = 0;
        while (true) {
            String url = BASE_URL + "/citas/?skip=" + skip + "&limit=" + TAMANO_PAGINA;
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
                throw new CitaException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
            }

            int status = response.statusCode();
            if (status == 401 || status == 403) {
                throw new CitaException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
            }
            if (status != 200) {
                throw new CitaException("Error inesperado del servidor (código " + status + ").");
            }

            List<Cita> pagina = parseCitas(response.body());
            acumulado.addAll(pagina);
            // Página incompleta -> era la última. El backend respeta el offset,
            // así que en cuanto se agotan las filas devuelve menos de las pedidas.
            if (pagina.size() < TAMANO_PAGINA) {
                break;
            }
            skip += TAMANO_PAGINA;
        }
        return acumulado;
    }

    /**
     * Recupera los recuentos agregados de citas (KPIs) desde
     * {@code GET /citas/resumen}. Se calculan en SQL sobre todo el tenant, por lo
     * que NO dependen de la paginación del listado.
     *
     * @return recuentos agregados
     * @throws CitaException si no hay sesión, falla la red o la API responde con error
     */
    public Resumen resumen() throws CitaException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new CitaException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/citas/resumen"))
                .header("Authorization", authorization)
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response;
        try {
            response = client.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new CitaException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
        }

        int status = response.statusCode();
        if (status == 401 || status == 403) {
            throw new CitaException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
        }
        if (status != 200) {
            throw new CitaException("Error inesperado del servidor (código " + status + ").");
        }

        Object root;
        try {
            root = SimpleJson.parse(response.body());
        } catch (RuntimeException e) {
            throw new CitaException("La respuesta del servidor no es un JSON válido.", e);
        }
        if (!(root instanceof Map<?, ?> map)) {
            throw new CitaException("La respuesta de resumen no tenía el formato esperado.");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> json = (Map<String, Object>) map;
        return new Resumen(
                asInt(json.get("total")),
                asInt(json.get("hoy")),
                asInt(json.get("pendientes")),
                asInt(json.get("confirmadas")),
                asInt(json.get("canceladas"))
        );
    }

    /**
     * Crea una cita. Si la franja se solapa con otra del profesional, el backend
     * responde 409 con un {@code detail} que incluye el profesional y la hora en
     * conflicto: se propaga tal cual para mostrarlo al usuario.
     *
     * @param fechaHoraIso fecha y hora en ISO-8601 (p. ej. "2026-08-20T12:10:00")
     * @return la cita creada
     * @throws CitaException con el mensaje de la API (409 solape, 422 datos…) o de red
     */
    public Cita crear(int clienteId, int empleadoId, int servicioId, String fechaHoraIso)
            throws CitaException {
        String authorization = requireAuth();
        String body = SimpleJson.object()
                .put("cliente_id", clienteId)
                .put("empleado_id", empleadoId)
                .put("servicio_id", servicioId)
                .put("fecha_hora", fechaHoraIso)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/citas/"))
                .header("Authorization", authorization)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = enviar(request);
        if (response.statusCode() == 201) {
            return unaCita(response.body());
        }
        throw errorDe(response);
    }

    /**
     * Edita una cita: solo fecha/hora, estado y notas (lo único que admite
     * {@code CitaUpdate}; el paciente, el profesional y el servicio no se pueden
     * cambiar).
     *
     * @return la cita actualizada
     * @throws CitaException con el mensaje de la API (409 solape al reprogramar…) o de red
     */
    public Cita editar(int id, String fechaHoraIso, String estado, String notas)
            throws CitaException {
        String authorization = requireAuth();
        String body = SimpleJson.object()
                .put("fecha_hora", fechaHoraIso)
                .put("estado", estado)
                .put("notas_ia", notas)
                .build();
        return enviarPut(id, body, authorization);
    }

    /**
     * Cambio rápido de estado (CONFIRMADA / CANCELADA) sin abrir el formulario
     * completo. Reactivar una cita cancelada sobre una franja ya ocupada
     * devuelve 409 con su {@code detail}.
     *
     * @return la cita actualizada
     * @throws CitaException con el mensaje de la API o de red
     */
    public Cita cambiarEstado(int id, String estado) throws CitaException {
        String authorization = requireAuth();
        String body = SimpleJson.object().put("estado", estado).build();
        return enviarPut(id, body, authorization);
    }

    /**
     * Elimina una cita.
     *
     * @throws CitaException con el mensaje de la API o de red
     */
    public void eliminar(int id) throws CitaException {
        String authorization = requireAuth();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/citas/" + id))
                .header("Authorization", authorization)
                .header("Accept", "application/json")
                .DELETE()
                .build();

        HttpResponse<String> response = enviar(request);
        if (response.statusCode() != 204) {
            throw errorDe(response);
        }
    }

    // ------------------ Utilidades compartidas de escritura ------------------

    /** Envía un PUT /citas/{id} y devuelve la cita actualizada, o traduce el error. */
    private Cita enviarPut(int id, String body, String authorization) throws CitaException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/citas/" + id))
                .header("Authorization", authorization)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .PUT(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = enviar(request);
        if (response.statusCode() == 200) {
            return unaCita(response.body());
        }
        throw errorDe(response);
    }

    /** Devuelve la cabecera de autorización o lanza si no hay sesión. */
    private String requireAuth() throws CitaException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new CitaException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }
        return authorization;
    }

    /** Envía la petición traduciendo los fallos de red a una excepción legible. */
    private HttpResponse<String> enviar(HttpRequest request) throws CitaException {
        try {
            return client.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new CitaException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
        }
    }

    /** Parsea un único objeto Cita de la respuesta de POST/PUT. */
    private Cita unaCita(String body) throws CitaException {
        Object root;
        try {
            root = SimpleJson.parse(body);
        } catch (RuntimeException e) {
            throw new CitaException("La respuesta del servidor no es un JSON válido.", e);
        }
        if (!(root instanceof Map<?, ?> map)) {
            throw new CitaException("La respuesta del servidor no tenía el formato esperado.");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> json = (Map<String, Object>) map;
        return Cita.fromJson(json);
    }

    /**
     * Construye la excepción de un error de escritura: 401 pide reiniciar
     * sesión; el resto (409 solape, 403 sin permiso, 422 datos…) muestra el
     * {@code detail} exacto del backend (incluye profesional y hora en el solape).
     */
    private CitaException errorDe(HttpResponse<String> response) {
        int status = response.statusCode();
        if (status == 401) {
            return new CitaException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
        }
        String porDefecto = "Error inesperado del servidor (código " + status + ").";
        return new CitaException(ApiError.detalle(response.body(), porDefecto));
    }

    /** Convierte el cuerpo JSON (array de objetos) en una lista de {@link Cita}. */
    private List<Cita> parseCitas(String body) throws CitaException {
        Object root;
        try {
            root = SimpleJson.parse(body);
        } catch (RuntimeException e) {
            throw new CitaException("La respuesta del servidor no es un JSON válido.", e);
        }

        if (!(root instanceof List<?> array)) {
            throw new CitaException("La respuesta del servidor no contenía una lista de citas.");
        }

        List<Cita> citas = new ArrayList<>();
        for (Object element : array) {
            if (element instanceof Map<?, ?> map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> json = (Map<String, Object>) map;
                citas.add(Cita.fromJson(json));
            }
        }
        return citas;
    }

    /** Interpreta un valor JSON numérico como int (0 si es nulo o no numérico). */
    private static int asInt(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value == null) {
            return 0;
        }
        try {
            return Integer.parseInt(value.toString().trim());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    /**
     * Recuentos agregados de citas para los KPIs, tal y como los calcula el
     * backend en SQL sobre todo el tenant. {@code hoy} excluye las canceladas.
     */
    public record Resumen(int total, int hoy, int pendientes, int confirmadas, int canceladas) {
    }

    /**
     * Excepción de dominio para transportar mensajes de error legibles hacia la interfaz.
     */
    public static class CitaException extends Exception {
        public CitaException(String message) {
            super(message);
        }

        public CitaException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
