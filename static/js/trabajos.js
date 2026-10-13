/* ═══════════════════════════════════════════════════════════════
   trabajos.js — los trabajos pesados en curso, arriba del panel.

   Pinta lo que llegó con la página (#trabajos-iniciales) y después
   pregunta cada 10 segundos (solo con la pestaña a la vista), así
   cualquiera que tenga el panel abierto, en cualquier navegador, ve cuándo
   empieza, cuánto va y cuándo termina un trabajo. Ver core/trabajos.py.
   ═══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    var CADA = 10000;   // ms entre preguntas
    var caja = document.querySelector('[data-trabajos]');
    if (!caja) return;

    function texto(valor) {
        var span = document.createElement('span');
        span.textContent = valor;
        return span;
    }

    function pintar(trabajos) {
        caja.replaceChildren();
        caja.hidden = !trabajos.length;
        trabajos.forEach(function (t) {
            var fila = document.createElement(t.url ? 'a' : 'div');
            fila.className = 'trabajo';
            if (t.url) fila.href = t.url;

            var punto = document.createElement('span');
            punto.className = 'trabajo-punto';
            punto.setAttribute('aria-hidden', 'true');

            var cuerpo = document.createElement('span');
            cuerpo.className = 'trabajo-cuerpo';
            var titulo = texto(t.titulo);
            titulo.className = 'trabajo-titulo';
            var datos = texto([t.detalle, 'lo empezó ' + t.quien + ' a las ' + t.desde].filter(Boolean).join(' · '));
            datos.className = 'trabajo-datos';
            cuerpo.append(titulo, datos);

            var barra = document.createElement('span');
            barra.className = 'trabajo-barra';
            barra.setAttribute('role', 'progressbar');
            barra.setAttribute('aria-valuenow', t.porcentaje);
            barra.setAttribute('aria-valuemin', '0');
            barra.setAttribute('aria-valuemax', '100');
            var relleno = document.createElement('span');
            relleno.style.width = t.porcentaje + '%';
            barra.append(relleno);

            var porcentaje = texto(t.porcentaje + ' %');
            porcentaje.className = 'trabajo-porcentaje';

            fila.append(punto, cuerpo, barra, porcentaje);
            caja.append(fila);
        });
        if (trabajos.length) {
            var nota = texto('Mientras tanto, los demás trabajos pesados esperan su turno (no se satura el servidor).');
            nota.className = 'trabajos-nota';
            caja.append(nota);
        }
    }

    async function preguntar() {
        if (document.hidden) return;
        try {
            var respuesta = await fetch(caja.dataset.trabajos, {
                credentials: 'same-origin', headers: {'Accept': 'application/json'},
            });
            if (respuesta.ok) pintar((await respuesta.json()).trabajos || []);
        } catch (error) {
            // Sin conexión: queda lo último que se pintó
        }
    }

    var iniciales = document.getElementById('trabajos-iniciales');
    pintar(iniciales ? JSON.parse(iniciales.textContent) || [] : []);
    setInterval(preguntar, CADA);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) preguntar(); });
})();
