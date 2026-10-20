/*
 * Kairos TV · la página de una serie (canales/serie_detalle.html): lo que se cambia ahí mismo, sin recargar
 * (views_organizar.cambiar, con KairosTrabajo.pedir de trabajo.js):
 *   - La portada: tocarla abre sus herramientas (buscar imágenes con ese nombre, subir una, pegar un link,
 *     sacarla); también se le arrastra una imagen encima o se pega con Ctrl+V. Ver imagenes_contenido.js.
 *   - El nombre: tocarlo, escribir y Enter (renombra todos los capítulos; la página pasa a la serie renombrada).
 *   - La categoría: elegirla en la lista (o «＋ Una nueva…», escribirla y Enter).
 *   - La imagen de un capítulo: arrastrarle una encima.
 */
(function () {
    'use strict';

    var raiz = document.querySelector('[data-serie]');
    if (!raiz || !window.KairosTrabajo || !window.KairosImagenes) return;
    var config = raiz.dataset;
    var nombre = config.nombre;
    var avisar = window.KairosTrabajo.avisar;

    function cambiar(datos) {
        var envio = new FormData();
        Object.keys(datos).forEach(function (clave) { envio.append(clave, datos[clave]); });
        return window.KairosTrabajo.pedir(config.urlCambiar, envio);
    }
    function deLaSerie(campo, valor, extra) {
        return cambiar(Object.assign({tipo: 'serie', serie: nombre, campo: campo, valor: valor == null ? '' : valor}, extra || {}));
    }

    function iniciales(texto) {
        return (texto || '').split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) { return p[0]; }).join('').toUpperCase() || '?';
    }

    // ── La portada ──
    var portada = raiz.querySelector('[data-portada]');
    var herramientas = raiz.querySelector('[data-portada-herramientas]');
    var portadaPropia = !!config.portadaPropia;   // sin portada propia usa la imagen del primer capítulo
    var sugerencias = herramientas && herramientas.querySelector('[data-sugerencias]');

    function pintarPortada(url) {
        var cartel = portada.querySelector('.serie-portada-cambiar');
        portada.textContent = '';
        if (url) {
            var imagen = document.createElement('img');
            imagen.alt = '';
            imagen.referrerPolicy = 'no-referrer';
            imagen.src = url;
            portada.appendChild(imagen);
        } else {
            var letras = document.createElement('span');
            letras.textContent = iniciales(nombre);
            portada.appendChild(letras);
        }
        if (cartel) portada.appendChild(cartel);
    }

    function ponerPortada(imagen) {
        if (!imagen) {
            avisar('Eso no parece una imagen: arrastrá la imagen misma (o su link).', 'mal');
            return;
        }
        portada.classList.add('guardando');
        // «Deshacer» vuelve a como estaba: a la portada de antes, o a no tener una propia
        var anterior = portadaPropia ? ((portada.querySelector('img') || {}).src || '') : '';
        deLaSerie('logo', imagen.url || '', imagen.archivo ? {imagen: imagen.archivo} : null).then(function (r) {
            portada.classList.remove('guardando');
            portadaPropia = !!(r.datos && r.datos.portada);
            pintarPortada(r.datos ? r.datos.logo : imagen.url);
            avisar(r.mensaje, 'bien', function () {
                deLaSerie('logo', anterior).then(function (otra) {
                    portadaPropia = !!(otra.datos && otra.datos.portada);
                    pintarPortada(otra.datos ? otra.datos.logo : anterior);
                    avisar(otra.mensaje, 'bien');
                }, function (error) { avisar(error.message, 'mal'); });
            });
        }, function (error) {
            portada.classList.remove('guardando');
            avisar(error.message, 'mal');
        });
    }

    if (portada && herramientas) {
        var abrirHerramientas = function () {
            herramientas.hidden = !herramientas.hidden;
            if (!herramientas.hidden) herramientas.querySelector('[data-portada-buscar]').focus();
        };
        portada.addEventListener('click', abrirHerramientas);
        portada.addEventListener('keydown', function (evento) {
            if (evento.key === 'Enter' || evento.key === ' ') {
                evento.preventDefault();
                abrirHerramientas();
            }
        });
        herramientas.querySelector('[data-portada-cerrar]').addEventListener('click', function () { herramientas.hidden = true; });
        herramientas.querySelector('[data-portada-buscar]').addEventListener('click', function () {
            window.KairosImagenes.pintar(sugerencias, {
                nombre: nombre, contenido: 'serie', urlPanel: config.urlImagenes, poster: true,
                alElegir: function (url) { ponerPortada({url: url}); }
            });
        });
        var archivo = herramientas.querySelector('[data-portada-archivo]');
        archivo.addEventListener('change', function () {
            if (archivo.files[0]) ponerPortada({archivo: archivo.files[0]});
            archivo.value = '';
        });
        var link = herramientas.querySelector('[data-portada-link]');
        link.addEventListener('submit', function (evento) {
            evento.preventDefault();
            var url = link.querySelector('input').value.trim();
            if (url) ponerPortada({url: url});
        });
        var sacar = herramientas.querySelector('[data-portada-sacar]');
        if (sacar) sacar.addEventListener('click', function () { ponerPortada({url: ''}); });
        // Pegar una imagen con Ctrl+V: con las herramientas de la portada abiertas (o la portada elegida con el
        // teclado), y sin estar escribiendo en un campo (ahí se pega lo normal)
        document.addEventListener('paste', function (evento) {
            var activo = document.activeElement;
            if (activo && /^(INPUT|TEXTAREA)$/.test(activo.tagName)) return;
            if (herramientas.hidden && activo !== portada) return;
            var portapapeles = evento.clipboardData;
            if (!portapapeles) return;
            var conArchivo = Array.prototype.some.call(portapapeles.files || [], function (f) { return /^image\//.test(f.type); });
            var texto = (portapapeles.getData('text') || '').trim();
            if (!conArchivo && !/^(https?:\/\/|data:image\/)\S+$/i.test(texto)) return;
            evento.preventDefault();
            window.KairosImagenes.leer(portapapeles).then(ponerPortada);
        });
    }

    // ── Soltar una imagen arriba de la portada o de un capítulo ──
    var bajo = null;
    function marcar(destino) {
        if (bajo === destino) return;
        if (bajo) bajo.classList.remove('soltar-aca');
        bajo = destino;
        if (destino) destino.classList.add('soltar-aca');
    }
    document.addEventListener('dragover', function (evento) {
        if (!window.KairosImagenes.trae(evento.dataTransfer)) return;
        var destino = evento.target.closest('[data-portada], [data-capitulo-imagen]');
        evento.preventDefault();   // afuera no se suelta (si no, el navegador abriría la imagen)
        evento.dataTransfer.dropEffect = destino ? 'copy' : 'none';
        marcar(destino);
    });
    document.addEventListener('dragleave', function (evento) {
        if (bajo && !bajo.contains(evento.relatedTarget)) marcar(null);
    });
    document.addEventListener('drop', function (evento) {
        if (!window.KairosImagenes.trae(evento.dataTransfer)) return;
        evento.preventDefault();
        var destino = evento.target.closest('[data-portada], [data-capitulo-imagen]');
        marcar(null);
        if (!destino) return;
        window.KairosImagenes.leer(evento.dataTransfer).then(function (imagen) {
            if (destino.hasAttribute('data-portada')) {
                ponerPortada(imagen);
                return;
            }
            if (!imagen) {
                avisar('Eso no parece una imagen: arrastrá la imagen misma (o su link).', 'mal');
                return;
            }
            destino.classList.add('guardando');
            cambiar(Object.assign({tipo: 'canal', canal: destino.dataset.capituloImagen, campo: 'logo', valor: imagen.url || ''},
                                  imagen.archivo ? {imagen: imagen.archivo} : {})).then(function (r) {
                destino.classList.remove('guardando');
                destino.textContent = '';
                var foto = document.createElement('img');
                foto.alt = '';
                foto.referrerPolicy = 'no-referrer';
                foto.src = r.datos ? r.datos.logo : imagen.url;
                destino.appendChild(foto);
                avisar(r.mensaje, 'bien');
            }, function (error) {
                destino.classList.remove('guardando');
                avisar(error.message, 'mal');
            });
        });
    });

    // ── El nombre de la serie, ahí mismo ──
    var titulo = raiz.querySelector('[data-serie-nombre]');
    if (titulo) {
        var editar = function () {
            if (titulo.querySelector('input')) return;
            var campo = document.createElement('input');
            campo.type = 'text';
            campo.className = 'form-control titulo-editando';
            campo.maxLength = 90;
            campo.value = nombre;
            campo.setAttribute('aria-label', 'Nombre nuevo de la serie (Enter guarda, Esc cancela)');
            titulo.textContent = '';
            titulo.appendChild(campo);
            campo.focus();
            campo.select();
            var listo = false;
            var terminar = function (guardar) {
                if (listo) return;
                listo = true;
                var nuevo = campo.value.trim().replace(/\s+/g, ' ');
                if (!guardar || !nuevo || nuevo === nombre) {
                    titulo.textContent = nombre;
                    return;
                }
                campo.disabled = true;
                deLaSerie('nombre', nuevo).then(function (r) {
                    // La página es de la serie con su nombre: se pasa a la renombrada
                    window.location.href = config.urlSerie + '?nombre=' + encodeURIComponent(r.datos ? r.datos.nombre : nuevo);
                }, function (error) {
                    titulo.textContent = nombre;
                    avisar(error.message, 'mal');
                });
            };
            campo.addEventListener('keydown', function (evento) {
                if (evento.key === 'Enter') {
                    evento.preventDefault();
                    terminar(true);
                } else if (evento.key === 'Escape') {
                    evento.preventDefault();
                    terminar(false);
                }
            });
            campo.addEventListener('blur', function () { terminar(true); });
        };
        titulo.addEventListener('click', editar);
        titulo.addEventListener('keydown', function (evento) {
            if ((evento.key === 'Enter' || evento.key === 'F2') && evento.target === titulo) {
                evento.preventDefault();
                editar();
            }
        });
    }

    // ── La categoría ──
    var categoria = raiz.querySelector('[data-serie-categoria]');
    if (categoria) {
        var nueva = raiz.querySelector('[data-serie-categoria-nueva]');
        var nombreCategoria = raiz.querySelector('[data-serie-categoria-nombre]');
        var anterior = categoria.value;
        var mostrar = function (r) {
            if (r.datos && nombreCategoria) {
                nombreCategoria.textContent = r.datos.categoria_nombre || 'Sin categoría';
                nombreCategoria.href = nombreCategoria.href.replace(/categoria=[^&]*/, 'categoria=' + r.datos.categoria);
            }
            avisar(r.mensaje, 'bien');
        };
        categoria.addEventListener('change', function () {
            if (categoria.value === '+nueva') {
                nueva.hidden = false;
                nueva.focus();
                return;
            }
            nueva.hidden = true;
            deLaSerie('categoria', categoria.value).then(function (r) {
                anterior = categoria.value;
                mostrar(r);
            }, function (error) {
                categoria.value = anterior;
                avisar(error.message, 'mal');
            });
        });
        nueva.addEventListener('keydown', function (evento) {
            if (evento.key === 'Escape') {
                nueva.hidden = true;
                categoria.value = anterior;
                return;
            }
            if (evento.key !== 'Enter') return;
            evento.preventDefault();
            var texto = nueva.value.trim();
            if (!texto) return;
            deLaSerie('categoria', '', {nueva: texto}).then(function (r) {
                var opcion = document.createElement('option');
                opcion.value = r.datos ? r.datos.categoria : '';
                opcion.textContent = r.datos ? r.datos.categoria_nombre : texto;
                categoria.insertBefore(opcion, categoria.querySelector('option[value="ninguna"]'));
                categoria.value = opcion.value;
                anterior = opcion.value;
                nueva.hidden = true;
                nueva.value = '';
                mostrar(r);
            }, function (error) { avisar(error.message, 'mal'); });
        });
    }
})();
