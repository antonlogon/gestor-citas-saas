package com.example.appclinica.data.model

import com.google.gson.annotations.SerializedName

/**
 * Perfil del cliente autenticado (schema `Cliente` del backend).
 * Se obtiene vía GET /clientes/me para, por ejemplo, saludar por su nombre.
 */
data class Cliente(
    val id: Int,
    @SerializedName("empresa_id") val empresaId: Int,
    val nombre: String,
    val email: String,
    val telefono: String
)
