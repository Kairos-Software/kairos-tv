/*
 * Prueba del decodificador MP1 / MP2 (../../main/cpp/kairos_audio.c), en la compu:
 *
 *   gcc -O2 -I ../../main/cpp kairos_audio_prueba.c ../../main/cpp/kairos_audio.c -o prueba && ./prueba tono_440hz.mp2
 *
 * tono_440hz.mp2: 2 segundos de un tono de 440 Hz, estéreo, 48 kHz, MP2 a 128 kb/s
 * (ffmpeg -f lavfi -i sine=frequency=440:sample_rate=48000:duration=2 -ac 2 -c:a mp2 -b:a 128k tono_440hz.mp2).
 *
 * Lo decodifica como lo hace el reproductor (un cuadro por vez, como los entrega
 * el lector de MPEG-TS) y de una sola vez, y comprueba que salga sonido de
 * verdad: la cantidad de muestras, que no sea silencio y que la frecuencia sea 440 Hz.
 * También que un cuadro roto o cortado no rompa nada.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "kairos_audio.h"

static int fallas = 0;

#define CHEQUEAR(condicion, ...) do { if (!(condicion)) { printf("FALLA: " __VA_ARGS__); printf("\n"); fallas++; } \
                                     else { printf("ok: " __VA_ARGS__); printf("\n"); } } while (0)

/* El largo de un cuadro MPEG audio capa 2 a partir de su encabezado (como hace el lector del reproductor). */
static int largo_de_cuadro(const uint8_t *h) {
    static const int kbps_l2[16] = {0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0};
    static const int hz[4] = {44100, 48000, 32000, 0};
    if (h[0] != 0xFF || (h[1] & 0xE0) != 0xE0) return -1;
    int bitrate = kbps_l2[(h[2] >> 4) & 0xF] * 1000;
    int frecuencia = hz[(h[2] >> 2) & 3];
    int relleno = (h[2] >> 1) & 1;
    if (!bitrate || !frecuencia) return -1;
    return 144 * bitrate / frecuencia + relleno;
}

static void analizar(const int16_t *pcm, int muestras_por_canal, double *rms, double *frecuencia) {
    double suma = 0;
    int cruces = 0;
    for (int i = 0; i < muestras_por_canal; i++) {
        double v = pcm[i * 2];   /* canal izquierdo */
        suma += v * v;
        if (i > 0 && pcm[(i - 1) * 2] < 0 && pcm[i * 2] >= 0) cruces++;
    }
    *rms = sqrt(suma / muestras_por_canal);
    *frecuencia = cruces / (muestras_por_canal / 48000.0);
}

int main(int argc, char **argv) {
    FILE *archivo = fopen(argc > 1 ? argv[1] : "tono_440hz.mp2", "rb");
    if (!archivo) { printf("No se encontró el archivo de prueba\n"); return 2; }
    uint8_t *datos = malloc(1 << 20);
    int largo = (int) fread(datos, 1, 1 << 20, archivo);
    fclose(archivo);
    int16_t *pcm = malloc(48000 * 2 * 4 * sizeof(int16_t));
    int capacidad = 48000 * 2 * 4 * (int) sizeof(int16_t);

    /* 1. Un cuadro por vez (como lo entrega el reproductor) */
    void *dec = kairos_abrir();
    int bytes_pcm = 0, cuadros = 0, canales = 0, hz = 0;
    for (int pos = 0; pos + 4 <= largo;) {
        int cuadro = largo_de_cuadro(datos + pos);
        if (cuadro <= 0 || pos + cuadro > largo) break;
        bytes_pcm += kairos_decodificar(dec, datos + pos, cuadro, pcm + bytes_pcm / 2, capacidad - bytes_pcm,
                                        &canales, &hz);
        pos += cuadro;
        cuadros++;
    }
    int por_canal = bytes_pcm / 2 / 2;
    double rms, frecuencia;
    analizar(pcm, por_canal, &rms, &frecuencia);
    CHEQUEAR(cuadros > 80, "%d cuadros leídos", cuadros);
    CHEQUEAR(canales == 2 && hz == 48000, "estéreo a 48 kHz (%d canales, %d Hz)", canales, hz);
    CHEQUEAR(por_canal >= (cuadros - 1) * 1152, "%d muestras por canal (1152 por cuadro)", por_canal);
    CHEQUEAR(rms > 1000, "hay sonido, no silencio (nivel %.0f)", rms);
    CHEQUEAR(fabs(frecuencia - 440) < 10, "el tono es de 440 Hz (sale %.1f Hz)", frecuencia);

    /* 2. Todo de una vez (varios cuadros en un mismo pedazo) */
    kairos_reiniciar(dec);
    int de_una = kairos_decodificar(dec, datos, largo, pcm, capacidad, NULL, NULL);
    CHEQUEAR(de_una >= bytes_pcm - 1152 * 2 * 2, "de una vez sale lo mismo (%d bytes contra %d)", de_una, bytes_pcm);

    /* 3. Lo que no es audio, un cuadro cortado o un buffer chico: no rompe ni escribe de más */
    uint8_t basura[700];
    for (int i = 0; i < (int) sizeof basura; i++) basura[i] = (uint8_t) (i * 37);
    CHEQUEAR(kairos_decodificar(dec, basura, sizeof basura, pcm, capacidad, NULL, NULL) == 0, "basura: 0 bytes");
    int primero = largo_de_cuadro(datos);
    kairos_reiniciar(dec);
    CHEQUEAR(kairos_decodificar(dec, datos, primero / 2, pcm, capacidad, NULL, NULL) == 0, "cuadro cortado: 0 bytes");
    int16_t chico[100];
    chico[99] = 12345;
    kairos_decodificar(dec, datos, largo, chico, 99 * 2, NULL, NULL);
    CHEQUEAR(chico[99] == 12345, "con un buffer chico no escribe de más");
    CHEQUEAR(kairos_decodificar(NULL, datos, largo, pcm, capacidad, NULL, NULL) == 0, "sin decodificador: 0 bytes");

    kairos_cerrar(dec);
    free(datos);
    free(pcm);
    printf(fallas ? "\nHUBO %d FALLAS\n" : "\nTodo bien\n", fallas);
    return fallas ? 1 : 0;
}
