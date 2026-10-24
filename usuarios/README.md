# usuarios/

Todo lo relacionado con las personas que usan el sistema: quiénes son, cómo
entran y qué puede hacer cada una.

## Propósito

- Modelo de usuario propio, con datos completos pero genéricos (sirve para
  cualquier sistema).
- Roles (paquetes de permisos) y permisos individuales por usuario,
  completamente configurables.
- Login, logout, recuperación de contraseña y perfil propio.

## Archivos

| Archivo | Capa | Qué contiene |
|---|---|---|
| `catalogo_permisos.py` | Base | **Único lugar** donde se declaran los permisos del sistema (agrupados por módulo), cuáles son restringidos y los roles iniciales. |
| `models.py` | Base | `Usuario`, `Rol`, `PermisoIndividual`, `CodigoRecuperacion`. |
| `permisos.py` | Base | La lógica que decide si un usuario tiene un permiso y qué permisos puede otorgar otro. |
| `consultas.py` | Base | Qué usuarios puede ver cada uno (`usuarios_gestionables`), la búsqueda con filtros y los roles con su cantidad de usuarios. |
| `servicios.py` | Base | Lo que el sistema hace con los usuarios: crear, editar, asignar rol, activar/desactivar, eliminar, restablecer contraseña, guardar roles y permisos individuales, perfil propio, cambio de contraseña propia, recuperación de contraseña por mail y bloqueo de login. Lanza `OperacionNoPermitida` cuando una regla lo impide. |
| `backends.py` | Base | Permite iniciar sesión con el nombre de usuario **o** el email, sin distinguir mayúsculas. |
| `forms.py` | Presentación | Formularios: login, alta y edición de usuario (con sus secciones), perfil propio, cambiar contraseña, asignar contraseña, rol, recuperación (pedir código, código, contraseña nueva). |
| `middleware.py` | Presentación | `CambioPasswordObligatorioMiddleware`: si el usuario debe cambiar la contraseña, no lo deja usar el sistema hasta que lo haga. |
| `decoradores.py` | Presentación | `@requiere_permiso('codigo')` para proteger vistas: sin sesión → login, sin permiso → página 403. |
| `context_processors.py` | Presentación | Deja `permisos` en todos los templates: `{% if permisos.ver_usuarios %}`. Solo para mostrar u ocultar; el servidor chequea igual. |
| `views/` | Presentación | Vistas separadas por tema: `auth.py` (login/logout), `usuarios.py` (gestión de usuarios y sus permisos individuales), `roles.py` (roles), `perfil.py` (Mi perfil y cambiar contraseña), `recuperacion.py` (recuperar contraseña). |
| `urls.py` | Presentación | Rutas de la app (`/login/`, `/logout/`, `/usuarios/...`, `/roles/...`, `/mi-perfil/...`, `/recuperar/...`). |
| `templates/usuarios/` | Presentación | HTML de la app: `login`, `lista`, `detalle`, `formulario` (alta y edición), `restablecer_password`, `eliminar`, `permisos`, `_grilla_permisos` (grilla compartida por roles y permisos individuales) `_seccion_foto`, `roles/` (`lista`, `formulario`, `eliminar`) `perfil/` (`ver`, `editar`, `cambiar_password`), `recuperar/` (`solicitar`, `codigo`, `nueva`) y `emails/` (mail del código, en HTML y texto). |
| `admin.py` | Técnica | Configuración del admin de Django (`/admin/`), solo para el equipo técnico. |
| `management/commands/crear_roles_iniciales.py` | Técnica | Comando que crea los roles por defecto. |
| `migrations/` | Técnica | Historial de cambios de las tablas (lo genera Django). |
| `tests/` | Técnica | Pruebas automáticas (`python manage.py test usuarios`). |

## Modelos

| Modelo | Para qué |
|---|---|
| `Usuario` | La persona. Acceso (usuario, email, rol, activo), datos personales, contacto, domicilio, contacto de emergencia, datos laborales, notas internas y auditoría. |
| `Rol` | Paquete de permisos con nombre (ej: Supervisor). Se asigna al usuario. |
| `PermisoIndividual` | Excepción para un usuario puntual: le da o le quita un permiso sin importar su rol. |
| `CodigoRecuperacion` | Código de 6 dígitos que se manda por mail para recuperar la contraseña (se guarda cifrado, vence a los 15 minutos, 5 intentos como máximo). |

