/*
 * Kairos TV · las imágenes de Contenido (logos y pósters) sin salir del panel. Lo usan Organizar
 * (organizar_trabajo.js) y la página de una serie (portada y capítulos).
 *
 *   KairosImagenes.trae(transferencia)        -> si lo que se arrastra puede ser una imagen
 *   KairosImagenes.leer(transferencia)        -> Promise de {archivo: File} | {url: 'https://...'} | null:
 *                                                lo que se arrastró desde otra ventana o se pegó con Ctrl+V.
 *                                                Entiende archivos, imágenes de páginas, links y los
 *                                                resultados de Google Imágenes (se queda con la imagen grande)
 *   KairosImagenes.pintar(caja, opciones)     -> la tira de sugerencias para elegir con un clic:
 *        {nombre, contenido, canal, urlPanel, alElegir(url)}
 *        Primero las que ya tienen otras cosas con ese nombre en el panel (otras listas importadas, otros
 *        canales: /canales/organizar/imagenes/) y después las de Wikipedia. Al final, "Buscar en Google".
 *
 * Las imágenes que se eligen quedan como link (igual que si se pegara); las que se arrastran o pegan como
 * archivo se suben (el servidor las achica: canales/imagenes.py).
 */
(function () {
    'use strict';

    var TIPOS = /^image\/(jpeg|png|webp|gif)$/;
    var ESPERA_MS = 8000;

    function trae(transferencia) {
        if (!transferencia) return false;
        var tipos = Array.prototype.slice.call(transferencia.types || []);
        return tipos.indexOf('Files') >= 0 || tipos.indexOf('text/uri-list') >= 0 || tipos.indexOf('text/html') >= 0;
    }

    /** Un resultado de Google Imágenes es "https://www.google.com/imgres?imgurl=<la imagen>&...": la imagen. */
    function sinGoogle(url) {
        try {
            var direccion = new URL(url);
            if (/(^|\.)google\./.test(direccion.hostname) && direccion.searchParams.get('imgurl')) {
                return direccion.searchParams.get('imgurl');
            }
        } catch (e) { /* no era una dirección */ }
        return url;
    }

    /** "data:image/png;base64,..." (lo que da Google para las miniaturas) -> un archivo para subir. */
    function aArchivo(datos) {
        return fetch(datos).then(function (respuesta) { return respuesta.blob(); }).then(function (blob) {
            if (!TIPOS.test(blob.type)) return null;
            return {archivo: new File([blob], 'imagen.' + blob.type.split('/')[1], {type: blob.type})};
        }, function () { return null; });
    }

    function deTexto(texto) {
        texto = (texto || '').trim();
        if (/^data:image\//.test(texto)) return aArchivo(texto);
        var linea = texto.split(/\s+/).filter(function (parte) { return /^https?:\/\//i.test(parte); })[0];
        return Promise.resolve(linea ? {url: sinGoogle(linea)} : null);
    }

    function leer(transferencia) {
        if (!transferencia) return Promise.resolve(null);
        var archivo = Array.prototype.filter.call(transferencia.files || [], function (f) { return TIPOS.test(f.type); })[0];
        if (archivo) return Promise.resolve({archivo: archivo});
        var lista = transferencia.getData ? (transferencia.getData('text/uri-list') || '') : '';
        // De Google Imágenes: el link trae la imagen grande (la de la página es una miniatura)
        if (/google\.[^/]+\/imgres\?/.test(lista)) return deTexto(lista);
        var html = transferencia.getData ? transferencia.getData('text/html') : '';
        if (html) {
            var imagen = new DOMParser().parseFromString(html, 'text/html').querySelector('img[src]');
            if (imagen) return deTexto(imagen.getAttribute('src'));
        }
        return deTexto(lista || (transferencia.getData ? transferencia.getData('text/plain') : ''));
    }

    function conEspera(url, opciones) {
        var control = window.AbortController ? new AbortController() : null;
        var reloj = control ? window.setTimeout(function () { control.abort(); }, ESPERA_MS) : null;
        return fetch(url, Object.assign({}, opciones || {}, control ? {signal: control.signal} : {}))
            .then(function (respuesta) {
                window.clearTimeout(reloj);
                if (!respuesta.ok) throw new Error('HTTP ' + respuesta.status);
                return respuesta.json();
            });
    }

    /** Las imágenes principales de los artículos de Wikipedia que encuentra con ese texto. */
    function wikipedia(idioma, texto) {
        var parametros = new URLSearchParams({
            action: 'query', format: 'json', origin: '*', generator: 'search', gsrsearch: texto, gsrlimit: '6',
            prop: 'pageimages', piprop: 'thumbnail', pithumbsize: '500', pilicense: 'any'
        });
        return conEspera('https://' + idioma + '.wikipedia.org/w/api.php?' + parametros).then(function (r) {
            var paginas = r.query && r.query.pages ? Object.keys(r.query.pages).map(function (k) { return r.query.pages[k]; }) : [];
            paginas.sort(function (a, b) { return (a.index || 0) - (b.index || 0); });
            return paginas.filter(function (p) { return p.thumbnail && p.thumbnail.source; })
                .map(function (p) { return {url: p.thumbnail.source, de: 'Wikipedia: ' + p.title}; });
        });
    }

    function sugerir(opciones, alLlegar) {
        var vistas = {};
        function sumar(lista) {
            var nuevas = (lista || []).filter(function (i) {
                if (!i.url || vistas[i.url]) return false;
                vistas[i.url] = true;
                return true;
            });
            if (nuevas.length) alLlegar(nuevas);
        }
        var pedidos = [];
        if (opciones.urlPanel) {
            var parametros = new URLSearchParams({nombre: opciones.nombre, contenido: opciones.contenido || '', canal: opciones.canal || ''});
            pedidos.push(conEspera(opciones.urlPanel + '?' + parametros, {credentials: 'same-origin', headers: {Accept: 'application/json'}})
                .then(function (r) { sumar(r.imagenes); }, function () {}));
        }
        var en = {pelicula: ' película', serie: ' serie de televisión'}[opciones.contenido] || '';
        var enIngles = {pelicula: ' film', serie: ' TV series'}[opciones.contenido] || '';
        pedidos.push(wikipedia('es', opciones.nombre + en).then(sumar, function () {}));
        pedidos.push(wikipedia('en', opciones.nombre + enIngles).then(sumar, function () {}));
        return Promise.all(pedidos);
    }

    function crear(etiqueta, clase, texto) {
        var elemento = document.createElement(etiqueta);
        if (clase) elemento.className = clase;
        if (texto) elemento.textContent = texto;
        return elemento;
    }

    function pintar(caja, opciones) {
        caja.hidden = false;
        caja.textContent = '';
        var pedido = (caja._pedido || 0) + 1;
        caja._pedido = pedido;
        var estado = crear('p', 'sugerencias-estado', 'Buscando imágenes con «' + opciones.nombre + '»…');
        var grilla = crear('div', 'sugerencias-grilla' + (opciones.poster ? ' con-poster' : ''));
        var pie = crear('p', 'sugerencias-pie');
        var google = crear('a', '', 'Buscar en Google');
        google.href = 'https://www.google.com/search?tbm=isch&q=' + encodeURIComponent(opciones.nombre + (opciones.poster ? ' póster' : ' logo png'));
        google.target = '_blank';
        google.rel = 'noopener';
        pie.appendChild(google);
        pie.appendChild(document.createTextNode(' y arrastrá la que te guste hasta acá (o copiala y pegala con Ctrl+V).'));
        caja.appendChild(estado);
        caja.appendChild(grilla);
        caja.appendChild(pie);
        var cuantas = 0;
        sugerir(opciones, function (lista) {
            if (caja._pedido !== pedido) return;
            lista.forEach(function (s) {
                var boton = crear('button', 'sugerencia');
                boton.type = 'button';
                boton.title = s.de;
                var imagen = crear('img');
                imagen.alt = '';
                imagen.loading = 'lazy';
                imagen.referrerPolicy = 'no-referrer';
                imagen.src = s.url;
                imagen.addEventListener('error', function () { boton.remove(); });
                boton.appendChild(imagen);
                boton.appendChild(crear('span', 'sugerencia-de', s.de));
                boton.addEventListener('click', function () {
                    grilla.querySelectorAll('.elegida').forEach(function (b) { b.classList.remove('elegida'); });
                    boton.classList.add('elegida');
                    opciones.alElegir(s.url);
                });
                grilla.appendChild(boton);
                cuantas += 1;
            });
            estado.textContent = 'Tocá una para usarla:';
        }).then(function () {
            if (caja._pedido === pedido && !cuantas) estado.textContent = 'No encontré imágenes con ese nombre.';
        });
    }

    window.KairosImagenes = {trae: trae, leer: leer, pintar: pintar};
})();
