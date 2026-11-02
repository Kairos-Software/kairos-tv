/*
 * Kairos TV · Organizar contenido para trabajar rápido (canales/organizar.html). Estilos: css/organizar_trabajo.css.
 *
 *   - Tocar una tarjeta abre el PANEL DE EDICIÓN al costado (#editor), el ÚNICO lugar donde se edita un canal:
 *     nombre, imagen (buscar, subir, pegar o arrastrar), categoría, sección, número, si se muestra (y por qué
 *     no), destacado, sus señales (su número = su orden, si la app usa ese orden, y «Agregar una fuente»: varias,
 *     con su número) y «Datos» (idioma, país, orden en la categoría; lo demás, para leer). «Guardar» guarda
 *     SIN recargar (la tarjeta se redibuja con lo que contesta views_organizar.tarjeta_json); «Siguiente» y
 *     «Anterior» pasan a la vecina guardando antes lo que cambió (Ctrl+Enter = guardar y seguir). Al terminar la
 *     página sigue en la próxima (?abrir=primera). Esc cierra.
 *   - Desde otras pantallas (Señales, Lo más visto, una serie...) se llega con ?canal=<id>&abrir=c<id> (lo arma
 *     views.canal_editar): Organizar muestra ese solo, con el panel abierto y «Volver».
 *   - Vista Lista: el nombre se cambia ahí mismo (Enter guarda, Tab pasa al siguiente, Esc cancela), la
 *     categoría con su botón (con buscador; también crea una nueva) y ★ / «se muestra» con un toque.
 *   - Arrastrar una imagen (un archivo, una imagen de otra página o un resultado de Google Imágenes) arriba de
 *     una tarjeta se la pone en el momento (con «Deshacer»). Ver imagenes_contenido.js.
 *   - Las casillas eligen tarjetas para la barra de abajo (Shift = todas las del medio). «Cambiar nombres»
 *     muestra cómo quedan antes de aplicarlo (views_organizar.renombrar).
 *   - Además: juntar categorías, buscar una categoría, crear una sección y el cuadro Exportar.
 */
