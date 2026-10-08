from django.conf import settings
from django.contrib import admin
from django.urls import path

admin.site.site_header = "Groupe – Suivi des marges"
admin.site.site_title = "Suivi des marges"
admin.site.index_title = "Administration"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
]
