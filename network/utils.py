
from network.models import _EarthChain_genesisId


def for_commitment(obj, genesis_obj, block):
    if genesis_obj._meta.object_name != 'Sonet' or (obj._meta.object_name in ['Sonet','Plugin','Node','Block','Validator'] or obj.id == _EarthChain_genesisId):
        # only certain models on sonet chain
        return True
    return False