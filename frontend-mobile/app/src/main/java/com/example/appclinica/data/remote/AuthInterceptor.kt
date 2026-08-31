package com.example.appclinica.data.remote

import okhttp3.Interceptor
import okhttp3.Response

/**
 * Interceptor de OkHttp que añade la cabecera `Authorization: Bearer <token>`
 * a cada petición saliente.
 *
 * El token se resuelve a través de [tokenProvider] en el momento de la llamada
 * (no se "congela"), de modo que un login o refresh posterior se refleja
 * automáticamente sin recrear el cliente HTTP.
 */
class AuthInterceptor(
    private val tokenProvider: () -> String?
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val requestBuilder = chain.request().newBuilder()

        // Solo se añade la cabecera si hay una sesión activa (token no nulo).
        tokenProvider()?.let { token ->
            requestBuilder.addHeader("Authorization", "Bearer $token")
        }

        return chain.proceed(requestBuilder.build())
    }
}
