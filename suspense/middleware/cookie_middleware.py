class SameSiteNoneMiddleware:
    """
    Ensures Safari/iOS accepts cross-site cookies by forcing SameSite=None; Secure
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        for key, value in response.cookies.items():
            value['samesite'] = 'None'
            value['secure'] = True

        return response
