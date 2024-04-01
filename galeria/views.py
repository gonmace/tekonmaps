from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Max
from django.views.generic import ListView
from .forms import ImagesForm
from .models import Galeria, Imagen, Comentario
from django.contrib import messages
from django.db.models import DateField
from django.db.models.functions import Trunc
from collections import OrderedDict
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .serializers import GaleriaSerializer
from rest_framework.response import Response
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy

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


@login_required(login_url='login/')
def fileupload(request):
    if request.method == 'POST':
        form = ImagesForm(request.POST, request.FILES)
        if form.is_valid():
            galeria = form.cleaned_data['galeria']
            fecha_carga = form.cleaned_data['fecha_carga']
            comentario_texto = form.cleaned_data.get('comentario') 
            images = request.FILES.getlist('images')  # Asegúrate de que el nombre del campo en el formulario HTML sea 'images'

            imagenes_a_crear = [Imagen(imagen=image, galeria=galeria, fecha_carga=fecha_carga, user=request.user) for image in images]

            # Usar bulk_create para mejorar la eficiencia
            Imagen.objects.bulk_create(imagenes_a_crear)

            # Crear y guardar el comentario si existe alguno
            if comentario_texto:  # Verificar si hay algún comentario para guardar
                Comentario.objects.create(galeria=galeria, comentario=comentario_texto, fecha_carga=fecha_carga)

            # Añadir un mensaje de éxito
            messages.success(request, "Imágenes cargadas correctamente.")

            return redirect('galeria:galeria_list')
        else:
            messages.error(request, "Se encontraron errores en el formulario, por favor corrígelos.")
            return render(request, "cargar.html", {'form': form})
    else:
        form = ImagesForm()
    
    context = {'form': form}
    return render(request, "cargar.html", context)

def galeria_detalle(request, slug):
    galeria = get_object_or_404(Galeria, slug=slug)
    
    # Obtener imágenes y truncar la fecha
    imagenes = Imagen.objects.filter(galeria=galeria).annotate(fecha=Trunc('fecha_carga', 'day', output_field=DateField())).order_by('-fecha')
    
    # Obtener comentarios y truncar la fecha
    comentarios = Comentario.objects.filter(galeria=galeria).annotate(fecha=Trunc('fecha_carga', 'day', output_field=DateField())).order_by('-fecha')
    
    items_por_fecha = OrderedDict()
    
    # Combinar imágenes y comentarios en la misma estructura
    for item in list(imagenes) + list(comentarios):
        items_por_fecha.setdefault(item.fecha, {'imagenes': [], 'comentarios': []})
        if isinstance(item, Imagen):
            items_por_fecha[item.fecha]['imagenes'].append(item)
        elif isinstance(item, Comentario):
            items_por_fecha[item.fecha]['comentarios'].append(item)

    context = {
        'galeria': galeria,
        'items_por_fecha': items_por_fecha,
    }
    return render(request, 'galeria_detalle.html', context)

class CustomLoginView(LoginView):
    template_name = 'login.html'
    redirect_authenticated_user = True  # Redirige a los usuarios ya autenticados
    next_page = reverse_lazy('imgs/cargar') 


class UltimasImagenes(APIView):
    def get(self, request, slug_sitio):
        galeria = get_object_or_404(Galeria, slug=slug_sitio)
        serializer = GaleriaSerializer(galeria, context={'request': request})
        return Response(serializer.data)