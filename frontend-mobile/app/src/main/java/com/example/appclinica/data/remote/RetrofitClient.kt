package com.example.appclinica.data.remote

import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Punto ÚNICO de acceso a la red de la aplicación.
 *
 * Toda llamada al backend —REST y asistente virtual— sale de aquí, por lo que
 * la URL base y la autenticación se definen en un solo sitio. No debe crearse
 * ninguna otra instancia de Retrofit en el proyecto: dos clientes en paralelo
 * significan dos URLs que mantener sincronizadas y dos formas de autenticar.
 *
 * BASE_URL apunta a 10.0.2.2, la IP con la que el emulador de Android accede al
 * `localhost` de la máquina anfitriona (donde corre FastAPI).
 *
 * USO: antes de la primera llamada, asigna la fuente del token (normalmente
 * `SessionManager::fetchToken`) para que el [AuthInterceptor] pueda inyectarlo.
 * Se hace una sola vez en `AppClinicaApp.onCreate`:
 *
 *     RetrofitClient.tokenProvider = { sessionManager.fetchToken() }
 */
object RetrofitClient {

    private const val BASE_URL = "http://10.0.2.2:8000/"

    /** Proveedor dinámico del JWT. Debe configurarse tras crear el SessionManager. */
    var tokenProvider: () -> String? = { null }

    private val okHttpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            // Se pasa una lambda que delega en el provider actual: así, aunque
            // `tokenProvider` se reasigne más tarde, el interceptor siempre lee el vigente.
            .addInterceptor(AuthInterceptor { tokenProvider() })
            .connectTimeout(30, TimeUnit.SECONDS)
            // 60 s de lectura porque el LLM local puede tardar en responder. Las
            // llamadas REST normales resuelven en milisegundos, así que compartir
            // este cliente no las penaliza: el margen solo actúa si el servidor
            // se queda colgado.
            .readTimeout(60, TimeUnit.SECONDS)
            .build()
    }

    /** Retrofit configurado con el cliente autenticado. Base de ambos servicios. */
    private val retrofit: Retrofit by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    /** API REST del backend: login, citas y perfil. */
    val apiService: ApiService by lazy { retrofit.create(ApiService::class.java) }

    /** Endpoint conversacional del asistente virtual. */
    val chatApiService: ChatApiService by lazy { retrofit.create(ChatApiService::class.java) }
}
