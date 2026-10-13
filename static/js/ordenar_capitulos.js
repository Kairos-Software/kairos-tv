/*
 * Ordenar los capítulos de una temporada (canales/serie_detalle.html).
 *
 * Se ordena en la misma lista: arrastrando un capítulo de los puntitos (con
 * el mouse o con el dedo) o con las flechas. Al cambiar algo aparece abajo
 * la barra "Guardar orden / Deshacer". El botón del aviso de desordenados
 * los ordena por el número que dice cada título ("Capítulo 12").
 *
 * Lo que se manda al guardar es el orden de los <input name="capitulo">: el
 * servidor los renumera 1, 2, 3... (canales/organizar.py -> ordenar_capitulos).
 */
(function () {
    'use strict';

    var sinGuardar = false;

    function preparar(form) {
        var lista = form.querySelector('.cap-lista');
        var barra = form.querySelector('[data-orden-barra]');
        var cuenta = form.querySelector('[data-orden-cuenta]');
        var original = filas();
        var arrastrada = null;
        var puntero = {x: 0, y: 0};

        function filas() {
            return Array.prototype.slice.call(lista.children);
        }

        function renumerar() {
            var movidos = 0;
            filas().forEach(function (fila, indice) {
                fila.querySelector('.cap-numero').textContent = indice + 1;
                var movida = original[indice] !== fila;
                fila.classList.toggle('cap-movido', movida);
                if (movida) movidos += 1;
            });
            barra.hidden = movidos === 0;
            sinGuardar = movidos > 0;
            cuenta.textContent = movidos === 1 ? '1 capítulo cambió de lugar.'
                : movidos + ' capítulos cambiaron de lugar.';
        }

        function poner(enOrden) {
            enOrden.forEach(function (fila) { lista.appendChild(fila); });
            renumerar();
        }

        // Flechas
        lista.addEventListener('click', function (evento) {
            var boton = evento.target.closest('[data-mover]');
            if (!boton) return;
            var fila = boton.closest('.cap');
            if (boton.getAttribute('data-mover') === '-1') {
                if (fila.previousElementSibling) lista.insertBefore(fila, fila.previousElementSibling);
            } else if (fila.nextElementSibling) {
                lista.insertBefore(fila.nextElementSibling, fila);
            }
            renumerar();
            boton.focus();
            fila.scrollIntoView({block: 'nearest'});
        });

        form.querySelector('[data-orden-deshacer]').addEventListener('click', function () { poner(original); });
        form.addEventListener('submit', function () { sinGuardar = false; });

        // Por el número del título (los que no dicen número quedan al final, como estaban)
        var porTitulo = form.querySelector('[data-orden-por-titulo]');
        if (porTitulo) {
            porTitulo.addEventListener('click', function () {
                var actuales = filas();
                var numero = function (fila) {
                    var valor = fila.getAttribute('data-numero-en-el-titulo');
                    return valor === '' ? Infinity : Number(valor);
                };
                poner(actuales.slice().sort(function (a, b) {
                    return (numero(a) - numero(b)) || (actuales.indexOf(a) - actuales.indexOf(b));
                }));
                porTitulo.closest('.orden-aviso').hidden = true;
                barra.scrollIntoView({block: 'nearest', behavior: 'smooth'});
            });
        }

        // Arrastrar (mouse o dedo): la fila sigue al puntero y las demás se corren
        function moverA(x, y) {
            var debajo = document.elementFromPoint(x, y);
            debajo = debajo && debajo.closest('.cap');
            if (!debajo || debajo === arrastrada || debajo.parentNode !== lista) return;
            var caja = debajo.getBoundingClientRect();
            lista.insertBefore(arrastrada, y < caja.top + caja.height / 2 ? debajo : debajo.nextElementSibling);
            renumerar();
        }

        function desplazarSiHaceFalta() {
            // Cerca del borde de la ventana, la página se mueve sola (series largas)
            if (!arrastrada) return;
            var margen = 70;
            var paso = puntero.y < margen ? -14 : (puntero.y > window.innerHeight - margen ? 14 : 0);
            if (paso) {
                window.scrollBy(0, paso);
                moverA(puntero.x, puntero.y);
            }
            window.requestAnimationFrame(desplazarSiHaceFalta);
        }

        lista.addEventListener('pointerdown', function (evento) {
            var agarre = evento.target.closest('.cap-agarre');
            if (!agarre || evento.button > 0) return;
            evento.preventDefault();
            arrastrada = agarre.closest('.cap');
            arrastrada.classList.add('cap-arrastrando');
            agarre.setPointerCapture(evento.pointerId);
            puntero = {x: evento.clientX, y: evento.clientY};
            window.requestAnimationFrame(desplazarSiHaceFalta);
        });
        lista.addEventListener('pointermove', function (evento) {
            if (!arrastrada) return;
            puntero = {x: evento.clientX, y: evento.clientY};
            moverA(puntero.x, puntero.y);
        });
        function soltar() {
            if (!arrastrada) return;
            arrastrada.classList.remove('cap-arrastrando');
            arrastrada = null;
            renumerar();
        }
        lista.addEventListener('pointerup', soltar);
        lista.addEventListener('pointercancel', soltar);
    }

    document.querySelectorAll('[data-orden]').forEach(preparar);

    // Si se va de la página sin guardar, el navegador pregunta
    window.addEventListener('beforeunload', function (evento) {
        if (!sinGuardar) return;
        evento.preventDefault();
        evento.returnValue = '';
    });
})();
