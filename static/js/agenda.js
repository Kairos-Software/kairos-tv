/*
 * La Agenda del panel (agenda/templates/agenda/):
 *   - Lista: "¿Sacar ... de la agenda?" antes de eliminar (data-confirmar).
 *   - Formulario: el buscador de arriba de la lista de canales la va achicando
 *     (por nombre o número) y elige el primero que coincide.
 */
(function () {
    'use strict';

    document.querySelectorAll('[data-confirmar]').forEach(function (boton) {
        if (!boton.form) return;
        boton.form.addEventListener('submit', function (evento) {
            if (!window.confirm(boton.dataset.confirmar)) evento.preventDefault();
        });
    });

    function sinAcentos(texto) {
        return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    }

    document.querySelectorAll('[data-filtra]').forEach(function (buscador) {
        var lista = document.getElementById(buscador.dataset.filtra);
        if (!lista) return;
        buscador.addEventListener('input', function () {
            var buscado = sinAcentos(buscador.value.trim());
            var primero = null;
            Array.prototype.forEach.call(lista.options, function (opcion) {
                var coincide = !buscado || !opcion.value || sinAcentos(opcion.text).indexOf(buscado) >= 0;
                opcion.hidden = !coincide;
                if (coincide && opcion.value && !primero) primero = opcion;
            });
            if (buscado && primero) lista.value = primero.value;
        });
    });
})();
