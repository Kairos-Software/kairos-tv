import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// La clave con la que se firma la APK de release. Los datos están en
// android/key.properties (NO va al repo; ver android/key.properties.ejemplo).
val propiedadesClave = Properties()
val archivoClave = rootProject.file("key.properties")
if (archivoClave.exists()) {
    propiedadesClave.load(FileInputStream(archivoClave))
}

android {
    namespace = "com.kairossoftware.app_movil"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        // Lo pide flutter_local_notifications ("Avisarme" de la Agenda, lib/movil/agenda.dart)
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        // El identificador de la app en Android (y en Play Store). NO cambiarlo una vez
        // publicada: Android la tomaría como otra app y habría que reinstalar.
        applicationId = "com.kairossoftware.kairostv"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // Dos apps distintas (se pueden tener las dos instaladas a la vez):
    //   produccion: la que se publica. Habla SIEMPRE con el servidor de
    //               producción (lib/config.dart). Es la que se arma por defecto
    //               (pubspec.yaml -> default-flavor).
    //   local:      para probar contra el servidor de la PC. Se llama "Kairos TV
    //               Local" y tiene otro identificador: nunca reemplaza a la de
    //               producción ni recibe sus actualizaciones.
    //     flutter run --flavor local
    //     flutter build apk --release --flavor local
    flavorDimensions += "servidor"
    productFlavors {
        create("produccion") {
            dimension = "servidor"
            resValue("string", "app_name", "Kairos TV")
        }
        create("local") {
            dimension = "servidor"
            applicationIdSuffix = ".local"
            versionNameSuffix = "-local"
            resValue("string", "app_name", "Kairos TV Local")
        }
    }

    buildFeatures {
        resValues = true
    }

    // Solo procesadores ARM (todos los celulares y TV box). La versión x86_64
    // (emuladores y algunas PC) sumaba 22 MB: sin ella la APK pesa ~40 MB en
    // vez de ~62, y se baja e instala más rápido en TVs con poco espacio.
    packaging {
        jniLibs {
            excludes += "lib/x86_64/**"
        }
    }

    signingConfigs {
        create("release") {
            if (archivoClave.exists()) {
                keyAlias = propiedadesClave["keyAlias"] as String
                keyPassword = propiedadesClave["keyPassword"] as String
                storeFile = file(propiedadesClave["storeFile"] as String)
                storePassword = propiedadesClave["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // Con key.properties: firma con TU clave. Sin él: con la clave de
            // prueba (sirve para probar, pero no para publicar ni actualizar).
            signingConfig = if (archivoClave.exists()) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    // FileProvider: para pasarle al instalador la APK nueva (MainActivity.kt)
    implementation("androidx.core:core-ktx:1.13.1")
    // Meter un script en el reproductor de YouTube (elegir el audio en castellano, MainActivity.kt)
    implementation("androidx.webkit:webkit:1.15.0")
    // Lo pide flutter_local_notifications (ver compileOptions)
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}

// cronet_http (la app le habla a YouTube con Cronet, ver lib/senales.dart)
// trae cronet-api 141, que viene partida en dos módulos con el mismo
// "namespace" y el Android Gradle de este proyecto no compila ("Namespace
// 'org.chromium.net' is used in multiple modules"). La 119 es un solo módulo
// y tiene todo lo que usa cronet_http.
configurations.all {
    resolutionStrategy {
        force("org.chromium.net:cronet-api:119.6045.31")
    }
}
