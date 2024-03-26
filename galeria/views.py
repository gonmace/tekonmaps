from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Max
from django.views.generic import ListView, DetailView
from .forms import ImagesForm
from .models import Galeria, Imagen
from django.http import HttpResponse
from django.db.models import DateField
from django.db.models.functions import Trunc
from collections import OrderedDict

class GaleriaListView(ListView):
    model = Galeria
    template_name = 'galeria_list.html'
    context_object_name = 'galerias'

    def get_queryset(self):
        queryset = super().get_queryset().annotate(ultima_fecha_imagen=Max('imagenes__fecha_carga')).prefetch_related('imagenes')
        for galeria in queryset:
            ultima_imagen = galeria.imagenes.filter(fecha_carga=galeria.ultima_fecha_imagen).first()
            galeria.ultima_imagen = ultima_imagen
        return queryset


# @login_required  # Asegura que solo usuarios logueados puedan acceder a esta vista


def fileupload(request):
    if request.method == 'POST':
        form = ImagesForm(request.POST)
        if form.is_valid():
            galeria = form.cleaned_data['galeria']
            fecha_carga = form.cleaned_data['fecha_carga']
            images = request.FILES.getlist('images')  # Asegúrate de que el nombre del campo en el formulario HTML sea 'images'

            imagenes_a_crear = [Imagen(imagen=image, galeria=galeria, fecha_carga=fecha_carga) for image in images]

            # Usar bulk_create para mejorar la eficiencia
            Imagen.objects.bulk_create(imagenes_a_crear)

            return redirect('galeria:galeria_list')
        else:
            print(form.errors)
            return render(request, "500.html", {'form': form})
    else:
        form = ImagesForm()
    
    context = {'form': form}
    return render(request, "cargar.html", context)

def galeria_detalle(request, slug):
    galeria = get_object_or_404(Galeria, slug=slug)
    # Cambia 'order_by' para ordenar las fechas de manera descendente
    imagenes = Imagen.objects.filter(galeria=galeria).annotate(fecha=Trunc('fecha_carga', 'day', output_field=DateField())).order_by('-fecha')
    imagenes_por_fecha = OrderedDict()  # Usa OrderedDict si es necesario
    for imagen in imagenes:
        imagenes_por_fecha.setdefault(imagen.fecha, []).append(imagen)

    context = {
        'galeria': galeria,
        'imagenes_por_fecha': imagenes_por_fecha,
    }
    return render(request, 'galeria_detalle.html', context)

