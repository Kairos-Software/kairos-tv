/*
 * Kairos TV: el decodificador de audio MPEG capa 1 y 2 (MP1 / MP2) propio de
 * la app. MP2 es el audio clásico de los canales de cable y satélite, y
 * Android NO trae decodificador para él: la imagen se veía pero sin sonido
 * (VLC sí suena porque trae los suyos). Ver KairosAudioMpeg.java.
 *
 * Usa minimp3 (https://github.com/lieff/minimp3), de dominio público (CC0,
 * ver minimp3-LICENSE.txt): se puede usar en una app comercial sin obligaciones.
 *
 * kairos_decodificar() recibe uno o más cuadros de audio comprimido y deja
 * el sonido en PCM de 16 bits intercalado (como lo espera el reproductor).
 * Nunca escribe fuera de los buffers: un cuadro roto se saltea (no corta el video).
 */

#define MINIMP3_IMPLEMENTATION
#include "minimp3.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "kairos_audio.h"

void *kairos_abrir(void) {
    mp3dec_t *decodificador = (mp3dec_t *) malloc(sizeof(mp3dec_t));
    if (decodificador != NULL) mp3dec_init(decodificador);
    return decodificador;
}

void kairos_reiniciar(void *decodificador) {
    if (decodificador != NULL) mp3dec_init((mp3dec_t *) decodificador);
}

void kairos_cerrar(void *decodificador) {
    free(decodificador);
}

int kairos_decodificar(void *decodificador, const uint8_t *entrada, int largo, int16_t *salida, int capacidad_bytes,
                       int *canales, int *frecuencia) {
    if (decodificador == NULL || entrada == NULL || salida == NULL || largo <= 0) return 0;
    mp3d_sample_t pcm[MINIMP3_MAX_SAMPLES_PER_FRAME];
    int usados = 0;
    int escritas = 0;   /* muestras de 16 bits ya escritas en `salida` */
    int maximo = capacidad_bytes / (int) sizeof(int16_t);
    while (usados < largo) {
        mp3dec_frame_info_t info;
        int muestras = mp3dec_decode_frame((mp3dec_t *) decodificador, entrada + usados, largo - usados, pcm, &info);
        if (info.frame_bytes <= 0) break;   /* no hay más cuadros enteros */
        usados += info.frame_bytes;
        if (muestras <= 0) continue;        /* cuadro roto o de sincronización: se saltea */
        int cuantas = muestras * info.channels;
        if (escritas + cuantas > maximo) break;
        memcpy(salida + escritas, pcm, (size_t) cuantas * sizeof(int16_t));
        escritas += cuantas;
        if (canales != NULL) *canales = info.channels;
        if (frecuencia != NULL) *frecuencia = info.hz;
    }
    return escritas * (int) sizeof(int16_t);
}
