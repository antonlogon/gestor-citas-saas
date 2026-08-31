package org.example.frontenddesktop.services;

import org.example.frontenddesktop.models.Cliente;
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
 * Servicio HTTP para el recurso de pacientes (clientes). Consume el endpoint
 * autenticado {@code GET /clientes/} de la API de FastAPI, adjuntando el JWT de
 * la sesión actual en la cabecera {@code Authorization: Bearer <token>}.
 */
public class ClienteService {

    private static final String BASE_URL = "http://127.0.0.1:8000";

    private final HttpClient client = HttpClient.newHttpClient();

    /**
     * Recupera todos los pacientes del usuario autenticado.
     *
     * @return lista de clientes (posiblemente vacía)
     * @throws ClienteException si no hay sesión, falla la red o la API responde con error
     */
    public List<Cliente> listar() throws ClienteException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new ClienteException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/clientes/"))
                .header("Authorization", authorization)
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response;
        try {
            response = client.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new ClienteException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
        }

        int status = response.statusCode();
        if (status == 200) {
            return parseClientes(response.body());
        }

        if (status == 401 || status == 403) {
            throw new ClienteException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
        }

        throw new ClienteException("Error inesperado del servidor (código " + status + ").");
    }

    /**
     * Recupera TODOS los pacientes recorriendo todas las páginas, para el
     * desplegable de selección de paciente.
     *
     * <p>El backend aplica limit=100 por defecto; una sola petición omitiría en
     * silencio a los pacientes a partir del número 100. Se recorren todas las
     * páginas (skip/limit) en lugar de fijar un límite alto que volvería a
     * mentir por encima.
     *
     * @return lista completa de pacientes (posiblemente vacía)
     * @throws ClienteException si no hay sesión, falla la red o la API responde con error
     */
    public List<Cliente> listarTodos() throws ClienteException {
        String authorization = requireAuth();
        List<Cliente> acumulado = new ArrayList<>();
        int skip = 0;
        final int limit = 100;
        while (true) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(BASE_URL + "/clientes/?skip=" + skip + "&limit=" + limit))
                    .header("Authorization", authorization)
                    .header("Accept", "application/json")
                    .GET()
                    .build();

            HttpResponse<String> response = enviar(request);
            int status = response.statusCode();
            if (status == 401 || status == 403) {
                throw new ClienteException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
            }
            if (status != 200) {
                throw new ClienteException("Error inesperado del servidor (código " + status + ").");
            }

            List<Cliente> pagina = parseClientes(response.body());
            acumulado.addAll(pagina);
            if (pagina.size() < limit) {
                break;  // página incompleta -> última
            }
            skip += limit;
        }
        return acumulado;
    }

    /**
     * Da de alta un paciente. La contraseña la genera el cliente (no la teclea
     * el personal) y se muestra después una sola vez.
     *
     * @return el paciente creado (con su id asignado por la BD)
     * @throws ClienteException con el mensaje de la API (409 email duplicado,
     *         403 sin permiso, 422 datos inválidos…) o de red
     */
    public Cliente crear(String nombre, String email, String telefono, String password)
            throws ClienteException {
        String authorization = requireAuth();
        String body = SimpleJson.object()
                .put("nombre", nombre)
                .put("email", email)
                .put("telefono", telefono)
                .put("password", password)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/clientes/"))
                .header("Authorization", authorization)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = enviar(request);
        if (response.statusCode() == 201) {
            return unCliente(response.body());
        }
        throw errorDe(response);
    }

    /**
     * Edita nombre, email y teléfono de un paciente (lo único que admite
     * {@code ClienteUpdate}).
     *
     * @return el paciente actualizado
     * @throws ClienteException con el mensaje de la API o de red
     */
    public Cliente editar(int id, String nombre, String email, String telefono)
            throws ClienteException {
        String authorization = requireAuth();
        String body = SimpleJson.object()
                .put("nombre", nombre)
                .put("email", email)
                .put("telefono", telefono)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/clientes/" + id))
                .header("Authorization", authorization)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .PUT(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = enviar(request);
        if (response.statusCode() == 200) {
            return unCliente(response.body());
        }
        throw errorDe(response);
    }

    /**
     * Elimina un paciente. AVISO: el borrado es en cascada (arrastra sus citas);
     * la confirmación con esa advertencia se hace en la interfaz.
     *
     * @throws ClienteException con el mensaje de la API o de red
     */
    public void eliminar(int id) throws ClienteException {
        String authorization = requireAuth();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/clientes/" + id))
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

    /** Devuelve la cabecera de autorización o lanza si no hay sesión. */
    private String requireAuth() throws ClienteException {
        String authorization = SessionManager.getAuthorizationHeader();
        if (authorization == null) {
            throw new ClienteException("No hay una sesión activa. Vuelve a iniciar sesión.");
        }
        return authorization;
    }

    /** Envía la petición traduciendo los fallos de red a una excepción legible. */
    private HttpResponse<String> enviar(HttpRequest request) throws ClienteException {
        try {
            return client.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new ClienteException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
        }
    }

    /** Parsea un único objeto Cliente de la respuesta de POST/PUT. */
    private Cliente unCliente(String body) throws ClienteException {
        Object root;
        try {
            root = SimpleJson.parse(body);
        } catch (RuntimeException e) {
            throw new ClienteException("La respuesta del servidor no es un JSON válido.", e);
        }
        if (!(root instanceof Map<?, ?> map)) {
            throw new ClienteException("La respuesta del servidor no tenía el formato esperado.");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> json = (Map<String, Object>) map;
        return Cliente.fromJson(json);
    }

    /**
     * Construye la excepción de un error de escritura: para 401 pide reiniciar
     * sesión; para el resto (403/409/422/400…) muestra el {@code detail} exacto
     * que envía el backend, en vez de un genérico.
     */
    private ClienteException errorDe(HttpResponse<String> response) {
        int status = response.statusCode();
        if (status == 401) {
            return new ClienteException("Tu sesión ha caducado. Vuelve a iniciar sesión.");
        }
        String porDefecto = "Error inesperado del servidor (código " + status + ").";
        return new ClienteException(ApiError.detalle(response.body(), porDefecto));
    }

    /** Convierte el cuerpo JSON (array de objetos) en una lista de {@link Cliente}. */
    private List<Cliente> parseClientes(String body) throws ClienteException {
        Object root;
        try {
            root = SimpleJson.parse(body);
        } catch (RuntimeException e) {
            throw new ClienteException("La respuesta del servidor no es un JSON válido.", e);
        }

        if (!(root instanceof List<?> array)) {
            throw new ClienteException("La respuesta del servidor no contenía una lista de pacientes.");
        }

        List<Cliente> clientes = new ArrayList<>();
        for (Object element : array) {
            if (element instanceof Map<?, ?> map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> json = (Map<String, Object>) map;
                clientes.add(Cliente.fromJson(json));
            }
        }
        return clientes;
    }

    /**
     * Excepción de dominio para transportar mensajes de error legibles hacia la interfaz.
     */
    public static class ClienteException extends Exception {
        public ClienteException(String message) {
            super(message);
        }

        public ClienteException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
