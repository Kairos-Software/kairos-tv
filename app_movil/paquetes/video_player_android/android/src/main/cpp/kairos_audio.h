/* Kairos TV: decodificador de audio MP1 / MP2 (ver kairos_audio.c). */
#ifndef KAIROS_AUDIO_H
#define KAIROS_AUDIO_H

#include <stdint.h>

void *kairos_abrir(void);
void kairos_reiniciar(void *decodificador);
void kairos_cerrar(void *decodificador);

/* Devuelve cuántos BYTES de PCM 16 bits escribió en `salida` (0 si no había un cuadro entero o venía roto). */
int kairos_decodificar(void *decodificador, const uint8_t *entrada, int largo, int16_t *salida, int capacidad_bytes,
                       int *canales, int *frecuencia);

#endif
