from django.contrib import admin
from .models import Stadium   # فرض می‌کنیم مدل Stadium توی models.py هست

@admin.register(Stadium)
class StadiumAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state")
