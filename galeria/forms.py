from django import forms
from .models import Galeria, Imagen
from django.utils import timezone

class ImagesForm(forms.ModelForm):
    class Meta:
        model = Imagen
        fields = ['galeria', 'fecha_carga']

    def __init__(self, *args, **kwargs):
        super(ImagesForm, self).__init__(*args, **kwargs)
        self.fields['fecha_carga'].widget = forms.DateInput(attrs={
            'class': 'datepicker',
            'type': 'text',
        })
        self.fields['fecha_carga'].initial = timezone.now().date()
