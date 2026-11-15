from apps.vps.models import Plan, Duration
#

def all_vps_plans():
    return Plan.objects.all()

def get_vps_plan_by_id(plan_id):
    return Plan.objects.filter(uuid=plan_id).first()


def all_durations():

    return Duration.objects.all()

def get_duration_by_id(duration_id):

    return Duration.objects.filter(id=duration_id).first()