package com.example.appclinica

import android.app.Application
import com.example.appclinica.data.remote.RetrofitClient

/**
 * Clase Application de la app.
 *
 * Se ejecuta una sola vez, antes que cualquier Activity, por lo que es el punto
 * ideal para enlazar la fuente del token JWT con el cliente de red: así toda
 * petición de [RetrofitClient] viajará ya autenticada sin repetir configuración.
 */
class AppClinicaApp : Application() {

    override fun onCreate() {
        super.onCreate()

        // SessionManager usa internamente applicationContext, así que es seguro
        // mantenerlo vivo durante todo el ciclo de la aplicación.
        val sessionManager = SessionManager(this)
        RetrofitClient.tokenProvider = { sessionManager.fetchToken() }
    }
}
