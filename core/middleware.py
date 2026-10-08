class EnTetesSecuriteMiddleware:
    """En-têtes de sécurité non gérés par Django : désactive les API sensibles du navigateur."""

    PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reponse = self.get_response(request)
        reponse.headers.setdefault("Permissions-Policy", self.PERMISSIONS_POLICY)
        return reponse
