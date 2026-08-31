plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.example.appclinica"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.example.appclinica"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        // La interfaz es 100 % vistas XML + Material Components; no se usa
        // Jetpack Compose en ninguna pantalla.
        viewBinding = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.ktx)

    // Interfaz basada en Vistas (XML)
    implementation(libs.androidx.constraintlayout)
    implementation(libs.androidx.recyclerview)
    implementation(libs.androidx.cardview)
    implementation(libs.material)

    // Capa de red: Retrofit + conversor Gson
    implementation(libs.retrofit)
    implementation(libs.retrofit.converter.gson)

    // Corrutinas para Android (lifecycleScope + llamadas suspend)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
}
