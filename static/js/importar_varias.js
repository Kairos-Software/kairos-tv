/*
 * Importar varias listas de una (Contenido → "Importar lista", canales/inicio.html):
 *
 *   - El botón "Importar lista" de arriba abre la tarjeta Y el explorador de archivos.
 *   - Se eligen (o se arrastran) varias listas a la vez, y se suben solas, de a una,
 *     apenas se eligen: sin "Subir y analizar".
 *   - Cada una muestra cómo va (esperando, subiendo 40 %, analizando, lista o el error) y,
 *     al terminar, "Abrir" para probarla y cargarla. Las opciones de la tarjeta (prueba,
 *     filtros, destino) valen para todas.
 *
 * Cada lista va en su propio pedido (el mismo formulario, con X-Requested-With): el
 * servidor responde JSON (views.inicio). Sin JavaScript, el formulario anda como siempre (una).
 */
(function () {
    'use strict';

    var form = document.getElementById('form-importar');
    if (!form || !window.FormData) return;
    var campo = form.querySelector('input[type=file][name=archivo]');
    var boton = form.querySelector('button[type=submit]');
    if (!campo) return;
    campo.multiple = true;

    var lista = document.createElement('ul');
    lista.className = 'subidas';
    lista.setAttribute('aria-live', 'polite');
    lista.hidden = true;
    var resumen = document.createElement('p');
    resumen.className = 'subidas-resumen';
    resumen.hidden = true;
    var lugar = campo.closest('[class*="col-"]') || campo.parentNode;
    lugar.appendChild(lista);
    lugar.appendChild(resumen);
    // Ya no hace falta confirmar: se sube al elegir
    if (boton) boton.closest('div').hidden = true;

    var cola = [];
    var subiendo = false;
    var hechas = 0;
    var fallidas = 0;

    function fila(archivo) {
        var item = document.createElement('li');
        item.className = 'subida';
        item.innerHTML = '<i class="bi bi-hourglass-split" aria-hidden="true"></i>' +
            '<span class="subida-nombre"></span><span class="subida-estado">Esperando…</span>';
        item.querySelector('.subida-nombre').textContent = archivo.name;
        lista.appendChild(item);
        lista.hidden = false;
        return item;
    }

    function poner(item, clase, icono, texto) {
        item.className = 'subida ' + clase;
        item.querySelector('i').className = 'bi ' + icono;
        var estado = item.querySelector('.subida-estado');
        estado.textContent = '';
        if (typeof texto === 'string') estado.textContent = texto;
        else estado.appendChild(texto);
    }

    function agregar(archivos) {
        Array.prototype.forEach.call(archivos, function (archivo) {
            cola.push({archivo: archivo, item: fila(archivo)});
        });
        campo.value = '';   // así se puede volver a elegir el mismo archivo
        siguiente();
    }

    function contar() {
        var partes = [];
        if (hechas) partes.push(hechas + (hechas === 1 ? ' lista subida' : ' listas subidas'));
        if (fallidas) partes.push(fallidas + ' con error');
        resumen.innerHTML = '';
        resumen.appendChild(document.createTextNode(partes.join(' · ') + '. Abrí cada una para probarla y cargarla. '));
        var actualizar = document.createElement('a');
        actualizar.href = window.location.pathname + '#importaciones';
        actualizar.textContent = 'Actualizar el historial';
        actualizar.addEventListener('click', function () { window.location.reload(); });
        resumen.appendChild(actualizar);
        resumen.hidden = false;
    }

    function siguiente() {
        if (subiendo) return;
        var proxima = cola.shift();
        if (!proxima) {
            contar();
            return;
        }
        subiendo = true;
        var item = proxima.item;
        var datos = new FormData(form);
        datos.delete('archivo');
        datos.append('archivo', proxima.archivo, proxima.archivo.name);

        var pedido = new XMLHttpRequest();
        pedido.open('POST', form.action || window.location.pathname);
        pedido.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        pedido.upload.onprogress = function (e) {
            if (!e.lengthComputable) return;
            var porcentaje = Math.round(100 * e.loaded / e.total);
            poner(item, 'subiendo', 'bi-cloud-arrow-up', porcentaje < 100 ? 'Subiendo… ' + porcentaje + ' %'
                : 'Analizando… (con listas grandes, un par de minutos)');
        };
        pedido.onload = function () {
            var respuesta = null;
            try { respuesta = JSON.parse(pedido.responseText); } catch (_) { /* no vino JSON */ }
            if (respuesta && respuesta.ok) {
                hechas++;
                var abrir = document.createElement('span');
                var abrirLink = document.createElement('a');
                abrirLink.href = respuesta.url;
                abrirLink.target = '_blank';
                abrirLink.rel = 'noopener';
                abrirLink.className = 'btn btn-sm btn-outline-secondary';
                abrirLink.textContent = 'Abrir';
                abrir.appendChild(document.createTextNode(Tandas.numero(respuesta.total) + ' elementos '));
                abrir.appendChild(abrirLink);
                poner(item, 'lista', 'bi-check-circle-fill', abrir);
            } else {
                fallidas++;
                var mensaje = respuesta && respuesta.error ? respuesta.error
                    : (pedido.status === 413 ? 'Es demasiado grande para el servidor: comprimila en un .zip.'
                        : 'No se pudo subir (' + (pedido.status || 'sin conexión') + ').');
                poner(item, 'error', 'bi-x-circle-fill', mensaje);
            }
            subiendo = false;
            siguiente();
        };
        pedido.onerror = function () {
            fallidas++;
            poner(item, 'error', 'bi-x-circle-fill', 'Se cortó la conexión. Volvé a elegirla.');
            subiendo = false;
            siguiente();
        };
        poner(item, 'subiendo', 'bi-cloud-arrow-up', 'Subiendo…');
        pedido.send(datos);
    }

    campo.addEventListener('change', function () {
        if (campo.files.length) agregar(campo.files);
    });

    // Arrastrar las listas sobre la tarjeta
    var zona = document.getElementById('importar-lista') || form;
    ['dragenter', 'dragover'].forEach(function (tipo) {
        zona.addEventListener(tipo, function (e) {
            if (!e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') < 0) return;
            e.preventDefault();
            zona.open = true;
            zona.classList.add('soltar-aca');
        });
    });
    ['dragleave', 'drop'].forEach(function (tipo) {
        zona.addEventListener(tipo, function (e) {
            if (tipo === 'dragleave' && zona.contains(e.relatedTarget)) return;
            zona.classList.remove('soltar-aca');
        });
    });
    zona.addEventListener('drop', function (e) {
        if (!e.dataTransfer || !e.dataTransfer.files.length) return;
        e.preventDefault();
        agregar(e.dataTransfer.files);
    });

    // "Importar lista" (arriba): abre la tarjeta y directo el explorador
    document.querySelectorAll('[data-abrir-detalle="importar-lista"]').forEach(function (enlace) {
        enlace.addEventListener('click', function () { campo.click(); });
    });

    // Mientras sube, salir de la página corta la subida: se avisa
    window.addEventListener('beforeunload', function (e) {
        if (!subiendo && !cola.length) return;
        e.preventDefault();
        e.returnValue = '';
    });
})();
