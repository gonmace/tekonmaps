
from django.views.generic import TemplateView
from main.models import Sitio
from django.http import FileResponse, Http404
from .models import PdfFile
from django.conf import settings
import os

class Home(TemplateView):
    template_name = "home_page.html"

    def get_context_data(self, **kwargs):
        sitios = list(Sitio.objects.all().values('cod','comuna','altura', 'contratista', 'estado', 'lat', 'lon', 'ito', 'hormigonado', 'montado', 'empalmeE', 'descripcion', 'avance', 'fechaFin'))
         # Puedes ajustar los campos que necesitas en el 'only' según tu modelo.
                # Modificando los valores de 'hormigonado' y 'montado'
        for sitio in sitios:
            sitio['hormigonado'] = int(sitio['hormigonado'])
            sitio['montado'] = int(sitio['montado'])
            sitio['empalmeE'] = int(sitio['empalmeE'])
            
        return {'sitios': sitios,}

def download_pdf(request, title):
    try:
        pdf_file = PdfFile.objects.get(title=title)
        file_path = os.path.join(settings.MEDIA_ROOT, pdf_file.pdf.name)
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=pdf_file.pdf.name)
    except PdfFile.DoesNotExist:
        raise Http404("El archivo PDF no existe.")