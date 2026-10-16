"""Errores de las plantillas que no rompen nada pero se VEN en la página."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

# {# ... #} es un comentario de UN renglón: partido en dos, Django lo muestra tal cual en la página
# (pasó al pie de Organizar contenido). Para varios renglones va {% comment %}...{% endcomment %}.
_COMENTARIO_PARTIDO = re.compile(r'\{#(?:(?!#\}).)*?\n', re.S)


class PlantillasTests(SimpleTestCase):

    def test_ningun_comentario_corto_ocupa_dos_renglones(self):
        partidos = []
        for plantilla in Path(settings.BASE_DIR).glob('**/templates/**/*.html'):
            if 'entorno' in plantilla.parts or 'node_modules' in plantilla.parts:
                continue
            texto = plantilla.read_text(encoding='utf-8')
            for encontrado in _COMENTARIO_PARTIDO.finditer(texto):
                partidos.append(f'{plantilla.relative_to(settings.BASE_DIR)}:{texto[:encontrado.start()].count(chr(10)) + 1}')
        self.assertEqual(partidos, [], 'Estos {# #} ocupan dos renglones y se verían en la página: usá {% comment %}.')
