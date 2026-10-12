from django import forms
from django.db import models

from docs.models import (
    CarpetaRaiz, DocumentoEsperado, NextcloudConfig, PlantillaEstructura,
    SiteConfig, UserProfile,
)


class StyledFormMixin:
    """Aplica clases DaisyUI a los widgets (estilo iOS del proyecto)."""

    def _apply_styles(self):
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault('class', 'checkbox')
            elif isinstance(w, forms.RadioSelect):
                w.attrs.setdefault('class', 'radio radio-sm')
            elif isinstance(w, forms.Select):
                w.attrs.setdefault('class', 'select select-bordered w-full')
            elif isinstance(w, forms.Textarea):
                w.attrs.setdefault('class', 'textarea textarea-bordered w-full')
            else:
                w.attrs.setdefault('class', 'input input-bordered w-full')


class NextcloudConfigForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = NextcloudConfig
        fields = ['base_url', 'usuario', 'app_password', 'final_base', 'templates_path']
        labels = {
            'base_url': 'URL WebDAV',
            'usuario': 'Usuario de servicio',
            'app_password': 'App-password',
            'final_base': 'Base Docs. Finales',
            'templates_path': 'Ruta de plantillas',
        }
        widgets = {'app_password': forms.PasswordInput(render_value=True)}
        help_texts = {
            'base_url': 'Ej: https://cloud…/remote.php/dav/files/<usuario>/. Vacío = usa .env.',
            'usuario': 'Vacío = usa el de .env.',
            'app_password': 'Vacío = usa la de .env (no se muestra aquí por seguridad).',
            'final_base': 'Vacío = usa .env.',
            'templates_path': 'Vacío = usa .env.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()


class CarpetaRaizForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = CarpetaRaiz
        fields = ['codigo', 'orden', 'escanear', 'es_contratista',
                  'link_admin', 'link_visitante']
        labels = {
            'codigo': 'Código de empresa',
            'escanear': 'Escanear en Seguimiento',
            'es_contratista': 'Carpeta de contratista (solo lectura)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()


class SiteConfigForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SiteConfig
        fields = ['clave', 'link_admin', 'link_visitante', 'descripcion']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()


class PlantillaEstructuraForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PlantillaEstructura
        fields = ['nombre', 'descripcion']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()


class DocumentoEsperadoForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = DocumentoEsperado
        # `plantilla` no es editable por el usuario: la fija la vista según el contexto.
        fields = ['etapa', 'carpeta', 'nombre', 'codigo', 'tipo_esperado',
                  'rol_buscador', 'rol_tk_redline', 'rol_constructor',
                  'rol_ito', 'rol_ito_hse', 'rol_esp_electrico', 'rol_coordinador',
                  'obligatorio', 'galeria', 'orden', 'activo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()


class AccesoSeccionesMixin(forms.Form):
    """Casillas de acceso por sección del navbar («Seguimiento old» es solo del
    superusuario y no se asigna). Los sitios se asignan en Panel → Accesos."""
    acceso_contratista = forms.BooleanField(label='Acceso a Docs. Contratista', required=False)
    acceso_finales = forms.BooleanField(label='Acceso a Docs. Finales', required=False)
    acceso_proyectos = forms.BooleanField(
        label='Acceso a Seguimiento', required=False,
        help_text='Secciones que el usuario ve en el menú. Los sitios que puede ver se '
                  'asignan después (Accesos).')


class UserCreateForm(AccesoSeccionesMixin, StyledFormMixin, forms.Form):
    field_order = ['full_name', 'email', 'rol', 'acceso_contratista', 'acceso_finales',
                   'acceso_proyectos', 'modo_acceso', 'password']
    MODOS = [
        ('correo', 'Enviar un correo para que ingrese y cree su contraseña'),
        ('password', 'Definir la contraseña ahora'),
    ]
    modo_acceso = forms.ChoiceField(
        label='Primer ingreso', choices=MODOS, widget=forms.RadioSelect, required=False,
        initial='correo')
    password = forms.CharField(
        label='Contraseña', widget=forms.PasswordInput(render_value=False), required=False,
        min_length=8, help_text='Mínimo 8 caracteres. Solo si eliges definirla ahora.')
    full_name = forms.CharField(label='Nombre completo', max_length=150)
    email = forms.EmailField(label='Correo')
    rol = forms.ChoiceField(label='Rol', choices=UserProfile.ROL_CHOICES,
                            help_text='Visitante = solo lectura; una función ITO = edita y '
                                      'auto-confirma su rol. Coordinador acepta borrados.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault('acceso_proyectos', True)   # solo «Seguimiento» de entrada
        self._apply_styles()

    def clean(self):
        from django.contrib.auth.password_validation import validate_password
        cd = super().clean()
        cd['modo_acceso'] = cd.get('modo_acceso') or 'correo'
        if cd['modo_acceso'] == 'password':
            pwd = cd.get('password') or ''
            if not pwd:
                self.add_error('password', 'Escribe la contraseña o elige enviar el correo.')
            else:
                try:
                    validate_password(pwd)
                except forms.ValidationError as exc:
                    self.add_error('password', exc)
        return cd

    def clean_email(self):
        from django.contrib.auth.models import User
        email = self.cleaned_data['email'].strip()
        if User.objects.filter(username__iexact=email).exists() or \
                User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con ese correo.')
        return email


class UserEditForm(AccesoSeccionesMixin, StyledFormMixin, forms.Form):
    field_order = ['full_name', 'email', 'rol', 'acceso_contratista', 'acceso_finales',
                   'acceso_proyectos', 'is_active', 'password', 'requerir_password']
    full_name = forms.CharField(label='Nombre completo', max_length=150, required=False)
    email = forms.EmailField(label='Correo')
    rol = forms.ChoiceField(label='Rol', choices=UserProfile.ROL_CHOICES,
                            help_text='Visitante = solo lectura; una función ITO = edita y '
                                      'auto-confirma su rol. Coordinador acepta borrados.')
    is_active = forms.BooleanField(label='Activo', required=False)
    password = forms.CharField(
        label='Nueva contraseña',
        widget=forms.PasswordInput,
        required=False,
        min_length=8,
        help_text='Déjalo en blanco para mantener la contraseña actual.',
    )
    requerir_password = forms.BooleanField(
        label='Requerir nueva contraseña en el próximo ingreso',
        required=False,
        help_text='Borra la contraseña actual; el usuario la vuelve a crear al ingresar.',
    )

    def __init__(self, *args, **kwargs):
        self.user_pk = kwargs.pop('user_pk', None)
        super().__init__(*args, **kwargs)
        self._apply_styles()

    def clean_email(self):
        from django.contrib.auth.models import User
        email = self.cleaned_data['email'].strip()
        qs = User.objects.filter(
            models.Q(username__iexact=email) | models.Q(email__iexact=email))
        if self.user_pk:
            qs = qs.exclude(pk=self.user_pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe otro usuario con ese correo.')
        return email
