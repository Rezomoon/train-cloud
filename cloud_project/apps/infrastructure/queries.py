from apps.infrastructure.models import OperatingSystem

# 

def all_active_operating_systems():
    return OperatingSystem.objects.filter(is_active=True)