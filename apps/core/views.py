from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


def readyz(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        return JsonResponse({"status": "ready"})
    except Exception:
        return JsonResponse({"status": "db_unavailable"}, status=503)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
