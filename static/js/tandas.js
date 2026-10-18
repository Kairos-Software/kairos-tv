/* ═══════════════════════════════════════════════════════════════
   tandas.js — corre una tarea larga de a tandas.

   El servidor hace un pedacito por pedido (ej: verifica 50 canales) y
   responde cómo va (JSON). Esto lo llama una y otra vez hasta que termina,
   y en cada vuelta avisa para pintar el avance. Así ningún pedido tarda
   demasiado y el servidor no se satura.

     var tarea = Tandas({
         url: '/canales/importaciones/7/lote/',
         datos: function () { return {desde: 120}; },   // opcional: qué mandar en cada pedido
         termino: function (r) { return r.terminada; },  // ¿ya está?
         alAvanzar: function (r) { ... },                // pintar el avance
         alTerminar: function (r) { ... },
         alCambiar: function (corriendo) { ... },        // para los botones Empezar / Pausar
         alError: function (mensaje) { ... },
     });
     tarea.empezar();  tarea.pausar();  tarea.cancelar();
   ═══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    var REINTENTOS = 3;          // errores seguidos antes de pausar
    var ESPERA_ERROR = 5000;     // ms entre reintentos
    var ESPERA_OCUPADA = 3000;   // otra pestaña está procesando lo mismo

    function esperar(ms) {
        return new Promise(function (resolver) { setTimeout(resolver, ms); });
    }

    function tokenCsrf() {
        var campo = document.querySelector('input[name=csrfmiddlewaretoken]');
        if (campo) return campo.value;
        var cookie = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return cookie ? decodeURIComponent(cookie[1]) : '';
    }

    window.Tandas = function (opciones) {
        var corriendo = false;
        var nada = function () {};
        var alAvanzar = opciones.alAvanzar || nada;
        var alTerminar = opciones.alTerminar || nada;
        var alCambiar = opciones.alCambiar || nada;
        var alError = opciones.alError || nada;
        var alCancelar = opciones.alCancelar || nada;
        var pedidoEnCurso = null;

        function avisarAlSalir(evento) {
            // Si se cierra la página se corta (se puede seguir después), pero mejor avisar
            evento.preventDefault();
            evento.returnValue = '';
        }

        function cambiar(valor) {
            corriendo = valor;
            if (valor) window.addEventListener('beforeunload', avisarAlSalir);
            else window.removeEventListener('beforeunload', avisarAlSalir);
            alCambiar(valor);
        }

        async function pedir() {
            var cuerpo = new FormData();
            var extra = opciones.datos ? opciones.datos() : {};
            Object.keys(extra).forEach(function (clave) { cuerpo.append(clave, extra[clave]); });
            pedidoEnCurso = new AbortController();
            try {
                var respuesta = await fetch(opciones.url, {
                    method: 'POST',
                    body: cuerpo,
                    credentials: 'same-origin',
                    headers: {'X-CSRFToken': tokenCsrf(), 'Accept': 'application/json'},
                    signal: pedidoEnCurso.signal,
                });
                if (!respuesta.ok) throw new Error('El servidor respondió ' + respuesta.status + '.');
                return respuesta.json();
            } finally {
                pedidoEnCurso = null;
            }
        }

        async function cancelarEnServidor() {
            if (!opciones.urlCancelar) return;
            var respuesta = await fetch(opciones.urlCancelar, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {'X-CSRFToken': tokenCsrf(), 'Accept': 'application/json'},
            });
            if (!respuesta.ok) throw new Error('El servidor respondió ' + respuesta.status + '.');
            await respuesta.json();
        }

        async function correr() {
            var errores = 0;
            while (corriendo) {
                var resultado;
                try {
                    resultado = await pedir();
                    errores = 0;
                } catch (error) {
                    if (!corriendo || error.name === 'AbortError') return;
                    errores += 1;
                    if (errores >= REINTENTOS) {
                        cambiar(false);
                        alError('Se cortó: ' + error.message + ' Revisá la conexión y tocá "Continuar".');
                        return;
                    }
                    await esperar(ESPERA_ERROR);
                    continue;
                }
                if (!corriendo) return;   // la pausaron mientras esperaba la respuesta
                alAvanzar(resultado);
                if (opciones.termino(resultado)) {
                    cambiar(false);
                    alTerminar(resultado);
                    return;
                }
                if (resultado.ocupada) await esperar(ESPERA_OCUPADA);
            }
        }

        return {
            empezar: function () {
                if (corriendo) return;
                cambiar(true);
                correr();
            },
            pausar: function () { if (corriendo) cambiar(false); },
            cancelar: async function () {
                if (corriendo) cambiar(false);
                if (pedidoEnCurso) pedidoEnCurso.abort();
                try {
                    await cancelarEnServidor();
                    alCancelar();
                } catch (error) {
                    alError('No se pudo cancelar: ' + error.message);
                }
            },
            corriendo: function () { return corriendo; },
        };
    };

    // Formatos que usan las pantallas
    window.Tandas.numero = function (n) { return Number(n || 0).toLocaleString('es-AR'); };
    window.Tandas.duracion = function (segundos) {
        segundos = Math.max(0, Math.round(segundos));
        if (segundos < 60) return segundos + ' s';
        var minutos = Math.round(segundos / 60);
        if (minutos < 60) return minutos + ' min';
        return Math.floor(minutos / 60) + ' h ' + (minutos % 60) + ' min';
    };
})();
