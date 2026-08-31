package org.example.frontenddesktop.utils;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Parser JSON minimalista y sin dependencias externas, suficiente para
 * deserializar las respuestas de la API (objetos, arrays, cadenas, números,
 * booleanos y null). Se mantiene la filosofía del proyecto de no añadir
 * librerías de terceros.
 *
 * <p>Devuelve estructuras estándar: {@link Map} para objetos, {@link List}
 * para arrays, {@link String}, {@link Double}, {@link Boolean} o {@code null}.
 */
public final class SimpleJson {

    private final String src;
    private int pos;

    private SimpleJson(String src) {
        this.src = src;
    }

    /** Parsea un documento JSON completo y devuelve el valor raíz. */
    public static Object parse(String json) {
        SimpleJson parser = new SimpleJson(json);
        parser.skipWhitespace();
        Object value = parser.readValue();
        parser.skipWhitespace();
        if (parser.pos < parser.src.length()) {
            throw new IllegalArgumentException("Contenido JSON sobrante en la posición " + parser.pos);
        }
        return value;
    }

    private Object readValue() {
        char c = peek();
        switch (c) {
            case '{': return readObject();
            case '[': return readArray();
            case '"': return readString();
            case 't':
            case 'f': return readBoolean();
            case 'n': return readNull();
            default: return readNumber();
        }
    }

    private Map<String, Object> readObject() {
        Map<String, Object> map = new LinkedHashMap<>();
        expect('{');
        skipWhitespace();
        if (peek() == '}') {
            pos++;
            return map;
        }
        while (true) {
            skipWhitespace();
            String key = readString();
            skipWhitespace();
            expect(':');
            skipWhitespace();
            map.put(key, readValue());
            skipWhitespace();
            char c = next();
            if (c == '}') {
                break;
            }
            if (c != ',') {
                throw error("',' o '}'");
            }
        }
        return map;
    }

    private List<Object> readArray() {
        List<Object> list = new ArrayList<>();
        expect('[');
        skipWhitespace();
        if (peek() == ']') {
            pos++;
            return list;
        }
        while (true) {
            skipWhitespace();
            list.add(readValue());
            skipWhitespace();
            char c = next();
            if (c == ']') {
                break;
            }
            if (c != ',') {
                throw error("',' o ']'");
            }
        }
        return list;
    }

