package com.example.appclinica.data.model

import com.google.gson.annotations.SerializedName

/**
 * Modelos (DTOs) del endpoint conversacional `POST /chatbot/chat`.
 *
 * Los nombres de propiedad Kotlin se mapean con los del JSON del backend
 * mediante @SerializedName, para que Gson serialice/deserialice correctamente
 * aunque cambie la convención de nombres.
 */

/**
 * Un turno del historial de conversación tal y como lo espera el backend.
 * `role` es "user" (paciente) o "assistant" (IA); `content` es el texto.
 */
data class MensajeHistorial(
    @SerializedName("role")
    val role: String,

    @SerializedName("content")
    val content: String
)

/**
 * Cuerpo de la petición. El backend ahora exige el historial completo para dar
 * memoria de contexto a la IA: {"historial": [{"role": ..., "content": ...}, ...]}
 */
data class ChatRequest(
    @SerializedName("historial")
    val historial: List<MensajeHistorial>
)

/** Cuerpo de la respuesta: {"respuesta": "texto de la IA"} */
data class ChatResponse(
    @SerializedName("respuesta")
    val respuesta: String
)
