package org.example.frontenddesktop.utils;

import org.example.frontenddesktop.models.HorarioApertura;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Sesión de usuario a nivel de aplicación. Almacena de forma estática el JWT
 * y los datos del usuario autenticado para que estén disponibles en cualquier
 * punto de la aplicación de escritorio.
 *
 * <p>Los datos se extraen de los claims que emite el backend (FastAPI,
 * {@code schemas.TokenData}): {@code sub} (email del usuario), {@code tipo}
 * ("cliente" o "empleado") e {@code id} (identificador del usuario en su tabla).
 *
 * <p>No es instanciable: se usa a través de sus métodos estáticos.
 */
public final class SessionManager {

    // Extraen los claims del payload del JWT (JSON plano).
    // "sub" y "tipo" son cadenas; "id" es numérico (sin comillas).
    private static final Pattern SUB_PATTERN =
            Pattern.compile("\"sub\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern TIPO_PATTERN =
            Pattern.compile("\"tipo\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern ID_PATTERN =
            Pattern.compile("\"id\"\\s*:\\s*(\\d+)");

    private static String accessToken;
    private static String email;
    private static String tipo;
    private static Integer userId;

    // Horario de apertura del tenant. Se cachea a nivel de sesión porque no cambia
    // mientras dure: se carga UNA vez (la primera que la vista de Citas lo
    // necesita) y lo reutilizan todas las aperturas del formulario, en lugar de
    // pedirlo a la API cada vez. Puede ser null si aún no se ha cargado o si no se
    // pudo obtener (el formulario degrada a "sin restricción").
    private static HorarioApertura horario;

    private SessionManager() {
        // Clase de utilidad estática.
    }

    /**
     * Inicia la sesión con el token recibido de la API. Enriquece los datos del
     * usuario (email, tipo e id) decodificando el payload del JWT; si el email no
     * está presente, usa el usuario introducido en el login como valor por defecto.
     *
     * @param token         JWT (access_token) devuelto por la API
     * @param fallbackEmail usuario introducido en el login, usado si el JWT no trae email
     */
    public static void start(String token, String fallbackEmail) {
        accessToken = token;

        String jwtSub = null;
        String jwtTipo = null;
        Integer jwtId = null;

        String payload = decodePayload(token);
        if (payload != null) {
            jwtSub = firstMatch(SUB_PATTERN, payload);
            jwtTipo = firstMatch(TIPO_PATTERN, payload);
            String rawId = firstMatch(ID_PATTERN, payload);
            if (rawId != null) {
                try {
                    jwtId = Integer.valueOf(rawId);
                } catch (NumberFormatException ignored) {
                    // Dejamos el id como null si no es parseable.
                }
            }
        }

        // El email viaja en "sub"; si no, usamos el usuario tecleado en el login.
        email = jwtSub != null ? jwtSub : fallbackEmail;
        tipo = jwtTipo;
        userId = jwtId;
    }

    /** Elimina todos los datos de la sesión actual (logout). */
    public static void clear() {
        accessToken = null;
        email = null;
        tipo = null;
        userId = null;
        horario = null;
    }

    /** Horario de apertura cacheado del tenant, o {@code null} si no se ha cargado. */
    public static HorarioApertura getHorario() {
        return horario;
    }

    /** Guarda el horario de apertura del tenant para reutilizarlo en la sesión. */
    public static void setHorario(HorarioApertura nuevo) {
        horario = nuevo;
    }

    public static boolean isActive() {
        return accessToken != null;
    }

    public static String getAccessToken() {
        return accessToken;
    }

    public static String getEmail() {
        return email;
    }

    /** Tipo de usuario autenticado: "cliente" o "empleado" (claim {@code tipo}). */
    public static String getTipo() {
        return tipo;
    }

    /** Identificador del usuario en su tabla (claim {@code id}). */
    public static Integer getUserId() {
        return userId;
    }

    /**
     * Cabecera Authorization lista para adjuntar a peticiones autenticadas.
     *
     * @return "Bearer &lt;token&gt;" o {@code null} si no hay sesión activa
     */
    public static String getAuthorizationHeader() {
        return accessToken == null ? null : "Bearer " + accessToken;
    }

    /** Decodifica el payload (segunda parte) de un JWT a JSON. Devuelve null si falla. */
    private static String decodePayload(String token) {
        if (token == null) {
            return null;
        }
        String[] parts = token.split("\\.");
        if (parts.length < 2) {
            return null;
        }
        try {
            byte[] decoded = Base64.getUrlDecoder().decode(parts[1]);
            return new String(decoded, StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            // Payload no válido en Base64Url: seguimos con los datos del login.
            return null;
        }
    }

    private static String firstMatch(Pattern pattern, String text) {
        Matcher matcher = pattern.matcher(text);
        return matcher.find() ? matcher.group(1) : null;
    }
}
