from django.db import IntegrityError
from django.test import TestCase

from usuarios.catalogo_permisos import CODIGOS_PERMISOS
from usuarios.models import PermisoIndividual, Rol, Usuario
from usuarios.permisos import (
    chequear_permiso, estado_permisos, filtrar_otorgables, limpiar_cache_permisos,
    permisos_efectivos, puede_otorgar_rol,
)


class PermisosEfectivosTests(TestCase):

    def setUp(self):
        self.rol = Rol.objects.create(nombre='Supervisor', permisos=['ver_usuarios', 'crear_usuarios'])
        self.usuario = Usuario.objects.create_user('juan', 'juan@test.com', 'clave-segura-123', rol=self.rol)

    def test_superusuario_tiene_todo(self):
        admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.assertEqual(permisos_efectivos(admin), CODIGOS_PERMISOS)

    def test_permisos_del_rol(self):
        self.assertTrue(chequear_permiso(self.usuario, 'ver_usuarios'))
        self.assertFalse(chequear_permiso(self.usuario, 'eliminar_usuarios'))

    def test_individual_concede_aunque_el_rol_no(self):
        PermisoIndividual.objects.create(usuario=self.usuario, permiso='eliminar_usuarios', concedido=True)
        self.assertTrue(chequear_permiso(self.usuario, 'eliminar_usuarios'))

    def test_individual_deniega_aunque_el_rol_si(self):
        PermisoIndividual.objects.create(usuario=self.usuario, permiso='ver_usuarios', concedido=False)
        self.assertFalse(chequear_permiso(self.usuario, 'ver_usuarios'))

    def test_sin_rol_no_tiene_nada(self):
        otro = Usuario.objects.create_user('pepe', None, 'x')
        self.assertEqual(permisos_efectivos(otro), frozenset())

    def test_inactivo_no_tiene_nada(self):
        self.usuario.is_active = False
        self.assertEqual(permisos_efectivos(self.usuario), frozenset())

    def test_permiso_inexistente(self):
        self.assertFalse(chequear_permiso(self.usuario, 'no_existe'))

    def test_codigos_viejos_del_rol_se_ignoran(self):
        self.rol.permisos = ['ver_usuarios', 'permiso_borrado_del_catalogo']
        self.rol.save()
        usuario = Usuario.objects.get(pk=self.usuario.pk)
        self.assertEqual(permisos_efectivos(usuario), {'ver_usuarios'})

    def test_cache_por_request_y_limpieza(self):
        self.assertFalse(chequear_permiso(self.usuario, 'eliminar_usuarios'))
        PermisoIndividual.objects.create(usuario=self.usuario, permiso='eliminar_usuarios', concedido=True)
        # Sigue cacheado hasta limpiar
        self.assertFalse(chequear_permiso(self.usuario, 'eliminar_usuarios'))
        limpiar_cache_permisos(self.usuario)
        self.assertTrue(chequear_permiso(self.usuario, 'eliminar_usuarios'))

    def test_una_sola_consulta_para_varios_chequeos(self):
        usuario = Usuario.objects.select_related('rol').get(pk=self.usuario.pk)
        # Si es revendedor (no tiene permisos) y sus permisos individuales: una vez, no por cada chequeo
        with self.assertNumQueries(2):
            for codigo in CODIGOS_PERMISOS:
                chequear_permiso(usuario, codigo)


class OtorgarPermisosTests(TestCase):

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        rol = Rol.objects.create(nombre='Gestor', permisos=['ver_usuarios', 'gestionar_permisos', 'ver_roles'])
        self.gestor = Usuario.objects.create_user('gestor', None, 'x', rol=rol)

    def test_superusuario_otorga_todo(self):
        self.assertEqual(filtrar_otorgables(CODIGOS_PERMISOS, self.admin), set(CODIGOS_PERMISOS))

    def test_no_se_otorga_lo_que_uno_no_tiene(self):
        resultado = filtrar_otorgables({'ver_usuarios', 'eliminar_usuarios'}, self.gestor)
        self.assertEqual(resultado, {'ver_usuarios'})

    def test_restringidos_solo_superusuario(self):
        # El gestor tiene 'ver_roles' pero es restringido: no lo puede dar
        self.assertEqual(filtrar_otorgables({'ver_roles'}, self.gestor), set())

    def test_puede_otorgar_rol(self):
        chico = Rol.objects.create(nombre='Chico', permisos=['ver_usuarios'])
        grande = Rol.objects.create(nombre='Grande', permisos=['ver_usuarios', 'eliminar_usuarios'])
        self.assertTrue(puede_otorgar_rol(chico, self.gestor))
        self.assertFalse(puede_otorgar_rol(grande, self.gestor))
        self.assertTrue(puede_otorgar_rol(grande, self.admin))

    def test_estado_permisos(self):
        empleado = Usuario.objects.create_user('empleado', None, 'x', rol=Rol.objects.create(
            nombre='Empleado', permisos=['ver_usuarios'],
        ))
        PermisoIndividual.objects.create(usuario=empleado, permiso='crear_usuarios', concedido=True)
        filas = {f['codigo']: f for _, grupo in estado_permisos(empleado, self.gestor) for f in grupo}

        self.assertEqual(filas['ver_usuarios']['origen'], 'rol')
        self.assertEqual(filas['crear_usuarios']['origen'], 'individual_si')
        self.assertEqual(filas['eliminar_usuarios']['origen'], 'ninguno')
        self.assertTrue(filas['ver_usuarios']['editable'])
        self.assertEqual(filas['eliminar_usuarios']['motivo_bloqueo'], 'sin_permiso_propio')
        self.assertEqual(filas['ver_roles']['motivo_bloqueo'], 'restringido')


class UsuarioModeloTests(TestCase):

    def test_username_y_email_unicos_sin_mayusculas(self):
        Usuario.objects.create_user('Juan', 'Juan@Test.com', 'x')
        with self.assertRaises(IntegrityError):
            Usuario.objects.create_user('juan', None, 'x')

    def test_email_se_guarda_en_minuscula_y_vacio_como_null(self):
        u1 = Usuario.objects.create_user('a', 'Mail@Test.COM', 'x')
        u2 = Usuario.objects.create_user('b', '', 'x')
        u3 = Usuario.objects.create_user('c', '', 'x')  # dos sin email no chocan
        self.assertEqual(u1.email, 'mail@test.com')
        self.assertIsNone(u2.email)
        self.assertIsNone(u3.email)

    def test_login_sin_distinguir_mayusculas(self):
        Usuario.objects.create_user('Juan', None, 'x')
        self.assertEqual(Usuario.objects.get_by_natural_key('JUAN').username, 'Juan')

    def test_iniciales_y_nombre(self):
        u = Usuario(username='jperez', first_name='Juan', last_name='Pérez')
        self.assertEqual(u.iniciales, 'JP')
        self.assertEqual(u.get_full_name(), 'Juan Pérez')
        self.assertEqual(Usuario(username='jperez').iniciales, 'JP')
