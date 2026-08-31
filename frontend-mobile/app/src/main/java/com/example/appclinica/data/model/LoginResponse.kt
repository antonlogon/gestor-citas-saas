package com.example.appclinica.data.model

import com.google.gson.annotations.SerializedName

/**
 * Respuesta del endpoint POST /login.
 *
 * Refleja el schema `Token` del backend (backend-api/app/schemas.py):
 *   { "access_token": "...", "token_type": "bearer" }
 */
data class LoginResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String
)