## Cómo se decide si alguien tiene un permiso

1. **Superusuario** → siempre sí.
2. **Usuario inactivo** → nunca.
   - **Revendedor** (tiene perfil de `Revendedor`) → nunca, tenga el rol o los permisos individuales que tenga. Ve su parte de reventa por ser revendedor, y nada de otros (ver `reventa/README.md`).
3. **Permiso individual** → si existe, manda (sí o no).
4. **Rol** → si no hay permiso individual, manda el rol.
5. Sin rol ni permiso individual → no.

Reglas para **otorgar** permisos (a un usuario o a un rol):

- Nadie puede dar un permiso que no tiene él mismo.
- Los permisos restringidos (los de roles) solo los puede dar un superusuario.
- Solo se puede asignar un rol si quien lo asigna tiene todos sus permisos.

## Roles iniciales

Se crean con `python manage.py crear_roles_iniciales`. Si ya existen no se
pisan, con una excepción: el **Administrador** (todos los permisos) recibe
siempre los permisos **nuevos** del catálogo (nunca se le quita ninguno).
También se puede correr desde Sistema → Herramientas → "Sincronizar roles".

| Rol | Permisos |
|---|---|
| Administrador | Todos |
| Supervisor | Ver, crear y editar usuarios, restablecer contraseñas |
| Consulta | Ver usuarios |
| Operador | Ninguno (solo su propio perfil) |

## Cómo agregar permisos de un módulo nuevo

1. En `catalogo_permisos.py`, sumar un bloque en `MODULOS_PERMISOS`.
2. Si alguno solo lo debe otorgar un superusuario, sumarlo a `PERMISOS_RESTRINGIDOS`.
3. En las vistas del módulo, chequear con `chequear_permiso(request.user, 'codigo')`.
4. Correr `python manage.py crear_roles_iniciales` para que el Administrador los reciba.

No hace falta migración: los permisos se guardan por código.

## Login

- Se entra con nombre de usuario o email.
- "Mantener la sesión iniciada": la sesión dura 2 semanas; si no se marca,
  se cierra al cerrar el navegador.
- Tras `LOGIN_INTENTOS_MAXIMOS` intentos fallidos (5 por defecto) para un
  mismo usuario desde una misma IP, se bloquea por `LOGIN_BLOQUEO_MINUTOS`
  (15 por defecto). Ambos se configuran en el `.env`.
- Cerrar sesión solo funciona por POST (botón del menú), para que un enlace
  externo no pueda desloguear a nadie.

## Gestión de usuarios

| Pantalla | Ruta | Permiso |
|---|---|---|
| Lista (buscar, filtrar por rol y estado) | `/usuarios/` | `ver_usuarios` |
| Nuevo usuario | `/usuarios/nuevo/` | `crear_usuarios` |
| Detalle | `/usuarios/<id>/` | `ver_usuarios` |
| Editar | `/usuarios/<id>/editar/` | `editar_usuarios` |
| Activar / desactivar | `/usuarios/<id>/estado/` (POST) | `editar_usuarios` |
| Asignar contraseña nueva | `/usuarios/<id>/contrasena/` | `restablecer_password_usuarios` |
| Eliminar | `/usuarios/<id>/eliminar/` | `eliminar_usuarios` |
| Permisos individuales | `/usuarios/<id>/permisos/` | `gestionar_permisos` |

Al crear un usuario:

- La **contraseña inicial puede ser cualquiera** (un carácter, igual al
  usuario, etc.): es solo para el primer ingreso. Con "Pedirle que elija su
  propia contraseña" (marcado por defecto) la persona pone la suya al
  entrar, y esa sí tiene que cumplir las reglas de seguridad.
- **Rol o permisos personalizados:** se elige un rol (paquete de permisos
  ya armado) o **"Personalizado"** cuando la persona necesita otra
  combinación. Un usuario personalizado no tiene rol: todo lo que puede
  hacer se lo marcás uno por uno en su pantalla de permisos. Al crearlo (o
  al quitarle el rol al editarlo) el sistema te lleva directo a esa
  pantalla, si tenés el permiso `gestionar_permisos`.

Reglas de seguridad:

- Los **superusuarios no aparecen** ni se pueden gestionar desde acá (solo
  desde `/admin/`): así nadie puede cambiarle el email al dueño y quedarse
  con su cuenta.
