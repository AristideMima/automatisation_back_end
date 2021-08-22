from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

UserAdmin.fieldsets = ((None, {'fields': ('username', 'password')}),(('Personal info'), {'fields': ('first_name', 'last_name', 'email',  'type')}),(('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser','groups', 'user_permissions')}),(('Important dates'), {'fields': ('last_login',)}))
admin.site.register(User, UserAdmin)
