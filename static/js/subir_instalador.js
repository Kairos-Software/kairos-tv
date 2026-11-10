/*
 * Subir un instalador para Windows: el de la app para PC (Descargas → App para PC) o el del analizador de canales
 * (Descargas → Analizador para PC, solo superusuarios). Sirve para cada <form data-subir-instalador> de la página:
 *
 *   - Al elegir el archivo, la versión se completa sola con su nombre (data-prefijo: KairosTV-2026.11.10.1530.exe,
 *     KairosAnalizador-2026.11.9.1530.exe).
 *   - Pesa cientos de MB y el servidor acepta hasta 160 MB por pedido: se manda de a pedazos (20 MB) con su
 *     avance; si un pedazo falla, se reintenta hasta 3 veces desde ese mismo lugar.
 *   - Al final se pide publicarlo (descargas/instaladores.py revisa el archivo y calcula su huella) y la página se
 *     recarga con la versión nueva en la lista.
 */
(function () {
    'use strict';

    if (!window.FormData || !window.Blob) return;
    document.querySelectorAll('form[data-subir-instalador]').forEach(preparar);

    function preparar(form) {
    var campo = form.querySelector('[data-archivo]');
    var version = form.querySelector('[data-version]');
    var notas = form.querySelector('[data-notas]');
    var prefijo = form.dataset.prefijo || 'KairosTV';
    var boton = form.querySelector('button[type=submit]');
    var subida = form.querySelector('[data-subida]');
    var barra = subida.querySelector('[role=progressbar]');
    var texto = subida.querySelector('[data-subida-texto]');
    var token = form.querySelector('input[name=csrfmiddlewaretoken]').value;
    var TAMANIO = parseInt(form.dataset.tamanioPedazo, 10) || 20 * 1024 * 1024;
    var subiendo = false;

    function mb(bytes) {
        return (bytes / (1024 * 1024)).toLocaleString('es-AR', {maximumFractionDigits: 0}) + ' MB';
    }

    function mostrar(porcentaje, mensaje, error) {
        subida.hidden = false;
        subida.classList.toggle('error', !!error);
        barra.setAttribute('aria-valuenow', porcentaje);
        barra.firstElementChild.style.width = porcentaje + '%';
        texto.textContent = mensaje;
    }

    function identificador() {
        var bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        return Array.prototype.map.call(bytes, function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
    }

    function enviar(url, datos) {
        return fetch(url, {method: 'POST', body: datos, headers: {'X-CSRFToken': token}, credentials: 'same-origin'})
            .then(function (respuesta) {
                return respuesta.json().catch(function () { return {}; }).then(function (cuerpo) {
                    if (!respuesta.ok) {
                        var problema = new Error(cuerpo.error || ('El panel contestó ' + respuesta.status));
                        problema.definitivo = !!cuerpo.error;
                        throw problema;
                    }
                    return cuerpo;
                });
            });
    }

    function pedazo(id, archivo, desde, intento) {
        var datos = new FormData();
        datos.append('id', id);
        datos.append('desde', String(desde));
        datos.append('pedazo', archivo.slice(desde, desde + TAMANIO), 'pedazo');
        return enviar(form.dataset.pedazo, datos).catch(function (problema) {
            if (problema.definitivo || intento >= 3) throw problema;
            return new Promise(function (listo) { setTimeout(listo, 2000 * intento); })
                .then(function () { return pedazo(id, archivo, desde, intento + 1); });
        });
    }

    function subir(archivo) {
        var id = identificador();
        var desde = 0;
        function siguiente() {
            if (desde >= archivo.size) return Promise.resolve();
            return pedazo(id, archivo, desde, 1).then(function (respuesta) {
                desde = respuesta.recibido;
                var porcentaje = Math.min(99, Math.floor(100 * desde / archivo.size));
                mostrar(porcentaje, 'Subiendo… ' + mb(desde) + ' de ' + mb(archivo.size) + ' (' + porcentaje + ' %)');
                return siguiente();
            });
        }
        mostrar(0, 'Subiendo… 0 de ' + mb(archivo.size));
        return siguiente().then(function () {
            mostrar(99, 'Revisando el instalador y calculando su huella…');
            var datos = new FormData();
            datos.append('id', id);
            datos.append('version', version.value.trim());
            datos.append('notas', notas.value);
            return enviar(form.dataset.publicar, datos);
        });
    }

    campo.addEventListener('change', function () {
        var archivo = campo.files[0];
        if (!archivo) return;
        var patron = new RegExp(prefijo + '-(\\d+(?:\\.\\d+){1,3})(?: \\(\\d+\\))?\\.exe$', 'i');
        var encontrada = patron.exec(archivo.name);
        if (encontrada) version.value = encontrada[1];
        subida.hidden = true;
    });

    form.addEventListener('submit', function (evento) {
        evento.preventDefault();
        if (subiendo) return;
        var archivo = campo.files[0];
        if (!archivo) {
            mostrar(0, 'Elegí el instalador (' + prefijo + '-….exe).', true);
            return;
        }
        if (!/\.exe$/i.test(archivo.name)) {
            mostrar(0, 'Tiene que ser el instalador .exe (' + prefijo + '-….exe).', true);
            return;
        }
        if (!version.value.trim()) {
            mostrar(0, 'Falta la versión: es la del nombre del archivo (ej: 2026.11.9.1530).', true);
            version.focus();
            return;
        }
        subiendo = true;
        boton.disabled = true;
        subir(archivo).then(function (respuesta) {
            mostrar(100, 'Listo: publicado.');
            subiendo = false;
            window.location.href = respuesta.url;
        }).catch(function (problema) {
            mostrar(0, problema.message || 'Se cortó la conexión. Volvé a intentarlo.', true);
        }).then(function () {
            subiendo = false;
            boton.disabled = false;
        });
    });

    // Salir de la página corta la subida: se avisa
    window.addEventListener('beforeunload', function (e) {
        if (!subiendo) return;
        e.preventDefault();
        e.returnValue = '';
    });
    }
})();
