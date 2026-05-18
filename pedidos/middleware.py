from django.http import HttpResponse


class HealthcheckMiddleware:
    """Answer Render health checks before host/HTTPS middleware.

    Render can call the health path through its internal network using an
    internal Host header. Public requests still go through the normal Django
    security stack; only /healthz/ is answered here.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
