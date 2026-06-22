from django import forms
from django.db import models

from docs.models import (
    DocumentoEsperado, EmpresaLink, PlantillaEstructura,
    SiteConfig, UserProfile,
)


class StyledFormMixin:
    """Aplica clases DaisyUI a los widgets (estilo iOS del proyecto)."""

    def _apply_styles(self):
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault('class', 'checkbox')
            elif isinstance(w, forms.Select):
                w.attrs.setdefault('class', 'select select-bordered w-full')
            elif isinstance(w, forms.Textarea):
                w.attrs.setdefault('class', 'textarea textarea-bordered w-full')
            else:
                w.attrs.setdefault('class', 'input input-bordered w-full')


class EmpresaLinkForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = EmpresaLink
        fields = ['nombre', 'link_admin', 'link_visitante']

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
                  'obligatorio', 'orden', 'activo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()


class UserCreateForm(StyledFormMixin, forms.Form):
    full_name = forms.CharField(label='Nombre completo', max_length=150)
    email = forms.EmailField(label='Correo')
    rol = forms.ChoiceField(label='Rol', choices=UserProfile.ROL_CHOICES,
                            help_text='Visitante = solo lectura; una función ITO = edita y '
                                      'auto-confirma su rol. Coordinador acepta borrados.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()

    def clean_email(self):
        from django.contrib.auth.models import User
        email = self.cleaned_data['email'].strip()
        if User.objects.filter(username__iexact=email).exists() or \
                User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con ese correo.')
        return email


class UserEditForm(StyledFormMixin, forms.Form):
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
