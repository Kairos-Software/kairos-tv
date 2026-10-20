/* Kairos TV: lo que llama Java (KairosAudioMpeg.java) para decodificar MP1 / MP2 (ver kairos_audio.c). */
#include <jni.h>
#include <stdint.h>

#include "kairos_audio.h"

JNIEXPORT jlong JNICALL
Java_io_flutter_plugins_videoplayer_KairosAudioMpeg_nativoAbrir(JNIEnv *env, jclass clase) {
    return (jlong) (intptr_t) kairos_abrir();
}

JNIEXPORT void JNICALL
Java_io_flutter_plugins_videoplayer_KairosAudioMpeg_nativoReiniciar(JNIEnv *env, jclass clase, jlong decodificador) {
    kairos_reiniciar((void *) (intptr_t) decodificador);
}

JNIEXPORT void JNICALL
Java_io_flutter_plugins_videoplayer_KairosAudioMpeg_nativoCerrar(JNIEnv *env, jclass clase, jlong decodificador) {
    kairos_cerrar((void *) (intptr_t) decodificador);
}

/* `entrada` y `salida` son ByteBuffer directos. Devuelve los bytes de PCM escritos (-1 si los buffers no sirven). */
JNIEXPORT jint JNICALL
Java_io_flutter_plugins_videoplayer_KairosAudioMpeg_nativoDecodificar(
        JNIEnv *env, jclass clase, jlong decodificador, jobject entrada, jint largo, jobject salida) {
    const uint8_t *datos = (const uint8_t *) (*env)->GetDirectBufferAddress(env, entrada);
    int16_t *pcm = (int16_t *) (*env)->GetDirectBufferAddress(env, salida);
    jlong capacidad_entrada = (*env)->GetDirectBufferCapacity(env, entrada);
    jlong capacidad_salida = (*env)->GetDirectBufferCapacity(env, salida);
    if (datos == NULL || pcm == NULL || largo < 0 || largo > capacidad_entrada || capacidad_salida <= 0) return -1;
    return kairos_decodificar((void *) (intptr_t) decodificador, datos, largo, pcm, (int) capacidad_salida, NULL, NULL);
}
