package org.example.frontenddesktop.services;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Servicio que encapsula la comunicación con la API de FastAPI para la autenticación.
 * Realiza el login OAuth2 (x-www-form-urlencoded) y extrae el JWT de la respuesta.
 */
public class AuthService {

    private static final String BASE_URL = "http://127.0.0.1:8000";

    // Extrae el valor de "access_token" tolerando espacios: {"access_token": "..."}
    private static final Pattern TOKEN_PATTERN =
            Pattern.compile("\"access_token\"\\s*:\\s*\"([^\"]+)\"");

    private final HttpClient client = HttpClient.newHttpClient();

    /**
     * Realiza el login contra la API.
     *
     * @param username usuario introducido en la pantalla de login
     * @param password contraseña introducida en la pantalla de login
     * @return el JWT (access_token) en caso de éxito
     * @throws AuthException si las credenciales son inválidas o la API responde con error
     */
    public String login(String username, String password) throws AuthException {
        // FastAPI OAuth2 exige application/x-www-form-urlencoded con los datos codificados.
        String formData = "username=" + encode(username) + "&password=" + encode(password);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/login"))
                .header("Content-Type", "application/x-www-form-urlencoded")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(formData))
                .build();

        HttpResponse<String> response;
        try {
            response = client.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            // Fallo de red / servidor no disponible.
            throw new AuthException("No se pudo conectar con el servidor. ¿Está la API en marcha?", e);
        }

        int status = response.statusCode();
        if (status == 200) {
            String token = extractToken(response.body());
            if (token == null) {
                throw new AuthException("La respuesta del servidor no contenía un token válido.");
            }
            return token;
        }

        if (status == 401 || status == 400) {
            throw new AuthException("Usuario o contraseña incorrectos.");
        }

        throw new AuthException("Error inesperado del servidor (código " + status + ").");
    }

    private String extractToken(String body) {
        if (body == null) {
            return null;
        }
        Matcher matcher = TOKEN_PATTERN.matcher(body);
        return matcher.find() ? matcher.group(1) : null;
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    /**
     * Excepción de dominio para transportar mensajes de error legibles hacia la interfaz.
     */
    public static class AuthException extends Exception {
        public AuthException(String message) {
            super(message);
        }

        public AuthException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
