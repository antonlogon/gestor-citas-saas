package com.example.appclinica.data.model

import com.google.gson.annotations.SerializedName

/**
 * Representa una cita tal y como la devuelve el backend (schema `Cita` en
 * backend-api/app/schemas.py).
 *
 * El backend "aplana" los nombres del servicio y del empleado (servicio_nombre
 * y empleado_nombre) para que el cliente no tenga que resolver los IDs.
 *
 * `fechaHora` llega como texto ISO-8601 (p. ej. "2026-08-20T10:00:00"); se
 * formatea para mostrar en el adaptador.
 */
data class Cita(
    val id: Int,
    @SerializedName("fecha_hora") val fechaHora: String,
    @SerializedName("notas_ia") val notasIa: String?,
    @SerializedName("empresa_id") val empresaId: Int,
    @SerializedName("cliente_id") val clienteId: Int,
    @SerializedName("empleado_id") val empleadoId: Int,
    @SerializedName("servicio_id") val servicioId: Int,
    val estado: String,
    @SerializedName("servicio_nombre") val servicioNombre: String?,
    @SerializedName("empleado_nombre") val empleadoNombre: String?
)
