from apps.vps.models import Plan
#

def all_vps_plans():
    return Plan.objects.all()

def get_vps_plan_by_id(plan_id):
    return Plan.objects.filter(id=plan_id).first()