- **Nadie se gestiona a sí mismo** desde acá: los datos propios se editan en
  "Mi perfil". Así nadie se sube el rol ni se desactiva por error.
- Solo se puede **asignar un rol** si quien lo asigna tiene todos sus
  permisos. Mantener el rol que ya tenía siempre se permite.
- **Eliminar** es definitivo. Si el usuario tiene información asociada en
  otros módulos, el sistema no lo deja y sugiere desactivarlo.

## Roles y permisos individuales

| Pantalla | Ruta | Permiso |
|---|---|---|
| Lista de roles | `/roles/` | `ver_roles` |
| Nuevo rol | `/roles/nuevo/` | `crear_roles` |
| Ver / editar rol | `/roles/<id>/` | `ver_roles` para ver, `editar_roles` para guardar |
| Eliminar rol | `/roles/<id>/eliminar/` | `eliminar_roles` (sus usuarios pasan a permisos personalizados) |

- Los cambios en un rol se aplican de inmediato a todos los usuarios que lo tienen.
- Al editar un rol o los permisos de un usuario, los permisos que quien edita
  **no puede otorgar** aparecen bloqueados (con el motivo) y **quedan como
  estaban**: no se agregan ni se quitan.
- Si el usuario es **Personalizado** (sin rol), la pantalla de permisos
  simplemente muestra lo que tiene: todo se lo da quien lo gestiona.
- Si tiene rol, cada permiso muestra su origen: *Por su rol*,
  *Agregado a este usuario* o *Quitado a este usuario*. Si se marca igual que
  el rol, la excepción se borra sola. "Volver a los permisos del rol" borra
  todas las excepciones.

## Mi perfil

Cualquier usuario con sesión (no requiere permisos). Se entra tocando el
nombre abajo en el menú.

| Pantalla | Ruta |
|---|---|
| Ver mi perfil (datos + lo que puedo hacer en el sistema) | `/mi-perfil/` |
| Editar mis datos | `/mi-perfil/editar/` |
| Cambiar mi contraseña (pide la actual) | `/mi-perfil/contrasena/` |

- Cada uno edita lo personal: nombre, email, fecha de nacimiento, género,
  foto, contacto, domicilio y contacto de emergencia.
- **No** puede cambiar: usuario, rol, documento, puesto, área, fecha de
  ingreso (los ve como solo lectura). Las **notas internas no las ve**.
- Al cambiar la contraseña se cierran sus sesiones en otros dispositivos.

**Cambio obligatorio:** si un usuario tiene la marca "debe cambiar la
contraseña" (se marca al crearlo o al asignarle una contraseña nueva), al
entrar va directo a una pantalla sin menú para elegir una nueva y no puede
usar nada más del sistema hasta hacerlo (solo cerrar sesión).

## Recuperar contraseña

Desde el login: "¿Olvidaste tu contraseña?" (no requiere sesión).

| Paso | Ruta | Qué pasa |
|---|---|---|
| 1 | `/recuperar/` | Escribe su usuario o email. Se manda un código de 6 dígitos al email de la cuenta. |
| 2 | `/recuperar/codigo/` | Escribe el código. Puede pedir que se lo reenvíen. |
| 3 | `/recuperar/nueva/` | Elige la contraseña nueva (tiene 10 minutos). |

Seguridad:

- **No revela si la cuenta existe**: la respuesta es siempre "si los datos
  son correctos, te mandamos un código", y la pantalla del código se
  comporta igual en los dos casos.
- El código se guarda **cifrado**, vence a los **15 minutos**, admite **5
  intentos** y solo vale el último pedido.
- Como mucho **un pedido por minuto y 5 por hora** para lo mismo que se
  escribió (evita llenarle la casilla de mails a alguien).
- Usuarios inactivos o sin email no reciben nada (sin email → un
  administrador le asigna una contraseña nueva).
- Al guardar la contraseña nueva se **cierran todas sus sesiones**, se
  quita la marca de "debe cambiarla" y se levanta el bloqueo de login.

## Contenido actual

- Parte 1: modelos, permisos, roles iniciales, admin, tests.
- Parte 2: login, logout, bloqueo por intentos, decorador de permisos.
- Parte 3: gestión de usuarios.
- Parte 4: roles y permisos individuales.
- Parte 5: Mi perfil, cambiar contraseña, cambio obligatorio.
- Parte 6: recuperación de contraseña por mail.
