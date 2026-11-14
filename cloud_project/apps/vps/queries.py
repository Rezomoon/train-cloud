from apps.vps.models import Plan
#

def all_vps_plans():
    return Plan.objects.all()