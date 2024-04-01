from django import forms
from .models import Galeria, Imagen, Comentario
from django.utils import timezone

class ImagesForm(forms.ModelForm):
        # Aquí agregas un campo extra para el comentario, este no está vinculado directamente a un modelo
    comentario = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        model = Imagen
        fields = ['galeria', 'fecha_carga', 'comentario']

    def __init__(self, *args, **kwargs):
        super(ImagesForm, self).__init__(*args, **kwargs)
        self.fields['fecha_carga'].widget = forms.DateInput(attrs={
            'class': 'datepicker',
            'type': 'text',
        })
        self.fields['fecha_carga'].initial = timezone.now().date()

