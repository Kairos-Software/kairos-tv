// "Separar en otra serie".
//   - Página de la serie (serie_detalle.html): Enter en "o a otra serie" usa
//     "Pasar a esa serie" (si no, el formulario usaría el primer botón: "Pasar"
//     a otra temporada).
//   - Vista previa (serie_separar.html): cuenta los tildados, "Tildar todos" /
//     "Destildar todos" y pregunta antes de separar.
document.querySelectorAll('[data-a-serie]').forEach(function (campo) {
    campo.addEventListener('keydown', function (evento) {
        if (evento.key !== 'Enter') return;
        evento.preventDefault();
        var boton = campo.parentElement.querySelector('[data-a-serie-boton]');
        if (boton) boton.click();
    });
});

(function () {
    var form = document.querySelector('form[data-separar]');
    if (!form) return;
    var cuenta = form.querySelector('[data-separar-cuenta]');
    var boton = form.querySelector('[data-separar-boton]');

    function casillas() { return Array.prototype.slice.call(form.querySelectorAll('input[name="elegido"]')); }
    function elegidos() { return casillas().filter(function (c) { return c.checked; }).length; }
    function contar() {
        var n = elegidos();
        cuenta.textContent = n;
        boton.disabled = !n;
        boton.lastChild.textContent = n === 1 ? ' Separar 1 capítulo' : ' Separar ' + n + ' capítulos';
    }

    form.addEventListener('change', contar);
    form.querySelectorAll('[data-separar-todos]').forEach(function (b) {
        b.addEventListener('click', function () {
            var tildar = b.dataset.separarTodos === '1';
            casillas().forEach(function (c) { c.checked = tildar; });
            contar();
        });
    });
    form.addEventListener('submit', function (evento) {
        var serie = form.querySelector('[name="a_serie"]').value.trim();
        var n = elegidos();
        if (!window.confirm('¿Pasar ' + (n === 1 ? '1 capítulo' : n + ' capítulos') + ' a la serie «' + serie + '»?')) {
            evento.preventDefault();
        }
    });
    contar();
})();