(function () {
    'use strict';

    var editor = document.getElementById('editor');
    var config = editor ? editor.dataset : {};
    var puedeEditar = !!config.puedeEditar;
    var esPoster = config.forma && config.forma !== 'vivo';
    var formOrganizar = document.getElementById('form-organizar');
    var form = document.getElementById('form-editor');
    var selector = document.getElementById('selector-categoria');

    // ── Herramientas (pedir y avisar: las comparte trabajo.js) ───────────────
    var pedir = window.KairosTrabajo.pedir;
    var avisar = window.KairosTrabajo.avisar;

    function crear(etiqueta, clase, texto) {
        var elemento = document.createElement(etiqueta);
        if (clase) elemento.className = clase;
        if (texto) elemento.textContent = texto;
        return elemento;
    }

    function normalizar(texto) {
        return (texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    }

    /** Si está abierta la burbuja de ayuda de un «?» (trabajo.js). */
    function ayudaAbierta() {
        var burbuja = document.getElementById('ayuda-flotante');
        if (!burbuja) return false;
        try { return burbuja.matches(':popover-open'); } catch (e) { return burbuja.classList.contains('abierta'); }
    }

    /** La dirección de esta misma página con `parametro` (abrir/ir) apuntando a una tarjeta. */
    function aca(parametro, clave) {
        var url = new URL(window.location.href);
        url.searchParams.delete('ir');
        url.searchParams.delete('abrir');
        if (clave) url.searchParams.set(parametro, clave);
        return url.pathname + url.search;
    }

    // ── Las tarjetas ─────────────────────────────────────────────────────────
    function tarjetas() { return Array.prototype.slice.call(document.querySelectorAll('.espejo-tarjeta')); }
    function datosDe(tarjeta) {
        try { return JSON.parse(tarjeta.dataset.datos); } catch (e) { return null; }
    }
    function claveDe(datos) { return datos.tipo === 'serie' ? 's:' + datos.nombre : 'c' + datos.pk; }
    function porClave(clave) {
        return tarjetas().filter(function (t) { return t.dataset.clave === clave; })[0] || null;
    }
    function vecina(tarjeta, paso) {
        var lista = tarjetas();
        return lista[lista.indexOf(tarjeta) + paso] || null;
    }
    function enLista() { return document.documentElement.classList.contains('vista-lista'); }

    /** Si cambió de categoría mientras se mira una sola: queda marcada (al recargar ya no aparece acá). */
    function marcarSiSeFue(tarjeta) {
        var vista = config.categoriaVista;
        var datos = datosDe(tarjeta);
        if (!datos || !vista || vista === 'todas' || String(datos.categoria) === vista) return;
        tarjeta.classList.add('se-fue');
        tarjeta.setAttribute('data-se-fue', 'Pasó a «' + (datos.categoria_nombre || 'Sin categoría') + '»');
    }

    /** Pone la tarjeta que mandó el servidor en lugar de la vieja (mantiene si estaba elegida o abierta). */
    function reemplazar(tarjeta, html) {
        if (!html) {
            tarjeta.classList.add('se-fue');
            return tarjeta;
        }
        var molde = document.createElement('template');
        molde.innerHTML = html.trim();
        var nueva = molde.content.firstElementChild;
        var casilla = tarjeta.querySelector('.canal-elegir');
        var casillaNueva = nueva.querySelector('.canal-elegir');
        if (casilla && casillaNueva) casillaNueva.checked = casilla.checked;
        if (tarjeta.classList.contains('abierta')) nueva.classList.add('abierta');
        tarjeta.replaceWith(nueva);
        if (actual === tarjeta) actual = nueva;
        if (selectorTarjeta === tarjeta) selectorTarjeta = nueva;
        nueva.classList.add('recien-editada');
        marcarSiSeFue(nueva);
        actualizarBarra();
        return nueva;
    }

    /**
     * Cambia UN dato de una tarjeta en el servidor (views_organizar.cambiar) y la redibuja.
     * opciones.deshacer(nueva): lo que hace «Deshacer» en el aviso.
     */
    function cambiar(tarjeta, campo, valor, extra, opciones) {
        var datos = datosDe(tarjeta);
        var envio = new FormData();
        envio.append('tipo', datos.tipo);
        envio.append(datos.tipo === 'serie' ? 'serie' : 'canal', datos.tipo === 'serie' ? datos.nombre : datos.pk);
        envio.append('campo', campo);
        envio.append('valor', valor == null ? '' : valor);
        Object.keys(extra || {}).forEach(function (clave) { envio.append(clave, extra[clave]); });
        tarjeta.classList.add('guardando');
        return pedir(config.urlCambiar, envio).then(function (r) {
            var nueva = reemplazar(tarjeta, r.tarjeta);
            nueva.classList.remove('guardando');
            if (actual === nueva && r.datos && !sucio()) llenar(r.datos, true);
            var deshacer = opciones && opciones.deshacer;
            avisar(r.mensaje, 'bien', deshacer ? function () { deshacer(nueva); } : null);
            return nueva;
        }, function (error) {
            tarjeta.classList.remove('guardando');
            avisar(error.message, 'mal');
            throw error;
        });
    }

    // ── El panel de edición ──────────────────────────────────────────────────
    var actual = null;      // la tarjeta abierta
    var datosActuales = null;
    var foto = null;        // cómo estaba el formulario al abrirla (para saber si cambió algo)
    var archivo = null;     // una imagen pegada o arrastrada, todavía sin guardar
    var urlVista = '';
    var vista = editor && editor.querySelector('[data-editor-vista]');
    var campos = form && form.elements.nombre ? form.elements : null;   // sin permiso de editar no hay campos
    var campoArchivo = editor && editor.querySelector('[data-imagen-archivo]');
    var sugerencias = editor && editor.querySelector('[data-sugerencias]');
    var nuevaCategoria = editor && editor.querySelector('[data-editor-nueva]');
    // Lo que en «Datos» ya se cambia arriba: no se repite en la lista de abajo
    var YA_SE_EDITAN = {'Categoría': true, 'Idioma': true, 'País': true, 'Por qué se quitó': true};

    /** «Por qué no se muestra»: solo cuando no se muestra en la app (un canal). */
    function mostrarMotivo() {
        var motivo = editor.querySelector('[data-editor-motivo]');
        motivo.hidden = campos.activo.checked || (datosActuales && datosActuales.tipo === 'serie');
    }

    // ── Agregar fuentes (un canal): filas con número y dirección; se guardan con «Guardar» ──
    var filasNuevas = editor && editor.querySelector('[data-filas-nuevas]');
    var moldeFila = editor && editor.querySelector('[data-fila-nueva]');
    var otraFuente = editor && editor.querySelector('[data-otra-fuente]');
    var totalNuevas = document.getElementById('id_nuevas-TOTAL_FORMS');
    var maximoNuevas = totalNuevas ? parseInt(document.getElementById('id_nuevas-MAX_NUM_FORMS').value, 10) : 0;

    function filasVisibles() {
        return Array.prototype.filter.call(filasNuevas.children, function (fila) { return !fila.hidden; });
    }
    /** Sin número va al final (después de las que lo tienen): el lugar vacío muestra el número que le toca. */
    function numerarFilasNuevas() {
        if (!filasNuevas) return;
        var siguiente = (datosActuales ? datosActuales.fuentes.length : 0) + 1;
        var conDireccion = [], sinDireccion = [];
        filasVisibles().forEach(function (fila) {
            var numero = fila.querySelector('input[name$="-numero"]');
            var direccion = fila.querySelector('input[name$="-url"]').value.trim();
            if (numero.value) {
                numero.placeholder = '';
                if (direccion) siguiente++;
            } else {
                (direccion ? conDireccion : sinDireccion).push(numero);
            }
        });
        conDireccion.concat(sinDireccion).forEach(function (numero) { numero.placeholder = siguiente++; });
        editor.querySelector('[data-ayuda-nuevas]').hidden = !filasVisibles().length;
        otraFuente.hidden = parseInt(totalNuevas.value, 10) >= maximoNuevas;
    }
    function vaciarFilasNuevas() {
        if (!filasNuevas) return;
        filasNuevas.textContent = '';
        totalNuevas.value = 0;
        numerarFilasNuevas();
    }
    function agregarFilaNueva() {
        var numeroFila = parseInt(totalNuevas.value, 10);
        filasNuevas.insertAdjacentHTML('beforeend', moldeFila.innerHTML.replace(/__prefix__/g, numeroFila));
        totalNuevas.value = numeroFila + 1;
        numerarFilasNuevas();
        filasNuevas.lastElementChild.querySelector('input[name$="-url"]').focus();
    }
    function hayFuentesNuevas() {
        return !!filasNuevas && filasVisibles().some(function (fila) { return fila.querySelector('input[name$="-url"]').value.trim(); });
    }

    function iniciales(texto) {
        return (texto || '').split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) { return p[0]; }).join('').toUpperCase() || '?';
    }

    function mostrarAviso(texto, tipo) {
        var aviso = editor.querySelector('[data-editor-aviso]');
        aviso.textContent = texto || '';
        aviso.className = 'editor-aviso' + (tipo ? ' aviso-' + tipo : '');
    }

    function pintarVista() {
        if (!vista || !datosActuales) return;
        vista.textContent = '';
        if (urlVista) URL.revokeObjectURL(urlVista);
        urlVista = archivo ? URL.createObjectURL(archivo) : '';
        var fuente = urlVista || (campos ? campos.logo.value.trim() : (datosActuales.logo_ver || datosActuales.logo || ''));
        vista.classList.toggle('poster', esPoster || datosActuales.tipo === 'serie');
        if (fuente) {
            var imagen = crear('img');
            imagen.alt = '';
            imagen.referrerPolicy = 'no-referrer';
            imagen.src = fuente;
            vista.appendChild(imagen);
        } else {
            vista.textContent = iniciales(campos ? campos.nombre.value : datosActuales.nombre);
        }
    }

    /** Todo lo que manda «Guardar» (también los números de las señales y las fuentes nuevas), para saber si cambió algo. */
    function estadoDelFormulario() {
        if (!campos) return '';
        var partes = [];
        new FormData(form).forEach(function (valor, nombre) {
            if (typeof valor !== 'string' || nombre === 'csrfmiddlewaretoken') return;
            // Una fila de fuente nueva vacía (o cuántas filas hay) no es un cambio
            if (/^nuevas-/.test(nombre) && (valor === '' || /^nuevas-[A-Z_]+$/.test(nombre))) return;
            partes.push(nombre + '=' + valor);
        });
        return partes.join('&') + (archivo ? '&archivo=' + archivo.name + archivo.size : '');
    }
    function sucio() { return !!actual && !!campos && foto !== null && estadoDelFormulario() !== foto; }
    // Los botones de cada señal recargan la página: preguntan antes si hay cambios sin guardar (organizar_detalle.js)
    window.KairosEditor = {sucio: sucio};

    function actualizarBotones() {
        if (!editor || !actual) return;
        var lista = tarjetas();
        var posicion = lista.indexOf(actual);
        var siguiente = editor.querySelector('[data-editor-siguiente]');
        siguiente.querySelector('span').textContent = sucio() ? 'Guardar y seguir' : 'Siguiente';
        siguiente.disabled = (posicion < 0 || posicion >= lista.length - 1) && !config.paginaSiguiente;
        editor.querySelector('[data-editor-anterior]').disabled = posicion <= 0 && !config.paginaAnterior;
        editor.querySelector('[data-editor-posicion]').textContent = posicion >= 0 ? (posicion + 1) + ' de ' + lista.length + ' en esta página' : '';
    }

    function llenar(datos, recienGuardado) {
        datosActuales = datos;
        var esSerie = datos.tipo === 'serie';
        editor.querySelector('[data-editor-nombre]').textContent = (datos.destacado ? '★ ' : '') + datos.nombre;
        var estado = editor.querySelector('[data-editor-estado]');
        estado.textContent = datos.en_app ? 'Se ve en la app.' : 'No se ve en la app: ' + (datos.motivo || '');
        estado.className = 'editor-estado ' + (datos.en_app ? 'estado-bien' : 'estado-mal');
        if (campos) {
            campos.tipo.value = datos.tipo;
            campos.canal.value = esSerie ? '' : datos.pk;
            campos.serie.value = esSerie ? datos.nombre : '';
            campos.nombre.value = datos.nombre;
            campos.nombre.maxLength = esSerie ? 90 : 120;
            campos.logo.value = datos.logo || '';
            if (campos.numero) campos.numero.value = datos.numero || '';
            campos.categoria.value = String(datos.categoria);
            if (campos.categoria.value !== String(datos.categoria)) campos.categoria.value = 'ninguna';
            campos.categoria.classList.remove('categoria-anulada');
            campos.nueva_categoria.value = '';
            nuevaCategoria.hidden = true;
            if (campos.contenido) campos.contenido.value = datos.contenido;
            campos.activo.checked = !!datos.activo;
            campos.destacado.checked = !!datos.destacado;
            // Lo de un canal que antes estaba en «Más opciones»: «Datos», por qué no se muestra y sus señales
            campos.completo.value = esSerie ? '' : '1';
            editor.querySelectorAll('[data-solo-canal]').forEach(function (parte) { parte.hidden = esSerie; });
            campos.idioma.value = datos.idioma || '';
            campos.pais.value = datos.pais || '';
            campos.orden.value = datos.orden == null ? '' : datos.orden;
            campos.motivo_quitado.value = datos.motivo_quitado || '';
            mostrarMotivo();
            campos.orden_fuentes_a_mano.checked = !!datos.orden_a_mano;
            vaciarFilasNuevas();
            archivo = null;
            if (campoArchivo) campoArchivo.value = '';
            editor.querySelector('[data-editor-imagen-titulo]').textContent = esSerie ? 'Portada de la serie' : (esPoster ? 'Póster' : 'Logo');
            editor.querySelector('[data-editor-imagen-ayuda]').textContent = !esSerie ? '' : datos.portada
                ? 'Es la portada propia de la serie. «Sacar» vuelve a usar la imagen del primer capítulo.'
                : 'Ahora usa la imagen del primer capítulo. La que pongas queda como portada de la serie (cada capítulo conserva la suya).';
            if (!recienGuardado) {
                sugerencias.hidden = true;
                sugerencias.textContent = '';
            }
        }
        pintarVista();

        var bloque = editor.querySelector('[data-editor-bloque-senales]');
        editor.querySelector('[data-editor-cuantas]').textContent = datos.fuentes.length;
        editor.querySelector('[data-editor-senales-ayuda]').textContent = esSerie
            ? 'Una por cada lista o canal de donde salieron sus capítulos. Las de cada capítulo, en «Capítulos y temporadas».'
            : puedeEditar
                ? 'Para cambiar el orden, cambiá el número: la señal va a ese lugar y las demás se corren. Si una no anda, quitala (la podés volver a mostrar) o borrala.'
                : 'La app prueba la 1 y, si no anda, pasa a la siguiente.';
        window.KairosSenales.pintar(editor.querySelector('[data-editor-senales]'), datos);
        var conProblemas = datos.fuentes.some(function (f) { return f.caida || f.oculta || !f.activa || f.salud_mal; });
        if (!recienGuardado) bloque.open = !puedeEditar || !datos.en_app || conProblemas;

        var filas = editor.querySelector('[data-editor-datos]');
        filas.textContent = '';
        (datos.datos || []).forEach(function (fila) {
            if (campos && !esSerie && YA_SE_EDITAN[fila[0]]) return;   // están arriba, para cambiarlos
            filas.appendChild(crear('dt', '', fila[0]));
            filas.appendChild(crear('dd', '', fila[1]));
        });

        // Una serie tiene su página (capítulos y temporadas); un canal se edita entero acá
        var mas = editor.querySelector('[data-editor-mas]');
        mas.hidden = !esSerie;
        if (esSerie) mas.href = datos.mas;
        var enSenales = editor.querySelector('[data-editor-senales-link]');
        enSenales.hidden = esSerie;
        if (!esSerie) enSenales.href = enSenales.dataset.base + '?problema=cualquiera&canal=' + datos.pk;
        foto = estadoDelFormulario();
        if (!recienGuardado) mostrarAviso('');
        actualizarBotones();
    }

    function abrir(tarjeta, opciones) {
        var datos = datosDe(tarjeta);
        if (!datos || !editor) return;
        if (actual && actual !== tarjeta) actual.classList.remove('abierta');
        actual = tarjeta;
        tarjeta.classList.add('abierta');
        llenar(datos);
        editor.hidden = false;
        document.body.classList.add('con-editor');
        editor.querySelector('.editor-cuerpo').scrollTop = 0;
        window.requestAnimationFrame(function () { tarjeta.scrollIntoView({block: 'nearest'}); });
        if (opciones && opciones.foco && campos && window.matchMedia('(pointer: fine)').matches) {
            campos.nombre.focus({preventScroll: true});
        }
    }

    function cerrar() {
        if (!editor || editor.hidden) return;
        if (sucio() && !window.confirm('Hay cambios sin guardar en «' + datosActuales.nombre + '». ¿Cerrar igual? (se pierden)')) return;
        editor.hidden = true;
        document.body.classList.remove('con-editor');
        if (actual) {
            actual.classList.remove('abierta');
            actual.focus({preventScroll: true});
        }
        actual = null;
        foto = null;
        archivo = null;
    }

    function guardando(si) {
        var boton = editor.querySelector('[data-editor-guardar]');
        if (boton) boton.disabled = si;
        editor.classList.toggle('guardando', si);
        if (si) mostrarAviso('Guardando…');
    }

    /** Guarda lo que cambió (sin recargar). Promise: true si guardó, false si no había cambios. */
    function guardar() {
        if (!actual || !campos || !sucio()) return Promise.resolve(false);
        if (campos.categoria.value === '+nueva' && !campos.nueva_categoria.value.trim()) {
            mostrarAviso('Escribí el nombre de la categoría nueva.', 'mal');
            nuevaCategoria.focus();
            return Promise.reject(new Error('Falta la categoría nueva'));
        }
        var datos = new FormData(form);
        if (archivo) datos.set('imagen', archivo);
        else datos.delete('imagen');
        var tarjeta = actual;
        guardando(true);
        if (hayFuentesNuevas()) mostrarAviso('Guardando y probando las fuentes nuevas (puede tardar unos segundos)…');
        return pedir(form.action, datos).then(function (r) {
            guardando(false);
            var nueva = reemplazar(tarjeta, r.tarjeta);
            if (actual === nueva && r.datos) llenar(r.datos, true);
            mostrarAviso('Guardado ✓', 'bien');
            avisar(r.mensaje, 'bien');
            return true;
        }, function (error) {
            guardando(false);
            mostrarAviso(error.message, 'mal');
            throw error;
        });
    }

    /** Pasa a la tarjeta de al lado (guardando antes lo que cambió); al terminar la página, a la próxima. */
    function ir(paso) {
        if (!actual) return;
        guardar().then(function () {
            var otra = vecina(actual, paso);
            if (otra) {
                abrir(otra, {foco: true});
                return;
            }
            var pagina = paso > 0 ? config.paginaSiguiente : config.paginaAnterior;
            if (pagina) window.location.href = pagina + '&abrir=' + (paso > 0 ? 'primera' : 'ultima');
            else mostrarAviso(paso > 0 ? 'Era la última.' : 'Era la primera.');
        }, function () {});
    }

    function abrirDesdeTarjeta(tarjeta) {
        if (actual === tarjeta && !editor.hidden) return;
        if (sucio()) guardar().then(function () { abrir(tarjeta); }, function () {});
        else abrir(tarjeta);
    }

    /** Una imagen arrastrada o pegada en el panel: queda puesta (se guarda con «Guardar»). */
    function ponerEnEditor(imagen) {
        if (!campos || !imagen) return;
        if (imagen.archivo) {
            archivo = imagen.archivo;
        } else {
            archivo = null;
            campos.logo.value = imagen.url;
        }
        if (campoArchivo) campoArchivo.value = '';
        pintarVista();
        actualizarBotones();
        mostrarAviso('Imagen puesta: tocá «Guardar» (o «Guardar y seguir»).', 'info');
    }

    if (editor && form) {
        form.addEventListener('submit', function (evento) {
            evento.preventDefault();
            guardar().then(function (hubo) { if (!hubo) mostrarAviso('No hay cambios para guardar.'); }, function () {});
        });
        form.addEventListener('input', actualizarBotones);
        form.addEventListener('change', actualizarBotones);
        editor.querySelector('[data-editor-anterior]').addEventListener('click', function () { ir(-1); });
        editor.querySelector('[data-editor-siguiente]').addEventListener('click', function () { ir(1); });
        editor.querySelector('[data-editor-cerrar]').addEventListener('click', cerrar);
        editor.addEventListener('keydown', function (evento) {
            if ((evento.ctrlKey || evento.metaKey) && evento.key === 'Enter') {
                evento.preventDefault();
                ir(1);
            }
        });
        document.addEventListener('keydown', function (evento) {
            if (evento.key !== 'Escape' || editor.hidden || document.querySelector('dialog[open]')) return;
            if (selector && !selector.hidden) return;
            if (ayudaAbierta()) return;   // Esc cierra primero la burbuja de ayuda (trabajo.js)
            cerrar();
        });

        if (campos) {
            campos.categoria.addEventListener('change', function () {
                nuevaCategoria.hidden = campos.categoria.value !== '+nueva';
                if (!nuevaCategoria.hidden) nuevaCategoria.focus();
            });
            campos.activo.addEventListener('change', mostrarMotivo);
            otraFuente.addEventListener('click', function () {
                agregarFilaNueva();
                actualizarBotones();
            });
            // La ✕ de una fila nueva: se vacía y se va (no se manda nada de ella)
            filasNuevas.addEventListener('click', function (evento) {
                var quitar = evento.target.closest('[data-quitar-fila]');
                if (!quitar) return;
                var fila = quitar.closest('.fuente-nueva');
                fila.querySelectorAll('input').forEach(function (campo) {
                    if (campo.type === 'checkbox') campo.checked = false;
                    else campo.value = '';
                });
                fila.hidden = true;
                numerarFilasNuevas();
                actualizarBotones();
            });
            // Elegir un número (de una señal o de una fuente nueva) = la app usa este orden
            form.addEventListener('input', function (evento) {
                var nombre = evento.target.name || '';
                if (/^nuevas-\d+-url$/.test(nombre)) numerarFilasNuevas();
                if (!/^(numero-\d+|nuevas-\d+-numero)$/.test(nombre)) return;
                if (evento.target.value) campos.orden_fuentes_a_mano.checked = true;
                numerarFilasNuevas();
                actualizarBotones();
            });
            campos.logo.addEventListener('input', function () {
                archivo = null;
                pintarVista();
            });
            campos.nombre.addEventListener('input', function () { if (!campos.logo.value && !archivo) pintarVista(); });
            campoArchivo.addEventListener('change', function () {
                archivo = campoArchivo.files[0] || null;
                pintarVista();
                actualizarBotones();
            });
            editor.querySelector('[data-imagen-quitar]').addEventListener('click', function () {
                campos.logo.value = '';
                archivo = null;
                campoArchivo.value = '';
                pintarVista();
                actualizarBotones();
            });
            editor.querySelector('[data-imagen-buscar]').addEventListener('click', function () {
                window.KairosImagenes.pintar(sugerencias, {
                    nombre: campos.nombre.value.trim() || datosActuales.nombre,
                    contenido: datosActuales.tipo === 'serie' ? 'serie' : (esPoster ? 'pelicula' : 'vivo'),
                    canal: datosActuales.pk || '',
                    urlPanel: config.urlImagenes,
                    poster: esPoster || datosActuales.tipo === 'serie',
                    alElegir: function (url) { ponerEnEditor({url: url}); }
                });
            });
            vista.addEventListener('click', function () { campoArchivo.click(); });
            vista.addEventListener('keydown', function (evento) {
                if (evento.key === 'Enter' || evento.key === ' ') {
                    evento.preventDefault();
                    campoArchivo.click();
                }
            });
            // Pegar una imagen (o el link de una) con Ctrl+V en el panel
            editor.addEventListener('paste', function (evento) {
                var portapapeles = evento.clipboardData;
                if (!portapapeles) return;
                var conArchivo = Array.prototype.some.call(portapapeles.files || [], function (f) { return /^image\//.test(f.type); });
                var texto = (portapapeles.getData('text') || '').trim();
                var escribiendo = document.activeElement && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName) &&
                    document.activeElement !== campos.logo;
                if (!conArchivo && (escribiendo || !/^(https?:\/\/|data:image\/)\S+$/i.test(texto))) return;
                evento.preventDefault();
                window.KairosImagenes.leer(portapapeles).then(ponerEnEditor);
            });
            var eliminar = editor.querySelector('[data-editor-eliminar]');
            if (eliminar) {
                eliminar.addEventListener('click', function () {
                    var esSerie = datosActuales.tipo === 'serie';
                    if (!window.confirm('¿Eliminar «' + datosActuales.nombre + '»' + (esSerie ? ' con todos sus capítulos' : '') +
                            '? Desaparece del panel y de la app (se recupera en «Eliminados»).')) return;
                    var uno = document.getElementById('form-eliminar-uno');
                    var campo = crear('input');
                    campo.type = 'hidden';
                    campo.name = esSerie ? 'serie' : 'canal';
                    campo.value = esSerie ? datosActuales.nombre : datosActuales.pk;
                    uno.appendChild(campo);
                    var siguiente = vecina(actual, 1);
                    uno.elements.volver.value = aca('ir', siguiente ? siguiente.dataset.clave : '');
                    uno.submit();
                });
            }
        }
    }

    // ── Tocar una tarjeta (o sus botones) ────────────────────────────────────
    document.addEventListener('click', function (evento) {
        var tarjeta = evento.target.closest('.espejo-tarjeta');
        if (!tarjeta || !editor) return;
        if (evento.target.closest('a, input, select, textarea, label')) return;
        var rapido = evento.target.closest('[data-rapido]');
        if (rapido) {
            alternar(tarjeta, rapido);
            return;
        }
        var categoria = evento.target.closest('[data-elegir-categoria]');
        if (categoria) {
            abrirSelector(tarjeta, categoria);
            return;
        }
        if (puedeEditar && enLista() && evento.target.closest('[data-nombre-editable]')) {
            editarNombre(tarjeta);
            return;
        }
        abrirDesdeTarjeta(tarjeta);
    });
    document.addEventListener('keydown', function (evento) {
        var tarjeta = evento.target;
        if (!tarjeta.classList || !tarjeta.classList.contains('espejo-tarjeta')) return;
        if (evento.key === 'Enter') {
            evento.preventDefault();
            abrirDesdeTarjeta(tarjeta);
        } else if (evento.key === ' ') {
            var casilla = tarjeta.querySelector('.canal-elegir');
            if (casilla) {
                evento.preventDefault();
                casilla.click();
            }
        }
    });

    // ── ★ y «se muestra» con un toque (vista Lista) ──────────────────────────
    function alternar(tarjeta, boton) {
        var campo = boton.dataset.rapido;
        var nuevo = boton.getAttribute('aria-pressed') !== 'true';
        cambiar(tarjeta, campo, nuevo ? '1' : '0', null, {
            deshacer: function (nueva) { cambiar(nueva, campo, nuevo ? '0' : '1'); }
        }).catch(function () {});
    }

    // ── El nombre, ahí mismo (vista Lista) ───────────────────────────────────
    function editarNombre(tarjeta) {
        var texto = tarjeta.querySelector('[data-nombre-editable]');
        if (!texto || texto.querySelector('input')) return;
        var antes = texto.textContent;
        var campo = crear('input', 'form-control form-control-sm nombre-en-linea');
        campo.type = 'text';
        campo.value = antes;
        campo.maxLength = datosDe(tarjeta).tipo === 'serie' ? 90 : 120;
        campo.setAttribute('aria-label', 'Nombre nuevo de «' + antes + '» (Enter guarda, Tab pasa al siguiente, Esc cancela)');
        texto.textContent = '';
        texto.appendChild(campo);
        campo.focus();
        campo.select();
        var listo = false;

        function dejarComoEstaba() { texto.textContent = antes; }
        function seguirCon(otra, paso) {
            var proxima = paso ? vecina(otra, paso) : null;
            if (proxima) editarNombre(proxima);
        }
        function terminar(paso) {
            if (listo) return;
            listo = true;
            var valor = campo.value.trim().replace(/\s+/g, ' ');
            if (!valor || valor === antes) {
                dejarComoEstaba();
                seguirCon(tarjeta, paso);
                return;
            }
            campo.disabled = true;
            cambiar(tarjeta, 'nombre', valor).then(function (nueva) { seguirCon(nueva, paso); }, dejarComoEstaba);
        }
        campo.addEventListener('keydown', function (evento) {
            if (evento.key === 'Enter') {
                evento.preventDefault();
                terminar(0);
            } else if (evento.key === 'Tab') {
                evento.preventDefault();
                terminar(evento.shiftKey ? -1 : 1);
            } else if (evento.key === 'Escape') {
                evento.preventDefault();
                evento.stopPropagation();
                listo = true;
                dejarComoEstaba();
                tarjeta.focus({preventScroll: true});
            }
        });
        campo.addEventListener('blur', function () { terminar(0); });
    }

    // ── Elegir la categoría (vista Lista): uno solo para todas, con buscador ───
    var selectorTarjeta = null;
    function filtrarSelector(texto) {
        var buscado = normalizar(texto);
        var exacta = false;
        selector.querySelectorAll('[data-valor]').forEach(function (boton) {
            var nombre = normalizar(boton.textContent);
            boton.hidden = !!buscado && nombre.indexOf(buscado) < 0;
            if (nombre === buscado) exacta = true;
        });
        var crearNueva = selector.querySelector('[data-selector-nueva]');
        crearNueva.hidden = !buscado || exacta;
        crearNueva.querySelector('span').textContent = texto.trim();
    }
    function abrirSelector(tarjeta, boton) {
        if (!selector) return;
        selectorTarjeta = tarjeta;
        var actualDe = String(datosDe(tarjeta).categoria);
        var buscar = selector.querySelector('[data-selector-buscar]');
        buscar.value = '';
        filtrarSelector('');
        selector.querySelectorAll('[data-valor]').forEach(function (opcion) {
            opcion.classList.toggle('actual', opcion.dataset.valor === actualDe);
        });
        selector.hidden = false;
        var caja = boton.getBoundingClientRect();
        var izquierda = Math.min(Math.max(8, caja.left), window.innerWidth - selector.offsetWidth - 8);
        selector.style.left = izquierda + 'px';
        var arriba = caja.bottom + 4;
        if (arriba + selector.offsetHeight > window.innerHeight - 8 && caja.top > window.innerHeight / 2) {
            arriba = caja.top - selector.offsetHeight - 4;
        }
        selector.style.bottom = 'auto';
        selector.style.top = Math.max(8, Math.min(arriba, window.innerHeight - selector.offsetHeight - 8)) + 'px';
        buscar.focus({preventScroll: true});
    }
    function cerrarSelector() {
        if (selector) selector.hidden = true;
        selectorTarjeta = null;
    }
    function sumarCategoria(pk, nombre) {
        // Una categoría recién creada: que aparezca en las listas sin recargar
        if (!pk || selector.querySelector('[data-valor="' + pk + '"]')) return;
        var boton = crear('button', '', nombre);
        boton.type = 'button';
        boton.dataset.valor = pk;
        var lista = selector.querySelector('[data-selector-lista]');
        lista.insertBefore(boton, lista.querySelector('[data-valor="ninguna"]'));
        [campos && campos.categoria, formOrganizar && formOrganizar.querySelector('select[data-pide=mover]')].forEach(function (select) {
            if (!select) return;
            var opcion = crear('option', '', nombre);
            opcion.value = pk;
            select.insertBefore(opcion, select.querySelector('option[value="ninguna"]'));
        });
    }
    function elegirCategoria(valor, nombreNuevo) {
        var tarjeta = selectorTarjeta;
        cerrarSelector();
        if (!tarjeta) return;
        var antes = String(datosDe(tarjeta).categoria);
        if (!nombreNuevo && valor === antes) return;
        cambiar(tarjeta, 'categoria', nombreNuevo ? '' : valor, nombreNuevo ? {nueva: nombreNuevo} : null, {
            deshacer: function (nueva) { cambiar(nueva, 'categoria', antes); }
        }).then(function (nueva) {
            var datos = datosDe(nueva);
            if (nombreNuevo && datos) sumarCategoria(String(datos.categoria), datos.categoria_nombre);
            nueva.focus({preventScroll: true});
        }, function () {});
    }
    if (selector) {
        var buscarCategoria = selector.querySelector('[data-selector-buscar]');
        buscarCategoria.addEventListener('input', function () { filtrarSelector(buscarCategoria.value); });
        buscarCategoria.addEventListener('keydown', function (evento) {
            if (evento.key === 'Escape') {
                evento.preventDefault();
                evento.stopPropagation();   // que no cierre también el panel de edición
                var volverA = selectorTarjeta;
                cerrarSelector();
                if (volverA) volverA.focus({preventScroll: true});
            } else if (evento.key === 'Enter') {
                // Enter elige la primera que coincide; crea una nueva solo si no coincide ninguna
                // (para crear una aunque haya parecidas está el botón «Crear»)
                evento.preventDefault();
                var primera = Array.prototype.filter.call(selector.querySelectorAll('[data-valor]'), function (b) { return !b.hidden; })[0];
                var crearNueva = selector.querySelector('[data-selector-nueva]');
                if (primera) elegirCategoria(primera.dataset.valor);
                else if (!crearNueva.hidden) elegirCategoria('', buscarCategoria.value.trim());
            } else if (evento.key === 'ArrowDown') {
                evento.preventDefault();
                var visible = Array.prototype.filter.call(selector.querySelectorAll('[data-valor]'), function (b) { return !b.hidden; })[0];
                if (visible) visible.focus();
            }
        });
        selector.addEventListener('click', function (evento) {
            var opcion = evento.target.closest('[data-valor]');
            if (opcion) elegirCategoria(opcion.dataset.valor);
            else if (evento.target.closest('[data-selector-nueva]')) elegirCategoria('', buscarCategoria.value.trim());
        });
        selector.addEventListener('keydown', function (evento) {
            var opcion = evento.target.closest('[data-valor]');
            if (!opcion || (evento.key !== 'ArrowDown' && evento.key !== 'ArrowUp')) return;
            evento.preventDefault();
            var visibles = Array.prototype.filter.call(selector.querySelectorAll('[data-valor]'), function (b) { return !b.hidden; });
            var otra = visibles[visibles.indexOf(opcion) + (evento.key === 'ArrowDown' ? 1 : -1)];
            if (otra) otra.focus();
            else if (evento.key === 'ArrowUp') buscarCategoria.focus();
        });
        document.addEventListener('click', function (evento) {
            if (!selector.hidden && !selector.contains(evento.target) && !evento.target.closest('[data-elegir-categoria]')) cerrarSelector();
        });
        window.addEventListener('scroll', function () { if (!selector.hidden) cerrarSelector(); }, {passive: true});
        window.addEventListener('resize', cerrarSelector);
    }

    // ── Arrastrar una imagen arriba de una tarjeta (o del panel) ──────────────
    var bajoElArrastre = null;
    function marcarArrastre(destino) {
        if (bajoElArrastre === destino) return;
        if (bajoElArrastre) bajoElArrastre.classList.remove('soltar-aca');
        bajoElArrastre = destino;
        if (destino) destino.classList.add('soltar-aca');
    }
    document.addEventListener('dragover', function (evento) {
        if (!puedeEditar || !window.KairosImagenes || !window.KairosImagenes.trae(evento.dataTransfer)) return;
        var destino = evento.target.closest('.espejo-tarjeta, #editor');
        // Afuera de una tarjeta no se suelta (si no, el navegador abriría la imagen y se saldría del panel)
        evento.preventDefault();
        evento.dataTransfer.dropEffect = destino ? 'copy' : 'none';
        marcarArrastre(destino);
    });
    document.addEventListener('dragleave', function (evento) {
        if (bajoElArrastre && !bajoElArrastre.contains(evento.relatedTarget)) marcarArrastre(null);
    });
    document.addEventListener('drop', function (evento) {
        if (!puedeEditar || !window.KairosImagenes || !window.KairosImagenes.trae(evento.dataTransfer)) return;
        evento.preventDefault();
        var destino = evento.target.closest('.espejo-tarjeta, #editor');
        marcarArrastre(null);
        if (!destino) return;
        window.KairosImagenes.leer(evento.dataTransfer).then(function (imagen) {
            if (!imagen) {
                avisar('Eso no parece una imagen: arrastrá la imagen misma (o su link).', 'mal');
                return;
            }
            if (destino.id === 'editor') {
                ponerEnEditor(imagen);
                return;
            }
            var anterior = (datosDe(destino) || {}).logo || '';
            cambiar(destino, 'logo', imagen.url || '', imagen.archivo ? {imagen: imagen.archivo} : null, {
                deshacer: function (nueva) { cambiar(nueva, 'logo', anterior); }
            }).catch(function () {});
        });
    });

    // ── Elegir tarjetas y la barra de abajo ──────────────────────────────────
    function casillas() {
        return formOrganizar ? Array.prototype.slice.call(formOrganizar.querySelectorAll('.canal-elegir')) : [];
    }
    var ultimaCasilla = null;
    function actualizarBarra() {
        if (!formOrganizar) return;
        var todasLasCasillas = casillas();
        var elegidos = todasLasCasillas.filter(function (c) { return c.checked; }).length;
        var cantidad = document.getElementById('cantidad-elegidos');
        var accion = document.getElementById('accion');
        var barra = formOrganizar.querySelector('.espejo-barra');
        var todos = document.getElementById('elegir-todos');
        if (cantidad) cantidad.textContent = elegidos ? elegidos + ' elegido' + (elegidos > 1 ? 's' : '') : 'Ninguno elegido';
        if (barra) barra.classList.toggle('tiene-seleccion', elegidos > 0);
        if (todos) {
            todos.checked = elegidos > 0 && elegidos === todasLasCasillas.length;
            todos.indeterminate = elegidos > 0 && elegidos < todasLasCasillas.length;
        }
        // Solo se ve lo de la acción elegida, y solo con algo elegido. Lo escondido no se manda
        formOrganizar.querySelectorAll('[data-accion]').forEach(function (fila) {
            fila.hidden = !elegidos || fila.dataset.accion !== (accion && accion.value);
            fila.querySelectorAll('input, select').forEach(function (campo) { campo.disabled = fila.hidden; });
        });
        var seccion = document.getElementById('seccion-destino');
        if (seccion) {
            var aSerie = seccion.value === 'serie';
            var cajaSerie = formOrganizar.querySelector('.espejo-barra-serie');
            cajaSerie.style.display = aSerie ? 'flex' : 'none';
            var sinSerie = formOrganizar.querySelector('[data-accion=seccion]').hidden || !aSerie;
            cajaSerie.querySelectorAll('input, select').forEach(function (campo) { campo.disabled = sinSerie; });
            document.getElementById('seccion-ayuda').textContent = aSerie
                ? 'Los elegidos quedan como capítulos de UNA serie: elegí la categoría, la serie (una que ya existe o una nueva) y la temporada. Siguen después del último capítulo de esa temporada, en orden alfabético.'
                : 'Los elegidos se mueven a esa sección (con una categoría del mismo nombre allá).';
        }
        if (accion && accion.value === 'renombrar') pedirVistaPrevia();
    }

    if (formOrganizar) {
        formOrganizar.addEventListener('click', function (evento) {
            var casilla = evento.target.closest('.canal-elegir');
            if (!casilla) return;
            // Shift + clic: todas las del medio quedan igual que esta
            if (evento.shiftKey && ultimaCasilla && ultimaCasilla !== casilla && document.contains(ultimaCasilla)) {
                var todas = casillas();
                var desde = todas.indexOf(ultimaCasilla);
                var hasta = todas.indexOf(casilla);
                todas.slice(Math.min(desde, hasta), Math.max(desde, hasta) + 1).forEach(function (c) { c.checked = casilla.checked; });
            }
            ultimaCasilla = casilla;
        });
        formOrganizar.addEventListener('change', function (evento) {
            if (evento.target.closest('.canal-elegir, #accion, #seccion-destino')) actualizarBarra();
        });
        var elegirPagina = document.getElementById('elegir-pagina');
        if (elegirPagina) {
            elegirPagina.addEventListener('click', function () {
                casillas().forEach(function (c) { c.checked = true; });
                actualizarBarra();
            });
        }
        var limpiar = document.getElementById('limpiar-seleccion');
        if (limpiar) {
            limpiar.addEventListener('click', function () {
                casillas().forEach(function (c) { c.checked = false; });
                var accion = document.getElementById('accion');
                if (accion) accion.value = '';
                actualizarBarra();
            });
        }
        var todos = document.getElementById('elegir-todos');
        if (todos) {
            todos.addEventListener('change', function () {
                casillas().forEach(function (c) { c.checked = todos.checked; });
                actualizarBarra();
            });
        }
        actualizarBarra();
    }

    // ── «Cambiar nombres»: cómo quedan, antes de aplicarlo ───────────────────
    var filaRenombrar = formOrganizar && formOrganizar.querySelector('[data-accion=renombrar]');
    var relojRenombrar = null;
    var pedidoRenombrar = 0;
    function pedirVistaPrevia() {
        if (!filaRenombrar) return;
        window.clearTimeout(relojRenombrar);
        relojRenombrar = window.setTimeout(vistaPrevia, 350);
    }
    function vistaPrevia() {
        if (!filaRenombrar || filaRenombrar.hidden) return;
        var vistaNombres = filaRenombrar.querySelector('[data-renombrar-vista]');
        var boton = filaRenombrar.querySelector('[data-renombrar-boton]');
        var valor = function (nombre) { return filaRenombrar.querySelector('[name=' + nombre + ']'); };
        var hayRegla = valor('sacar').value.trim() || valor('reemplazar').value.trim() || valor('limpiar').checked || valor('mayusculas').checked;
        boton.disabled = true;
        boton.textContent = 'Cambiar nombres';
        if (!hayRegla) {
            vistaNombres.textContent = 'Escribí qué sacar o qué cambiar, o marcá una opción: acá vas a ver cómo quedan antes de cambiarlos.';
            return;
        }
        var datos = new FormData();
        casillas().filter(function (c) { return c.checked; }).forEach(function (c) { datos.append(c.name, c.value); });
        ['sacar', 'reemplazar', 'por'].forEach(function (nombre) { datos.append(nombre, valor(nombre).value); });
        if (valor('limpiar').checked) datos.append('limpiar', '1');
        if (valor('mayusculas').checked) datos.append('mayusculas', '1');
        datos.append('vista_previa', '1');
        var este = ++pedidoRenombrar;
        vistaNombres.textContent = 'Viendo cómo quedan…';
        pedir(config.urlRenombrar, datos).then(function (r) {
            if (este !== pedidoRenombrar) return;
            vistaNombres.textContent = '';
            if (!r.cambios.length) {
                vistaNombres.textContent = 'Con eso no cambia ningún nombre de lo elegido (' + r.elegidos + ').';
                return;
            }
            var lista = crear('ul');
            r.cambios.slice(0, 12).forEach(function (cambio) {
                var fila = crear('li');
                fila.appendChild(crear('span', 'renombrar-antes', cambio.antes));
                fila.appendChild(crear('i', 'bi bi-arrow-right'));
                fila.appendChild(crear('strong', '', cambio.despues));
                lista.appendChild(fila);
            });
            vistaNombres.appendChild(lista);
            if (r.cambios.length > 12) vistaNombres.appendChild(crear('p', 'mb-0', 'Y ' + (r.cambios.length - 12) + ' más.'));
            boton.disabled = false;
            boton.textContent = 'Cambiar ' + r.cambios.length + ' nombre' + (r.cambios.length > 1 ? 's' : '');
        }, function (error) {
            if (este === pedidoRenombrar) vistaNombres.textContent = error.message;
        });
    }
    if (filaRenombrar) {
        filaRenombrar.addEventListener('input', pedirVistaPrevia);
        filaRenombrar.addEventListener('change', pedirVistaPrevia);
    }

    // ── Volver a una tarjeta (después de una acción que recarga) o abrirla: ?ir= / ?abrir= ──
    (function () {
        var parametros = new URLSearchParams(window.location.search);
        var abrirClave = parametros.get('abrir');
        var irClave = parametros.get('ir');
        var marca = /^#ver-(\d+)$/.exec(window.location.hash);   // las acciones de una señal vuelven con #ver-<canal>
        if (marca && !abrirClave) abrirClave = 'c' + marca[1];
        if (!abrirClave && !irClave) return;
        var lista = tarjetas();
        var tarjeta = abrirClave === 'primera' ? lista[0] : abrirClave === 'ultima' ? lista[lista.length - 1]
            : porClave(abrirClave || irClave);
        if (tarjeta) {
            tarjeta.scrollIntoView({block: 'center'});
            tarjeta.classList.add('recien-editada');
            if (abrirClave) abrir(tarjeta, {foco: true});
            else tarjeta.focus({preventScroll: true});
        }
        history.replaceState(null, '', aca('abrir', ''));   // (sin la marca: al recargar no se vuelve a abrir)
    })();

    // ── Juntar categorías: aparece al elegir dos o más ───────────────────────
    var juntar = document.getElementById('form-juntar');
    var barraJuntar = document.getElementById('juntar-barra');
    if (juntar && barraJuntar) {
        var destino = document.getElementById('juntar-destino');
        var actualizarJuntar = function () {
            var elegidas = Array.prototype.filter.call(juntar.querySelectorAll('[name=elegida]'), function (c) { return c.checked; });
            barraJuntar.hidden = elegidas.length < 2;
            document.getElementById('juntar-cuantas').textContent = elegidas.length;
            destino.textContent = '';
            elegidas.forEach(function (c) {
                var opcion = crear('option', '', '«' + c.dataset.nombre + '»');
                opcion.value = c.value;
                destino.appendChild(opcion);
            });
        };
        juntar.querySelectorAll('[name=elegida]').forEach(function (c) { c.addEventListener('change', actualizarJuntar); });
        actualizarJuntar();
    }

    // ── Buscar categorías (izquierda) sin recargar ni perder los filtros ─────
    var buscarCategorias = document.getElementById('buscar-categorias');
    if (buscarCategorias) {
        var filasCategorias = Array.prototype.slice.call(document.querySelectorAll('[data-categoria-fila]'));
        var categoriasVacio = document.getElementById('categorias-vacio');
        buscarCategorias.addEventListener('input', function () {
            var texto = normalizar(buscarCategorias.value);
            var visibles = 0;
            filasCategorias.forEach(function (fila, indice) {
                var coincide = !texto || normalizar(fila.textContent).indexOf(texto) >= 0;
                fila.hidden = texto ? !coincide : false;   // "Todas" queda cuando no se busca
                if (!fila.hidden && (texto || indice > 0)) visibles += 1;
            });
            categoriasVacio.hidden = !texto || visibles > 0;
        });
    }

    // ── «Nueva sección» en las pestañas muestra el formulario de crear ───────
    var crearSeccion = document.getElementById('nueva-seccion');
    if (crearSeccion) {
        var mostrarCrear = function () {
            crearSeccion.hidden = false;
            crearSeccion.open = true;
            crearSeccion.scrollIntoView({behavior: 'smooth', block: 'start'});
            document.getElementById('seccion-nombre').focus();
        };
        document.querySelectorAll('[data-abrir-seccion]').forEach(function (enlace) {
            enlace.addEventListener('click', function (evento) {
                evento.preventDefault();
                mostrarCrear();
            });
        });
        crearSeccion.addEventListener('toggle', function () { if (!crearSeccion.open) crearSeccion.hidden = true; });
        if (window.location.hash === '#nueva-seccion') mostrarCrear();
    }

    // ── Exportar ─────────────────────────────────────────────────────────────
    var cuadroExportar = document.getElementById('exportar');
    if (cuadroExportar) {
        var formExportar = document.getElementById('form-exportar');
        var arbol = document.getElementById('exportar-arbol');
        var radioLista = document.getElementById('exportar-lista');
        var radioElegido = document.getElementById('exportar-elegido');
        var avisoExportar = document.getElementById('exportar-aviso');
        var elegidas = function () { return casillas().filter(function (c) { return c.checked; }); };
        // Una sección entera marcada ya incluye sus categorías: se marcan y quedan fijas (no se mandan aparte)
        var acomodarSeccion = function (seccion) {
            arbol.querySelectorAll('[data-de="' + seccion.value + '"]').forEach(function (c) {
                if (seccion.checked) c.checked = true;
                else if (c.disabled) c.checked = false;
                c.disabled = seccion.checked;
            });
        };
        arbol.querySelectorAll('[data-seccion]').forEach(function (seccion) {
            acomodarSeccion(seccion);
            seccion.addEventListener('change', function () { acomodarSeccion(seccion); });
        });
        arbol.addEventListener('change', function () {
            radioLista.checked = true;
            avisoExportar.textContent = '';
        });
        cuadroExportar.querySelectorAll('[data-exportar-todo]').forEach(function (boton) {
            boton.addEventListener('click', function () {
                var marcar = boton.dataset.exportarTodo === '1';
                arbol.querySelectorAll('[data-seccion]').forEach(function (seccion) {
                    if (!seccion.disabled) seccion.checked = marcar;
                    acomodarSeccion(seccion);
                });
                arbol.querySelectorAll('[data-de]').forEach(function (c) { if (!marcar) c.checked = false; });
                radioLista.checked = true;
                avisoExportar.textContent = '';
            });
        });
        document.querySelectorAll('[data-abrir-exportar]').forEach(function (boton) {
            boton.addEventListener('click', function () {
                var cuantos = elegidas().length;
                document.getElementById('exportar-cuantos').textContent = cuantos;
                radioElegido.disabled = !cuantos;
                if (boton.dataset.abrirExportar === 'elegido' && cuantos) radioElegido.checked = true;
                else if (!cuantos) radioLista.checked = true;
                avisoExportar.textContent = '';
                cuadroExportar.showModal();
            });
        });
        formExportar.addEventListener('submit', function (evento) {
            formExportar.querySelectorAll('[data-tarjeta]').forEach(function (campo) { campo.remove(); });
            if (radioElegido.checked) {
                // Las tarjetas elegidas están en otro formulario: se copian acá
                elegidas().forEach(function (c) {
                    var campo = crear('input');
                    campo.type = 'hidden';
                    campo.name = c.name;
                    campo.value = c.value;
                    campo.dataset.tarjeta = '';
                    formExportar.appendChild(campo);
                });
            } else if (!arbol.querySelector('input:checked:not(:disabled)')) {
                evento.preventDefault();
                avisoExportar.textContent = 'Elegí al menos una sección o una categoría.';
                return;
            }
            // La descarga no cambia de página: se cierra el cuadro
            window.setTimeout(function () { cuadroExportar.close(); }, 300);
        });
        cuadroExportar.querySelectorAll('[data-cerrar]').forEach(function (b) { b.addEventListener('click', function () { cuadroExportar.close(); }); });
        cuadroExportar.addEventListener('click', function (evento) { if (evento.target === cuadroExportar) cuadroExportar.close(); });
    }
})();