    private String readString() {
        expect('"');
        StringBuilder sb = new StringBuilder();
        while (true) {
            char c = next();
            if (c == '"') {
                break;
            }
            if (c == '\\') {
                char esc = next();
                switch (esc) {
                    case '"': sb.append('"'); break;
                    case '\\': sb.append('\\'); break;
                    case '/': sb.append('/'); break;
                    case 'b': sb.append('\b'); break;
                    case 'f': sb.append('\f'); break;
                    case 'n': sb.append('\n'); break;
                    case 'r': sb.append('\r'); break;
                    case 't': sb.append('\t'); break;
                    case 'u':
                        String hex = src.substring(pos, pos + 4);
                        sb.append((char) Integer.parseInt(hex, 16));
                        pos += 4;
                        break;
                    default: throw error("una secuencia de escape válida");
                }
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    private Double readNumber() {
        int start = pos;
        while (pos < src.length() && "+-0123456789.eE".indexOf(src.charAt(pos)) >= 0) {
            pos++;
        }
        String number = src.substring(start, pos);
        if (number.isEmpty()) {
            throw error("un número");
        }
        return Double.parseDouble(number);
    }

    private Boolean readBoolean() {
        if (src.startsWith("true", pos)) {
            pos += 4;
            return Boolean.TRUE;
        }
        if (src.startsWith("false", pos)) {
            pos += 5;
            return Boolean.FALSE;
        }
        throw error("'true' o 'false'");
    }

    private Object readNull() {
        if (src.startsWith("null", pos)) {
            pos += 4;
            return null;
        }
        throw error("'null'");
    }

    private char peek() {
        if (pos >= src.length()) {
            throw error("más contenido");
        }
        return src.charAt(pos);
    }

    private char next() {
        if (pos >= src.length()) {
            throw error("más contenido");
        }
        return src.charAt(pos++);
    }

    private void expect(char c) {
        char actual = next();
        if (actual != c) {
            throw error("'" + c + "'");
        }
    }

    private void skipWhitespace() {
        while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) {
            pos++;
        }
    }

    private IllegalArgumentException error(String expected) {
        return new IllegalArgumentException(
                "JSON inválido: se esperaba " + expected + " en la posición " + pos);
    }

    // ======================================================================
    // CONSTRUCCIÓN DE JSON (serialización)
    // El parser de arriba solo LEE; para los cuerpos de POST/PUT necesitamos
    // ESCRIBIR JSON. Se mantiene la filosofía de no añadir dependencias.
    // ======================================================================

    /**
     * Serializa un valor Java a su representación JSON. Admite {@link Map}
     * (objeto), {@link List} (array), {@link String}, {@link Number},
     * {@link Boolean} y {@code null}; cualquier otro tipo se serializa como su
     * {@code toString()} entre comillas. Las cadenas se escapan correctamente
     * (comillas, barra invertida y caracteres de control).
     *
     * @param value valor a serializar
     * @return el documento JSON como cadena
     */
    public static String write(Object value) {
        StringBuilder sb = new StringBuilder();
        writeValue(sb, value);
        return sb.toString();
    }

    /** Crea un constructor fluido de objetos JSON (respeta el orden de inserción). */
    public static ObjectBuilder object() {
        return new ObjectBuilder();
    }

    /**
     * Constructor fluido de objetos JSON, para armar cuerpos de petición sin
     * mapas verbosos: {@code SimpleJson.object().put("nombre", n).build()}.
     */
    public static final class ObjectBuilder {
        private final Map<String, Object> campos = new LinkedHashMap<>();

        /** Añade un par clave/valor (el valor se serializa según su tipo). */
        public ObjectBuilder put(String clave, Object valor) {
            campos.put(clave, valor);
            return this;
        }

        /** Serializa el objeto acumulado a JSON. */
        public String build() {
            return write(campos);
        }
    }

    private static void writeValue(StringBuilder sb, Object value) {
        if (value == null) {
            sb.append("null");
        } else if (value instanceof String s) {
            writeString(sb, s);
        } else if (value instanceof Boolean b) {
            sb.append(b ? "true" : "false");
        } else if (value instanceof Number n) {
            sb.append(n.toString());
        } else if (value instanceof Map<?, ?> map) {
            writeObject(sb, map);
        } else if (value instanceof List<?> list) {
            writeArray(sb, list);
        } else {
            // Tipo no previsto: lo tratamos como cadena para no romper el JSON.
            writeString(sb, value.toString());
        }
    }

    private static void writeObject(StringBuilder sb, Map<?, ?> map) {
        sb.append('{');
        boolean primero = true;
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (!primero) {
                sb.append(',');
            }
            primero = false;
            writeString(sb, String.valueOf(entry.getKey()));
            sb.append(':');
            writeValue(sb, entry.getValue());
        }
        sb.append('}');
    }

    private static void writeArray(StringBuilder sb, List<?> list) {
        sb.append('[');
        boolean primero = true;
        for (Object elemento : list) {
            if (!primero) {
                sb.append(',');
            }
            primero = false;
            writeValue(sb, elemento);
        }
        sb.append(']');
    }

    /** Escribe una cadena JSON entre comillas, escapando lo que exige el estándar. */
    private static void writeString(StringBuilder sb, String s) {
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\b': sb.append("\\b"); break;
                case '\f': sb.append("\\f"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    // Caracteres de control (< 0x20) -> escape unicode.
                    // OJO: se escribe el prefijo con chars separados ('\\' y 'u')
                    // porque la secuencia literal barra-u la interpretaría el
                    // traductor unicode del compilador ("illegal unicode escape").
                    if (c < 0x20) {
                        sb.append('\\').append('u').append(String.format("%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        sb.append('"');
    }
}
