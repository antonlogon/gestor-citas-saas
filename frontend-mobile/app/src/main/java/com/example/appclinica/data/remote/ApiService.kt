package com.example.appclinica.data.remote

import com.example.appclinica.data.model.Cita
import com.example.appclinica.data.model.Cliente
import com.example.appclinica.data.model.LoginResponse
import retrofit2.http.Field
import retrofit2.http.FormUrlEncoded
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * Contrato de la API REST del backend (FastAPI).
 *
 * El endpoint de login usa `OAuth2PasswordRequestForm`, por lo que espera datos
 * codificados como `application/x-www-form-urlencoded` (NO JSON) con los campos
 * `username` (el email) y `password`.
 *
 * Ninguna operación declara la cabecera `Authorization`: la inyecta de forma
 * centralizada el [AuthInterceptor] a partir del token de sesión vigente (ver
 * [RetrofitClient]). Es intencionado que `login` también la reciba si hubiera
 * una sesión previa: el backend resuelve las credenciales desde el cuerpo del
 * formulario e ignora la cabecera.
 */
interface ApiService {

    @FormUrlEncoded
    @POST("login")
    suspend fun login(
        @Field("username") username: String,
        @Field("password") password: String
    ): LoginResponse

    /**
     * Lista las citas del usuario autenticado.
     *
     * Endpoint real del backend: `GET /citas/`. Para un cliente, el backend
     * fuerza el filtro a sus propias citas a partir del token, así que este
     * mismo endpoint actúa como "mis citas".
     *
     * @param proximas recorta el listado a partir de ahora, descartando lo ya
     *   pasado. El corte lo aplica el servidor con SU reloj, no el del
     *   teléfono, que puede ir desviado. Es un corte solo temporal: las
     *   canceladas que aún no han llegado vienen igualmente, para que el
     *   paciente se entere de la cancelación en vez de ver un hueco.
     */
    @GET("citas/")
    suspend fun getMisCitas(
        @Query("proximas") proximas: Boolean
    ): List<Cita>

    /**
     * Perfil del cliente autenticado. El nombre no viaja en el JWT, así que
     * la app lo obtiene con esta llamada extra para personalizar el saludo.
     */
    @GET("clientes/me")
    suspend fun getMiPerfil(): Cliente
}
