package org.example.frontenddesktop.models;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Horario de apertura semanal de la clínica (por tenant). Refleja el campo
 * {@code horario_apertura} del esquema de salida de la API ({@code schemas.Empresa}):
 * una lista de 7 posiciones indexadas como {@code datetime.weekday()} del backend
 * (0=lunes ... 6=domingo); cada una es la lista de TRAMOS de ese día y una lista
 * vacía significa CERRADO.
 *
 * <p>Sirve al formulario de citas para no ofrecer huecos imposibles: deshabilitar
 * los días cerrados y ofrecer solo las horas de inicio que caben, según la
 * duración del servicio, dentro de un mismo tramo de apertura. Es la misma regla
 * que valida el backend; aquí solo evita proponerlos (el backend sigue mandando).
 */
public final class HorarioApertura {

    /** Un tramo de apertura dentro de un día: [inicio, fin]. */
    public record Tramo(LocalTime inicio, LocalTime fin) {
    }

    // 7 listas de tramos, índice 0=lunes ... 6=domingo (como el backend).
    private final List<List<Tramo>> semana;

    private HorarioApertura(List<List<Tramo>> semana) {
        this.semana = semana;
    }

    /**
     * Construye el horario a partir del valor JSON ya parseado (la lista que
     * viene en {@code horario_apertura}). Devuelve {@code null} si el dato falta o
     * está mal formado: el formulario lo interpreta como "sin restricción" y
     * degrada al comportamiento anterior (el backend sigue validando igualmente),
     * en lugar de bloquear al usuario por un horario corrupto.
     *
     * @param horarioJson valor de {@code horario_apertura} (se espera una lista de
     *                    7 listas de objetos {@code {"inicio","fin"}})
     * @return el horario parseado, o {@code null} si no es interpretable
     */
    public static HorarioApertura fromJson(Object horarioJson) {
        if (!(horarioJson instanceof List<?> dias) || dias.size() != 7) {
            return null;
        }
        List<List<Tramo>> semana = new ArrayList<>(7);
        for (Object diaObj : dias) {
            if (!(diaObj instanceof List<?> tramos)) {
                return null;
            }
            List<Tramo> delDia = new ArrayList<>();
            for (Object tramoObj : tramos) {
                if (!(tramoObj instanceof Map<?, ?> tramo)) {
                    return null;
                }
                LocalTime inicio = parseHora(tramo.get("inicio"));
                LocalTime fin = parseHora(tramo.get("fin"));
                if (inicio == null || fin == null || !inicio.isBefore(fin)) {
                    return null;
                }
                delDia.add(new Tramo(inicio, fin));
            }
            semana.add(delDia);
        }
        return new HorarioApertura(semana);
    }

    /** Tramos de apertura de ese día (lista vacía si está cerrado). */
    public List<Tramo> tramosDe(LocalDate dia) {
        // DayOfWeek.getValue(): 1=lunes ... 7=domingo -> índice 0..6.
        return semana.get(dia.getDayOfWeek().getValue() - 1);
    }

    /** {@code true} si la clínica no abre ese día (ningún tramo). */
    public boolean estaCerrado(LocalDate dia) {
        return tramosDe(dia).isEmpty();
    }

    /**
     * Horas de inicio (en pasos de {@code pasoMinutos}) para las que una cita de
     * {@code duracionMinutos} cabe ENTERA dentro de algún tramo de ese día.
     *
     * <p>El cierre es inclusivo, como en el backend: una cita de 30 min a las
     * 13:30 (que termina justo a las 14:00) es válida. Con {@code duracionMinutos}
     * a 0 (aún no se ha elegido servicio) devuelve todas las horas del paso dentro
     * de los tramos, sin filtrar por duración.
     *
     * @param dia            día para el que se calculan las horas
     * @param duracionMinutos duración de la cita (0 si aún no se conoce)
     * @param pasoMinutos    granularidad de la rejilla de horas (p. ej. 15)
     * @return lista ordenada de horas válidas (posiblemente vacía)
     */
    public List<LocalTime> horasValidas(LocalDate dia, int duracionMinutos, int pasoMinutos) {
        List<LocalTime> horas = new ArrayList<>();
        for (Tramo tramo : tramosDe(dia)) {
            int iniMin = tramo.inicio().getHour() * 60 + tramo.inicio().getMinute();
            int finMin = tramo.fin().getHour() * 60 + tramo.fin().getMinute();
            // Se trabaja en minutos desde medianoche para no depender de la
            // aritmética de LocalTime (que da la vuelta a medianoche).
            for (int t = iniMin; t < finMin; t += pasoMinutos) {
                if (t + duracionMinutos <= finMin) {
                    horas.add(LocalTime.of(t / 60, t % 60));
                }
            }
        }
        return horas;
    }

    private static LocalTime parseHora(Object valor) {
        if (!(valor instanceof String texto)) {
            return null;
        }
        try {
            return LocalTime.parse(texto);  // admite "HH:MM"
        } catch (RuntimeException e) {
            return null;
        }
    }
}
