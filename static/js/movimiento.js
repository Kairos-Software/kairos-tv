/* movimiento.js — el movimiento sutil del panel (sin dependencias)

   Solo visual: lee lo que la página ya muestra y lo anima. No pide nada al
   servidor ni cambia datos. Sin este archivo, o con "reducir movimiento"
   activo en el sistema, el panel se ve y funciona igual, sin animar. */

(function () {
    'use strict';

    const reducir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const enfocadoConTeclado = function (el) {
        try { return el.matches(':focus-visible'); } catch (_) { return true; }
    };

    // ── Menú lateral: una sola luz que se desliza entre las opciones ──
    const nav = document.querySelector('.menu-nav');
    if (nav && !reducir) {
        const luz = document.createElement('span');
        luz.className = 'menu-luz';
        luz.setAttribute('aria-hidden', 'true');
        nav.prepend(luz);
        nav.classList.add('con-luz');

        const ubicar = function (enlace) {
            luz.style.transform = 'translate(' + enlace.offsetLeft + 'px,' + enlace.offsetTop + 'px)';
            luz.style.width = enlace.offsetWidth + 'px';
            luz.style.height = enlace.offsetHeight + 'px';
        };
        const apagar = function () { luz.style.opacity = '0'; };
        const prender = function (enlace) {
            if (enlace.classList.contains('activo')) return apagar();
            if (luz.style.opacity !== '1') {   // aparece ahí mismo, sin viajar desde la anterior
                luz.style.transition = 'none';
                ubicar(enlace);
                void luz.offsetWidth;
                luz.style.transition = '';
                luz.style.opacity = '1';
            } else {
                ubicar(enlace);
            }
        };
        nav.addEventListener('pointerover', function (evento) {
            if (evento.pointerType !== 'mouse') return;
            const enlace = evento.target.closest('.menu-link');
            if (enlace) prender(enlace);
        });
        nav.addEventListener('pointerleave', apagar);
        nav.addEventListener('focusin', function (evento) {
            const enlace = evento.target.closest('.menu-link');
            if (enlace && enfocadoConTeclado(enlace)) prender(enlace);
        });
        nav.addEventListener('focusout', apagar);
    }

    // ── Inicio: la onda de señal detrás del saludo ─────────────────
    // Sin WebGL queda el fondo de siempre (kairos.css). Solo dibuja mientras se ve.
    const VERTICES = 'attribute vec2 p; varying vec2 u; void main(){ u = p * .5 + .5; gl_Position = vec4(p, 0., 1.); }';
    const COLOR = [
        'precision mediump float;',
        'uniform float t; uniform vec2 r; varying vec2 u;',
        'float onda(vec2 p, float f, float v, float a){ return sin(p.x * f + t * v + sin(p.y * f * .8 - t * v * .6) * a); }',
        'void main(){',
        '  vec2 p = u * vec2(r.x / r.y, 1.);',
        '  float n = onda(p, .95, .11, 1.9) + .55 * onda(p + 3.1, 1.9, -.08, 1.3);',
        '  float der = smoothstep(.24, .92, u.x);',
        '  vec3 f = mix(vec3(.122, .122, .141), vec3(.055, .055, .071), u.x * .65 + (1. - u.y) * .35);',
        '  vec3 cel = vec3(0., .941, 1.), rub = vec3(.875, 0., .255);',
        '  float b = .5 + .5 * sin(n * 1.3);',
        '  f += cel * pow(b, 2.4) * .24 * der;',
        '  float hilo = abs(fract(n * 2.1) - .5);',
        '  f += cel * smoothstep(.022, .0, hilo) * .17 * der;',
        '  f += rub * pow(max(0., sin(n * .8 + 1.3)), 12.) * .1 * der;',
        '  gl_FragColor = vec4(f, 1.);',
        '}',
    ].join('\n');

    function iniciarOnda(caja) {
        const lienzo = document.createElement('canvas');
        const gl = lienzo.getContext('webgl', {alpha: false, antialias: false, powerPreference: 'low-power'});
        if (!gl) return;
        const armar = function (tipo, fuente) {
            const sombreador = gl.createShader(tipo);
            gl.shaderSource(sombreador, fuente);
            gl.compileShader(sombreador);
            return sombreador;
        };
        const programa = gl.createProgram();
        gl.attachShader(programa, armar(gl.VERTEX_SHADER, VERTICES));
        gl.attachShader(programa, armar(gl.FRAGMENT_SHADER, COLOR));
        gl.linkProgram(programa);
        if (!gl.getProgramParameter(programa, gl.LINK_STATUS)) return;
        gl.useProgram(programa);
        gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
        const posicion = gl.getAttribLocation(programa, 'p');
        gl.enableVertexAttribArray(posicion);
        gl.vertexAttribPointer(posicion, 2, gl.FLOAT, false, 0, 0);
        const uT = gl.getUniformLocation(programa, 't');
        const uR = gl.getUniformLocation(programa, 'r');

        lienzo.className = 'inicio-onda';
        lienzo.setAttribute('aria-hidden', 'true');
        caja.prepend(lienzo);
        caja.classList.add('con-onda');

        const dibujar = function (ms) {
            gl.uniform1f(uT, ms / 1000);
            gl.drawArrays(gl.TRIANGLES, 0, 3);
        };
        const medir = function () {
            const k = Math.min(window.devicePixelRatio || 1, 1.5);
            lienzo.width = Math.max(1, Math.round(caja.clientWidth * k));
            lienzo.height = Math.max(1, Math.round(caja.clientHeight * k));
            gl.viewport(0, 0, lienzo.width, lienzo.height);
            gl.uniform2f(uR, lienzo.width, lienzo.height);
            dibujar(performance.now());
        };
        medir();
        if ('ResizeObserver' in window) new ResizeObserver(medir).observe(caja);

        let enPantalla = true;
        let anterior = 0;
        let pedido = 0;
        const cuadro = function (ms) {
            pedido = 0;
            if (!enPantalla || document.hidden) return;
            if (ms - anterior >= 32) {   // se mueve lento: alcanza con 30 cuadros por segundo
                anterior = ms;
                dibujar(ms);
            }
            pedido = requestAnimationFrame(cuadro);
        };
        const seguir = function () { if (!pedido) pedido = requestAnimationFrame(cuadro); };
        document.addEventListener('visibilitychange', seguir);
        if ('IntersectionObserver' in window) {
            new IntersectionObserver(function (entradas) {
                enPantalla = entradas[0].isIntersecting;
                seguir();
            }).observe(caja);
        }
        lienzo.addEventListener('webglcontextlost', function () {
            enPantalla = false;
            lienzo.remove();
            caja.classList.remove('con-onda');
        });
        seguir();
    }

    const saludo = document.querySelector('.inicio-encabezado');
    if (saludo && !reducir) iniciarOnda(saludo);

    // ── Inicio: la luz del borde sigue al cursor por las herramientas ──
    const grilla = document.querySelector('.modulos-grid');
    if (grilla && !reducir) {
        const tarjetas = grilla.querySelectorAll('.acceso-rapido');
        let pedidoLuz = 0;
        grilla.addEventListener('pointermove', function (evento) {
            if (evento.pointerType !== 'mouse' || pedidoLuz) return;
            pedidoLuz = requestAnimationFrame(function () {
                pedidoLuz = 0;
                tarjetas.forEach(function (tarjeta) {
                    const caja = tarjeta.getBoundingClientRect();
                    tarjeta.style.setProperty('--luz-x', (evento.clientX - caja.left) + 'px');
                    tarjeta.style.setProperty('--luz-y', (evento.clientY - caja.top) + 'px');
                });
            });
        });
    }

    // ── Cifras: leer lo que escribió el servidor ───────────────────
    // "$ 812.500,00" o "312": valor y formato, para volver a escribirlo igual.
    function leerCifra(texto) {
        const partes = texto.trim().match(/^(\D*?)(-?)(\d[\d.,]*)(.*)$/);
        if (!partes) return null;
        const cuerpo = partes[3];
        const decimal = cuerpo.match(/[.,](\d{1,2})$/);
        const entero = decimal ? cuerpo.slice(0, decimal.index) : cuerpo;
        const miles = entero.match(/[.,]/);
        const valor = Number(entero.replace(/[.,]/g, '') + (decimal ? '.' + decimal[1] : ''));
        if (Number.isNaN(valor)) return null;
        return {
            prefijo: partes[1], signo: partes[2], sufijo: partes[4], valor: valor,
            decimales: decimal ? decimal[1].length : 0,
            coma: decimal ? cuerpo[decimal.index] : ',',
            miles: miles ? miles[0] : '',
        };
    }

    function escribirCifra(cifra, valor) {
        const partes = valor.toFixed(cifra.decimales).split('.');
        const entero = cifra.miles ? partes[0].replace(/\B(?=(\d{3})+$)/g, cifra.miles) : partes[0];
        return cifra.prefijo + cifra.signo + entero + (partes[1] ? cifra.coma + partes[1] : '') + cifra.sufijo;
    }

    // Las cifras de Reventa y Estadísticas suben hasta su valor y terminan con el texto original.
    if (!reducir) {
        document.querySelectorAll('.pagina-reventa .resumen-metricas dd, .pagina-estadisticas-reventa .resumen-metricas dd, .pagina-revendedor .resumen-metricas dd').forEach(function (dato) {
            const original = dato.textContent;
            const cifra = leerCifra(original);
            if (!cifra || !cifra.valor || dato.children.length) return;
            const DURACION = 1000;
            let inicio = null;
            const paso = function (ms) {
                if (inicio === null) inicio = ms;
                const avance = Math.min((ms - inicio) / DURACION, 1);
                if (avance === 1) { dato.textContent = original; return; }
                dato.textContent = escribirCifra(cifra, cifra.valor * (1 - Math.pow(1 - avance, 3)));
                requestAnimationFrame(paso);
            };
            requestAnimationFrame(paso);
        });
    }

    // Una ganancia negativa no se pinta como las buenas noticias
    document.querySelectorAll('.resumen-balance > div:last-child dd').forEach(function (dato) {
        const cifra = leerCifra(dato.textContent);
        if (cifra && cifra.signo && cifra.valor) dato.classList.add('negativo');
    });

    // ── Estado de clientes: la barra que suma los cuatro estados ───
    document.querySelectorAll('.resumen-clientes').forEach(function (lista) {
        const filas = Array.from(lista.children);
        const valores = filas.map(function (fila) {
            const cifra = leerCifra(fila.querySelector('dd').textContent);
            return cifra ? cifra.valor : 0;
        });
        if (!valores.some(Boolean)) return;
        const barra = document.createElement('div');
        barra.className = 'barra-estados';
        barra.setAttribute('role', 'img');
        barra.setAttribute('aria-label', filas.map(function (fila) {
            return fila.querySelector('dt').textContent.trim() + ': ' + fila.querySelector('dd').textContent.trim();
        }).join(', '));
        valores.forEach(function (valor, i) {
            if (!valor) return;
            const parte = document.createElement('i');
            parte.dataset.estado = i;
            parte.style.flex = valor + ' 1 0';
            barra.append(parte);
        });
        lista.after(barra);
        filas.forEach(function (fila, i) {
            fila.addEventListener('pointerenter', function () {
                barra.classList.add('resalta');
                barra.querySelectorAll('i').forEach(function (parte) {
                    parte.classList.toggle('si', Number(parte.dataset.estado) === i);
                });
            });
            fila.addEventListener('pointerleave', function () { barra.classList.remove('resalta'); });
        });
    });

    // ── Estadísticas: el gráfico sale de la tabla que ya está en la página ──
    const tabla = document.querySelector('.pagina-estadisticas-reventa .tabla-estadisticas');
    if (tabla) armarGrafico(tabla);

    function armarGrafico(tablaMeses) {
        const titulos = Array.from(tablaMeses.querySelectorAll('thead th')).map(function (th) { return th.textContent.trim(); });
        const filas = Array.from(tablaMeses.querySelectorAll('tbody tr')).reverse();   // la tabla trae primero el mes actual
        if (filas.length < 2) return;
        const columna = function (i) {
            return filas.map(function (fila) {
                const texto = fila.children[i].textContent.trim();
                const cifra = leerCifra(texto);
                return {texto: texto, valor: cifra ? (cifra.signo ? -cifra.valor : cifra.valor) : 0};
            });
        };
        // El dato de plata de la última columna (Ingresos o Ganancia), clientes nuevos y renovaciones
        const series = [titulos.length - 1, titulos.indexOf('Clientes nuevos'), titulos.indexOf('Renovaciones')]
            .filter(function (i) { return i > 0; })
            .map(function (i) {
                const datos = columna(i);
                return {nombre: titulos[i], datos: datos, plata: datos.some(function (d) { return d.texto.indexOf('$') >= 0; })};
            })
            .filter(function (serie) { return serie.datos.some(function (d) { return d.valor; }); });
        if (!series.length) return;
        const meses = filas.map(function (fila) { return fila.children[0].textContent.trim(); });

        const compacto = new Intl.NumberFormat('es-AR', {notation: 'compact', maximumFractionDigits: 1});
        const redondear = function (maximo) {
            const p = Math.pow(10, Math.floor(Math.log10(maximo)));
            return [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 9, 10].find(function (x) { return x * p >= maximo; }) * p;
        };
        // De dónde a dónde va el eje. La ganancia de un revendedor puede ser negativa: el piso baja de cero.
        const rango = function (serie) {
            const valores = serie.datos.map(function (d) { return d.valor; });
            const maximo = Math.max.apply(null, valores);
            const minimo = Math.min.apply(null, valores);
            return {tope: maximo > 0 ? redondear(maximo) : 0, piso: minimo < 0 ? -redondear(-minimo) : 0};
        };
        const normalizar = function (serie) {
            const r = rango(serie);
            return serie.datos.map(function (d) { return (d.valor - r.piso) / (r.tope - r.piso); });
        };

        const caja = document.createElement('div');
        caja.className = 'grafico-mes';
        const opciones = series.length > 1 ? '<div class="pestanias grafico-mes-opciones" role="group" aria-label="Qué dato graficar">'
            + series.map(function (serie, i) {
                return '<button type="button" data-serie="' + i + '" aria-pressed="' + (i === 0) + '">' + serie.nombre + '</button>';
            }).join('') + '</div>' : '';
        caja.innerHTML = opciones
            + '<div class="grafico-mes-lienzo" tabindex="0" role="img"><svg aria-hidden="true"></svg><div class="grafico-burbuja"></div></div>';
        tablaMeses.closest('.tarjeta').querySelector('.tarjeta-titulo').after(caja);
        const lienzo = caja.querySelector('.grafico-mes-lienzo');
        const svg = caja.querySelector('svg');
        const burbuja = caja.querySelector('.grafico-burbuja');

        let actual = 0;
        let alturas = normalizar(series[0]);
        let visto = null;      // el mes que se está mirando
        let revelado = reducir ? 1 : 0;

        const describir = function () {
            lienzo.setAttribute('aria-label', series[actual].nombre + ' de los últimos ' + meses.length
                + ' meses. Los mismos datos están en la tabla de abajo. Con las flechas se recorre mes por mes.');
        };

        function medidas() {
            const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
            const ancho = lienzo.clientWidth;
            return {ancho: ancho, alto: lienzo.clientHeight, izq: 3.6 * rem, der: 1.2 * rem, arr: 1.4 * rem, aba: 1.6 * rem, rem: rem};
        }

        function dibujar() {
            const m = medidas();
            if (!m.ancho) return;
            const serie = series[actual];
            const r = rango(serie);
            const X = function (i) { return m.izq + (i / (meses.length - 1)) * (m.ancho - m.izq - m.der); };
            const Y = function (n) { return m.arr + (1 - n) * (m.alto - m.arr - m.aba); };
            const YValor = function (v) { return Y((v - r.piso) / (r.tope - r.piso)); };
            const puntos = alturas.map(function (n, i) { return [X(i), Y(n)]; });
            const linea = puntos.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
            const area = linea + ' L' + X(meses.length - 1).toFixed(1) + ' ' + YValor(0) + ' L' + X(0).toFixed(1) + ' ' + YValor(0) + ' Z';
            const eje = function (v) { return (serie.plata ? '$ ' : '') + compacto.format(v); };
            const marcasEje = r.piso < 0 ? [r.piso, 0, r.tope] : [0, r.tope / 2, r.tope];
            const rejilla = marcasEje.filter(function (v, i, todas) {
                return todas.indexOf(v) === i && (serie.plata || Number.isInteger(v));   // no existe medio cliente
            }).map(function (v) {
                return '<line class="grafico-rejilla" x1="' + m.izq + '" x2="' + (m.ancho - m.der) + '" y1="' + YValor(v) + '" y2="' + YValor(v) + '"/>'
                    + '<text class="grafico-eje" x="' + (m.izq - .6 * m.rem) + '" y="' + (YValor(v) + .25 * m.rem) + '" text-anchor="end">' + eje(v) + '</text>';
            }).join('');
            // Con poco ancho, un mes sí y uno no, siempre terminando en el actual
            const salto = (m.ancho - m.izq - m.der) / meses.length < 34 ? 2 : 1;
            const etiquetas = meses.map(function (mes, i) {
                if ((meses.length - 1 - i) % salto) return '';
                return '<text class="grafico-eje" x="' + X(i) + '" y="' + (m.alto - .2 * m.rem) + '" text-anchor="middle">' + mes.slice(0, 3).toLowerCase() + '</text>';
            }).join('');
            const ultimo = puntos.length - 1;
            const marca = visto === null
                ? '<circle class="grafico-punto" cx="' + puntos[ultimo][0] + '" cy="' + puntos[ultimo][1] + '" r="4"/>'
                    + '<text class="grafico-rotulo" x="' + puntos[ultimo][0] + '" y="' + Math.max(puntos[ultimo][1] - .7 * m.rem, .9 * m.rem) + '" text-anchor="end">' + serie.datos[ultimo].texto + '</text>'
                : '<line class="grafico-guia" x1="' + puntos[visto][0] + '" x2="' + puntos[visto][0] + '" y1="' + m.arr + '" y2="' + Y(0) + '"/>'
                    + '<circle class="grafico-punto" cx="' + puntos[visto][0] + '" cy="' + puntos[visto][1] + '" r="5"/>';
            svg.innerHTML = '<defs><linearGradient id="grafico-relleno" x1="0" x2="0" y1="0" y2="1">'
                + '<stop offset="0" stop-color="#00F0FF" stop-opacity=".2"/><stop offset="1" stop-color="#00F0FF" stop-opacity="0"/></linearGradient>'
                + '<clipPath id="grafico-recorte"><rect x="0" y="0" width="' + (revelado * m.ancho) + '" height="' + m.alto + '"/></clipPath></defs>'
                + rejilla + etiquetas + '<g clip-path="url(#grafico-recorte)"><path d="' + area + '" fill="url(#grafico-relleno)"/>'
                + '<path class="grafico-linea" d="' + linea + '"/>' + marca + '</g>';
            if (visto === null) {
                burbuja.style.opacity = '0';
            } else {
                burbuja.innerHTML = '<span>' + meses[visto] + '</span><b>' + serie.datos[visto].texto + '</b>';
                const x = Math.min(Math.max(puntos[visto][0] - burbuja.offsetWidth / 2, 0), m.ancho - burbuja.offsetWidth);
                const y = Math.max(puntos[visto][1] - burbuja.offsetHeight - 12, 0);
                burbuja.style.transform = 'translate(' + x + 'px,' + y + 'px)';
                burbuja.style.opacity = '1';
            }
        }

        // Un solo cuadro por vez, aunque se pidan varios seguidos
        let animacion = 0;
        function animar(duracion, alAvanzar) {
            cancelAnimationFrame(animacion);
            let inicio = null;
            const paso = function (ms) {
                if (inicio === null) inicio = ms;
                const avance = Math.min((ms - inicio) / duracion, 1);
                alAvanzar(1 - Math.pow(1 - avance, 3));
                dibujar();
                if (avance < 1) animacion = requestAnimationFrame(paso);
            };
            animacion = requestAnimationFrame(paso);
        }

        caja.addEventListener('click', function (evento) {
            const boton = evento.target.closest('[data-serie]');
            if (!boton || Number(boton.dataset.serie) === actual) return;
            actual = Number(boton.dataset.serie);
            visto = null;
            revelado = 1;
            caja.querySelectorAll('[data-serie]').forEach(function (b) { b.setAttribute('aria-pressed', b === boton); });
            describir();
            const desde = alturas.slice();
            const hasta = normalizar(series[actual]);
            if (reducir) { alturas = hasta; dibujar(); return; }
            animar(700, function (k) {
                alturas = desde.map(function (v, i) { return v + (hasta[i] - v) * k; });
            });
        });

        const mirarEn = function (x) {
            const m = medidas();
            const relativo = (x - lienzo.getBoundingClientRect().left - m.izq) / (m.ancho - m.izq - m.der);
            visto = Math.min(Math.max(Math.round(relativo * (meses.length - 1)), 0), meses.length - 1);
            dibujar();
        };
        lienzo.addEventListener('pointermove', function (evento) { mirarEn(evento.clientX); });
        lienzo.addEventListener('pointerdown', function (evento) { mirarEn(evento.clientX); });
        lienzo.addEventListener('pointerleave', function () { visto = null; dibujar(); });
        lienzo.addEventListener('blur', function () { visto = null; dibujar(); });
        lienzo.addEventListener('keydown', function (evento) {
            if (evento.key !== 'ArrowLeft' && evento.key !== 'ArrowRight') return;
            const desde = visto === null ? meses.length - 1 : visto;
            const siguiente = desde + (evento.key === 'ArrowRight' ? 1 : -1);
            if (siguiente < 0 || siguiente >= meses.length) return;
            evento.preventDefault();
            visto = siguiente;
            dibujar();
        });
        if ('ResizeObserver' in window) new ResizeObserver(dibujar).observe(lienzo);

        describir();
        dibujar();
        if (!reducir) animar(1100, function (k) { revelado = k; });
    }
})();
