from apps.vps.models import Plan, Duration, VPS
#

def all_vps_plans():
    return Plan.objects.all()

def get_vps_plan_by_id(plan_id):
    return Plan.objects.filter(uuid=plan_id).first()


def all_durations():

    return Duration.objects.all()

def get_duration_by_id(duration_id):

    return Duration.objects.filter(id=duration_id).first()

def user_vps_list(user):
    return VPS.objects.filter(user=user)

def get_vps_by_id(vps_id):
    return VPS.objects.filter(uuid=vps_id).first()
