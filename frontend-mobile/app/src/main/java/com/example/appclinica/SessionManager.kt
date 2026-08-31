package com.example.appclinica

import android.content.Context
import android.content.SharedPreferences

/**
 * Gestiona la sesión del usuario persistiendo el token JWT en SharedPreferences.
 *
 * Al usar `applicationContext` evitamos fugas de memoria si se guarda una
 * referencia al SessionManager fuera del ciclo de vida de una Activity.
 */
class SessionManager(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /** Guarda el access_token recibido tras un login correcto. */
    fun saveToken(token: String) {
        prefs.edit().putString(KEY_TOKEN, token).apply()
    }

    /** Recupera el token guardado, o `null` si no hay sesión activa. */
    fun fetchToken(): String? = prefs.getString(KEY_TOKEN, null)

    /** Elimina el token (logout). */
    fun clearSession() {
        prefs.edit().clear().apply()
    }

    companion object {
        private const val PREFS_NAME = "app_clinica_session"
        private const val KEY_TOKEN = "access_token"
    }
}
