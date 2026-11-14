

def for_commitment(obj, genesis_obj, block):
    if genesis_obj._meta.object_name == 'Wallet' and obj._meta.object_name in ['Tx','Wallet','Block']:
        # only transactions on wallet chain
        return True
    return False