
from django.views.generic import TemplateView
from .models import Sitio
from django.db.models import Q


class Home(TemplateView):
    template_name = "home_page.html"

    def get_context_data(self, **kwargs):
        sitios = Sitio.objects.filter(avance__isnull=False).select_related('avance').all().values(
            'sitio',
            'entel_id',
            'nombre',
            'altura',
            'contratista',
            'lat',
            'lon',
            'ito',
            'avance__estado',
            'avance__excavacion',
            'avance__hormigonado',
            'avance__montado',
            'avance__empalmeE',
            'avance__porcentaje',
            'avance__fechaFin',
            'avance__comentario',
            )
        for sitio in sitios:
            if sitio['avance__excavacion'] is not None:
                sitio['avance__excavacion'] = sitio['avance__excavacion'].isoformat()
            else:
                sitio['avance__excavacion'] = ""

            if sitio['avance__hormigonado'] is not None:
                sitio['avance__hormigonado'] = sitio['avance__hormigonado'].isoformat()
            else:
                sitio['avance__hormigonado'] = ""
                
            if sitio['avance__montado'] is not None:
                sitio['avance__montado'] = sitio['avance__montado'].isoformat()
            else:
                sitio['avance__montado'] = ""
                
            if sitio['avance__empalmeE'] is not None:
                sitio['avance__empalmeE'] = sitio['avance__empalmeE'].isoformat()
            else:
                sitio['avance__empalmeE'] = ""
                
            if sitio['avance__fechaFin'] is not None:
                sitio['avance__fechaFin'] = sitio['avance__fechaFin'].isoformat()
            else:
                sitio['avance__fechaFin'] = ""
                                
                
        return {'sitios': list(sitios)}

# views.py
from django.http import JsonResponse


def buscar_sitio(request):
    query = request.GET.get('q', '')
    if query:
        sitios = Sitio.objects.filter(
            Q(sitio__icontains=query) |
            Q(nombre__icontains=query) |
            Q(entel_id__icontains=query)
        )
    else:
        sitios = Sitio.objects.none()

    sitios_data = list(sitios.values('sitio', 'nombre', 'lat', 'lon', 'entel_id'))  # Asegúrate de incluir 'entel_id' si quieres usarlo en el frontend.
    return JsonResponse(sitios_data, safe=False)
