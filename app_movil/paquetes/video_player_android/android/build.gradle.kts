group = "io.flutter.plugins.videoplayer"
version = "1.0-SNAPSHOT"

buildscript {
    val kotlinVersion = "2.3.0"
    repositories {
        google()
        mavenCentral()
    }

    dependencies {
        classpath("com.android.tools.build:gradle:8.13.1")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:$kotlinVersion")
    }
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

plugins {
    id("com.android.library")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

android {
    namespace = "io.flutter.plugins.videoplayer"
    compileSdk = flutter.compileSdkVersion

    defaultConfig {
        minSdk = 24
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        consumerProguardFiles("kairos-proguard.pro")
    }

    // Kairos TV: el decodificador de audio MP1 / MP2 (src/main/cpp/, ver KairosAudioMpeg.java)
    ndkVersion = flutter.ndkVersion
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    lint {
        checkAllWarnings = true
        warningsAsErrors = true
        disable.addAll(setOf("AndroidGradlePluginVersion", "InvalidPackage", "GradleDependency", "NewerVersionAvailable"))
        baseline = file("lint-baseline.xml")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    dependencies {
        val exoplayerVersion = "1.9.2"
        implementation("androidx.media3:media3-exoplayer:${exoplayerVersion}")
        implementation("androidx.media3:media3-exoplayer-hls:${exoplayerVersion}")
        implementation("androidx.media3:media3-exoplayer-dash:${exoplayerVersion}")
        implementation("androidx.media3:media3-exoplayer-rtsp:${exoplayerVersion}")
        implementation("androidx.media3:media3-exoplayer-smoothstreaming:${exoplayerVersion}")
        // Kairos TV: las anotaciones que usa el decodificador FFmpeg de media3 (solo al compilar). Ver ffmpeg/README.md
        compileOnly("org.checkerframework:checker-qual:3.43.0")
        testImplementation("junit:junit:4.13.2")
        testImplementation("androidx.test:core:1.7.0")
        testImplementation("org.mockito:mockito-core:5.23.0")
        testImplementation("org.robolectric:robolectric:4.16")
        testImplementation("androidx.media3:media3-test-utils:${exoplayerVersion}")
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
            all {
                it.outputs.upToDateWhen { false }
                it.testLogging {
                    events("passed", "skipped", "failed", "standardOut", "standardError")
                    showStandardStreams = true
                }
                // The org.gradle.jvmargs property that may be set in gradle.properties does not impact
                // the Java heap size when running the Android unit tests. The following property here
                // sets the heap size to a size large enough to run the robolectric tests across
                // multiple SDK levels.
                it.jvmArgs("-Xmx4G")
            }
        }
    }
}
