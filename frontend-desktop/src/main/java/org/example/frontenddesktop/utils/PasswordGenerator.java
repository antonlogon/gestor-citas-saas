package org.example.frontenddesktop.utils;

import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Genera contraseñas provisionales robustas para los pacientes recién dados de
 * alta. El personal NO teclea la contraseña: se genera aquí, se muestra una
 * sola vez y se entrega al paciente (ver {@code Dialogs.credencialesGeneradas}).
 *
 * <p>Se usa {@link SecureRandom} (no {@code Random}) por tratarse de una
 * credencial. Se excluyen caracteres ambiguos (O/0, I/l/1) para que sea fácil
 * de dictar o teclear, y se garantiza al menos un carácter de cada clase.
 */
public final class PasswordGenerator {

    private static final String MAYUSCULAS = "ABCDEFGHJKLMNPQRSTUVWXYZ";  // sin I, O
    private static final String MINUSCULAS = "abcdefghijkmnpqrstuvwxyz";  // sin l, o
    private static final String DIGITOS = "23456789";                     // sin 0, 1
    private static final String SIMBOLOS = "!@#$%*?-_";

    private static final SecureRandom RANDOM = new SecureRandom();

    private static final int LONGITUD_POR_DEFECTO = 16;

    private PasswordGenerator() {
        // Clase de utilidad estática.
    }

    /** Genera una contraseña con la longitud por defecto (16 caracteres). */
    public static String generar() {
        return generar(LONGITUD_POR_DEFECTO);
    }

    /**
     * Genera una contraseña aleatoria de la longitud indicada, con al menos un
     * carácter de cada clase (mayúscula, minúscula, dígito y símbolo).
     *
     * @param longitud número de caracteres (mínimo 8; el backend exige 8)
     * @return la contraseña generada
     */
    public static String generar(int longitud) {
        int total = Math.max(8, longitud);

        // Garantizamos un carácter de cada clase y rellenamos el resto con el
        // alfabeto completo; luego barajamos para que las posiciones fijas no
        // queden siempre al principio.
        List<Character> caracteres = new ArrayList<>(total);
        caracteres.add(aleatorio(MAYUSCULAS));
        caracteres.add(aleatorio(MINUSCULAS));
        caracteres.add(aleatorio(DIGITOS));
        caracteres.add(aleatorio(SIMBOLOS));

        String alfabeto = MAYUSCULAS + MINUSCULAS + DIGITOS + SIMBOLOS;
        while (caracteres.size() < total) {
            caracteres.add(aleatorio(alfabeto));
        }

        Collections.shuffle(caracteres, RANDOM);

        StringBuilder sb = new StringBuilder(total);
        for (char c : caracteres) {
            sb.append(c);
        }
        return sb.toString();
    }

    /** Devuelve un carácter aleatorio del conjunto dado usando SecureRandom. */
    private static char aleatorio(String conjunto) {
        return conjunto.charAt(RANDOM.nextInt(conjunto.length()));
    }
}
