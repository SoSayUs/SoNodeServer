from django.db.models import Q
from accounts.models import UserPubKey
from utils.models import get_sigData, get_timeData


def for_commitment(obj, genesis_obj, block):
    if genesis_obj._meta.object_name == 'User':
        # last sig must belong to user when committing item to user chain
        sigData = get_sigData(obj, first_key=False)
        i_dt = get_timeData(obj, 'updated')
        if UserPubKey.objects.filter(id=sigData['pk'], User_obj=genesis_obj).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=i_dt)).exclude(signed={}).exists():
            return True
    else:
        return True
    
    return False