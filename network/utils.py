
from django.db import models
from network.models import Node, DataPacket, Block, Blockchain, _OperationsChain_genesisId, universalChains, _EarthChain_genesisId
from utils.utils import (
    prnt, prntn, prntDebug, prntDebugn, request_items, get_self_node, process_received_dp, exists_in_worker,
    now_utc, string_to_dt, dt_to_string, value_is_none, get_sigData, is_id,  hash_upk_id, get_or_create_model,
    get_node, get_pointer_type
)
from utils.models import (
    e_brake, decompress_data, compress_data, get_operator_obj, downstream_broadcast, create_job, get_operatorData,
    connect_to_node, sign_post_header, sync_model
)
import django_rq
import datetime
import json
import random

def for_commitment(obj, genesis_obj, block):
    if genesis_obj._meta.object_name != 'Sonet' or (obj._meta.object_name in ['Sonet','Plugin','Node','Block','Validator'] or obj.id == _EarthChain_genesisId):
        # only certain models on sonet chain
        return True
    return False



def process_received_data(received_data, block_dict=None, downstream_worker=True, return_updated_count=False, return_updated_objs=False, return_updated_ids=False, check_consensus=True, skip_log_check=False, get_missing_blocks=True, override_completed=False, force_sync=False):
    prnt('---process_received_data now_utc:', now_utc(),'get_missing_blocks',get_missing_blocks,'check_consensus',check_consensus)
    from accounts.models import User, Notification, UserPubKey
    from transactions.models import Transaction
    from posts.models import scoreMe, Update, Post
    from utils.locked import verify_data, check_commit_data, get_signing_data, convert_to_dict, sign_obj, validate_obj, get_relevant_nodes, get_node_assignment, get_commit_data, check_block_contents, check_validation_consensus
    from network.models import Plugin, DataPacket, Block, Blockchain, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay, share_to_all, script_created_modifiable_models
    from network.utils import retrieve_missing_blocks
    from utils.models import get_data, set_model_attrs, save_sigs
    from utils.utils import data_sort_priority, get_model_prefix, get_dynamic_model, dynamic_bulk_create, dynamic_bulk_update, get_model, has_method, has_field, sigData_to_hash, is_locked, logError, seperate_by_type, find_or_create_chain_from_object, testing
    
    result = process_received_dp(received_data, 'process_received_data', skip_log_check=skip_log_check, override_completed=override_completed)
    prnt('reslut:',str(result)[:1000])
    if result and 'dp' in result:
        log = result['dp']
        received_data = result['data']
    elif result and 'data' in result:
        received_data = result['data']
        log = None
    else:
        received_data = []
        log = None

    if not force_sync and log and isinstance(log, models.Model):
        if log.func and 'process' not in log.func and not override_completed:
            return []

    synced_idens = []
    updated_objs = []
    updated_count = 0
    databaseUpdated = False
    if 'opBlock' in received_data and received_data['opBlock']:
        if 'opBlock_hash' in received_data:
            block_exists = Block.objects.filter(hash=received_data['opBlock_hash'], validated=True).exists()
        else:
            block_exists = Block.objects.filter(id=received_data['opBlock'], validated=True).exists()
        prnt('block_exists??1',block_exists)
        if not block_exists:
            if 'senderId' in received_data and received_data['senderId']:
                nodes = [received_data['senderId']]
            else:
                nodes = None
            request_items(requested_items=[received_data['opBlock']], get_missing_blocks=get_missing_blocks, nodes=nodes, downstream_worker=False)
            
    try:
        if isinstance(received_data, dict) and 'content' in received_data:
            content = received_data['content']
            if isinstance(content, dict) and 'content' in content: 
                content = content['content']
        else:
            content = received_data
        content = decompress_data(content)
        if isinstance(content, str):
            content = json.loads(content)
        elif isinstance(content, list):
            content = content
        prnt('next3')
        if not content:
            prnt('no data')
            if log:
                log.completed(note='no_data')
            return []
        objs = {}
        for i in content:
            try:
                objs[i['objType']].append(i['id'])
            except:
                objs[i['objType']] = [i['id']]
        self_node = get_self_node()
        if self_node and self_node.node_type == 'relay':
            prcs = share_to_all+['blc','val','chn']
            content = [i for i in content if isinstance(i,dict) and get_model_prefix(i['objType']) in prcs]
        prnt('aa0')
        prnt('stage2- data Len:',len(content))
        opBlock_dict = {'index':{}}
        userVotes = []
        validators = []
        received_invalids = []
        prnt('aa1')
        try:
            prnt('aa2')
            storedModels, not_found, not_valid = get_data(content, return_model=True, include_related=False, result_as_dict=True, verify_data=False)
            prnt('***get_data success')
        except Exception as e:
            prnt('*** err get_data',str(e))
        prnt('aa3')
        storedModels, not_found, not_valid = get_data(content, return_model=True, include_related=False, result_as_dict=True, verify_data=False)
        prnt('existing_objs-',len(storedModels))

        sorted_data = sorted(content, key=data_sort_priority) # data must be added in order due to dependancies
        prntDebug('--received_data len:',len(sorted_data))
        # get_model_prefix

        def save_to_db(bulk_update_items):
            prntDebug('save_to_db',len(bulk_update_items))
            nonlocal return_updated_objs
            nonlocal return_updated_ids
            nonlocal return_updated_count
            nonlocal updated_objs
            nonlocal updated_count
            nonlocal synced_idens
            created_items = []
            bulk_create_objs = [bulk_update_items[key]['obj'] for key in bulk_update_items if bulk_update_items[key]['is_new']]
            prnt('bulk_create_objs',bulk_create_objs)
            if bulk_create_objs:
                created_items = dynamic_bulk_create(current_model_type, items=bulk_create_objs, return_items=True, retrieve_missing=get_missing_blocks)
                prnt('created_items',[i.id for i in created_items])
                synced_idens += [i.id for i in created_items]
                prnt('proof:',[i['id'] for i in get_model(current_model_type).objects.filter(id__in=synced_idens).values('id')])
                if return_updated_objs:
                    updated_objs = updated_objs + created_items
                elif return_updated_ids:
                    updated_objs = updated_objs + [i.id for i in created_items]
                elif return_updated_count:
                    updated_count += len(created_items)
            prnt('bulk_update_items',bulk_update_items.keys())
            bulk_update_objs = [bulk_update_items[key]['obj'] for key in bulk_update_items if not bulk_update_items[key]['is_new'] and bulk_update_items[key]['updatedDB']]
            prnt('bulk_update_objs',bulk_update_objs)
            if bulk_update_objs:
                updated_items = dynamic_bulk_update(current_model_type, items=bulk_update_objs, return_items=True, retrieve_missing=get_missing_blocks)
                synced_idens += [i.id for i in updated_items]
                prnt('proof:',[i['id'] for i in get_model(current_model_type).objects.filter(id__in=synced_idens).values('id')])
                if return_updated_objs:
                    updated_objs = updated_objs + updated_items
                elif return_updated_ids:
                    updated_objs = updated_objs + [i.id for i in updated_items]
                elif return_updated_count:
                    updated_count += len(updated_items)
                if updated_items:
                    updated_items.clear()
            prnt('bulk_update_items',bulk_update_items)
            for key, value in bulk_update_items.items():
                prnt('item',value)
                save_sigs(value['sigs'])
            prnt('created_items',created_items)
            for obj in created_items:
                prnt('obj',obj)
                if bulk_update_items[obj.id]['is_new'] or bulk_update_items[obj.id]['updatedDB']:
                    if has_method(obj, 'boot'):
                        if not has_field(obj, 'proposed_modification') or not obj.proposed_modification:
                            prntDebug('booting obj', obj.id)
                            obj.boot()
            prnt('to_chain_items')
            to_chain_items = created_items + [i for i in bulk_update_items]
            if created_items:
                created_items.clear()
            bulk_update_items.clear()
            to_queue = {}
            for i in to_chain_items:
                if has_field(i, 'networkChain') and i.networkChain:
                    if i.networkChain not in to_queue:
                        to_queue[i.networkChain] = []
                    to_queue[i.networkChain].append(i)
            to_chain_items.clear()
            prnt('to_queue',to_queue)
            for chainId, objs in to_queue.items():
                blockchain = Blockchain.objects.filter(id=chainId).first()
                prnt('blockchain',blockchain)
                if blockchain:
                    blockchain.add_item_to_queue(objs)
            to_queue.clear()
            

        current_model_type = None
        bulk_update_items = {}
        for i in sorted_data:
            prntDebugn('ixi:',str(i)[:2000])
            if not current_model_type:
                current_model_type = i['objType']
            if current_model_type != i['objType'] or len(bulk_update_items) >= 1000:
                prnt('bulk_update_items p1', len(bulk_update_items))
                if bulk_update_items:
                    save_to_db(bulk_update_items)
                current_model_type = i['objType']
                bulk_update_items = {}
            valid_obj = False
            bad_commit = False
            val_err = '-'
            updatedDB = False
            if block_dict: # not doing anything currently
                hash = sigData_to_hash(i)
                receivedHash = [data['hash'] for iden, data in block_dict['data'].items() if iden == i['id'] and 'hash' in data][0]
                if receivedHash == hash:
                    hashMatch = True
                else:
                    hashMatch = False
            try:
                prnt('try')
                # check self_node that plugin and region are supported before sync for each item 

                userModels = ['User', 'Node', 'Transaction', 'UserPubKey']
                if i['objType'] in storedModels and i['id'] in storedModels[i['objType']] and storedModels[i['objType']][i['id']].signed:
                    val_err += 'a'
                    obj = storedModels[i['objType']][i['id']]
                    del storedModels[i['objType']][i['id']]
                    is_new = False
                else:
                    val_err += 'b'
                    obj, is_new = get_or_create_model(i['objType'], return_is_new=True, id=i['id'])
                
                if bad_commit:
                    prnt('bad_commit',bad_commit)
                elif i['objType'] == 'Sonet':
                    from network.models import Sonet
                    if not Sonet.objects.all().exists():
                        if verify_data(get_signing_data(i), i['signed']):
                            sonet, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                            new_sonet_valid = verify_data(get_signing_data(sonet), i['signed'])
                            prnt('new_sonet_valid',new_sonet_valid)
                            if new_sonet_valid:
                                from utils.locked import bytes_to_base64url
                                sonet.save(sig=bytes_to_base64url(sigs[-1].sig))
                                sonet.boot()
                                obj = sonet
                                save_sigs(sigs)
                    else:
                        val_err += '3'
                        obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                        val_err += f"_{valid_obj}_{updatedDB}_"
                elif i['objType'] in userModels:
                    val_err += 'A'
                    if obj._meta.object_name == 'User':
                        prnt('obj is user')
                        val_err += 'B'
                        if is_new:
                            val_err += '1'
                            prntDebug('is new')
                            if verify_data(get_signing_data(i), i['signed']):
                                val_err += '2'
                                prnt('create user')
                                user, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                                new_user_valid = verify_data(get_signing_data(user), i['signed'])
                                prnt('new_user_valid',new_user_valid)
                                if new_user_valid:
                                    user.save(bypass_verify=True)
                                    obj = user
                                    save_sigs(sigs)
                                    if has_method(obj, 'boot'):
                                        obj.boot()
                                    new = False
                        else:
                            val_err += 'C'
                            # check on UserVerification_obj here - isVerified is no longer used
                            if has_field(obj, 'isVerified') and obj.isVerified == False and i['isVerified'] == 'True' or has_field(obj, 'isVerified') and obj.isVerified == True and i['isVerified'] == 'False':
                                val_err += '1'
                                is_verified = obj.assess_verification()
                                obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                                if not is_verified:
                                    obj.isVerified = False
                                    # obj.save()
                            else:
                                val_err += '2'
                                obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                        val_err += 'D'
                        # check if username already taken
                        must_rename = False
                        u = User.objects.filter(username=i['username']).exclude(id=i['id']).first()
                        if u and u.lastpdate > string_to_dt(i['lastUpdate']):
                            u.alerts['must_rename'] = True
                            # u.save() # shuold broadcast?
                            bulk_update_items[u.id] = {'is_new':False,'updatedDB':True,'obj':u}

                        elif u:
                            must_rename = True
                        if must_rename:
                            obj.alerts['must_rename'] = True
                            # obj.save()
                    elif obj._meta.object_name == 'Transaction':
                        val_err += 'E'
                        # if 'ReceiverBlock_obj' in i and value_is_none(i['ReceiverBlock_obj']):
                        # receiverBlock = Block.objects.filter(Transaction_obj=self.Transaction_obj, Blockchain_obj__genesisId=self.Transaction_obj.ReceiverWallet_obj.id).exclude(id=self.Transaction_obj.senderBlockId).first()
                        # if receiverBlock:
                        #     obj.ReceiverBlock_obj = Block.objects.filter(id=i['receiverBlockId']).first()
                        if 'senderBlockId' in i and not value_is_none(i['senderBlockId']):
                            obj.SenderBlock_obj = Block.objects.filter(id=i['senderBlockId']).first()
                        val_err += '1'
                        obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                    elif obj._meta.object_name == 'Node':
                        val_err += 'F'
                        is_active = True
                        if obj.expelled_dt or i['expelled_dt']:
                            # handle disavowed claims appropriately
                            val_err += '1'
                            pass
                        if obj.suspended_dt and i['suspended_dt'] == 'None':
                            val_err += '2'
                            is_active = obj.assess_activity()
                        if is_active:
                            val_err += '3'
                            if verify_data(get_signing_data(i), i['signed']):
                                from utils.locked import bytes_to_base64url
                                val_err += '5'
                                if is_new:
                                    val_err += '6'
                                    prnt('create node')
                                    node, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                                    new_node_valid = verify_data(node, i['signed'], sigs)
                                    prnt('new_node_valid',new_node_valid)
                                    if new_node_valid:
                                        val_err += '7'
                                        node.save(bypass_lock=True, bypass_upk_block=True)
                                        obj = node
                                        save_sigs(sigs)
                                        is_new = False
                                else:
                                    val_err += '8'
                                    node, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                                    node_is_valid = verify_data(get_signing_data(node), i['signed'])
                                    prnt('node_is_valid',node_is_valid, 'updatedDB',updatedDB)
                                    if node_is_valid:
                                        val_err += '9'
                                        node.save(bypass_lock=True, bypass_upk_block=True)
                                        save_sigs(sigs)
                                        obj = node
                    
                    elif obj._meta.object_name == 'UserPubKey':
                        val_err += 'G'
                        prnt('obj is upk')
                        if is_new or not obj.Block_obj:
                            val_err += '1'
                            prntDebug('is new')

                            # sig_data = get_sigData(target_data, first_key=False)
                            # target_dt = sig_data['dt']

                            if verify_data(get_signing_data(i), i['signed'], upk_bypass=True):
                                val_err += '2'
                                valid_obj = True
                                prntDebug('creta upk')
                                if not User.objects.filter(id=i['User_obj']).exists():
                                    user = User(id=i['User_obj'], modlVer=1)
                                    user.save(bypass_verify=True)
                                # double check:
                                # make sure not injecting unauthorized super keys
                                # nodeId must correlate with keyType = 'node', upk.user must match node.user
                                # new upks are signed by older upk from same user, if no prev upk, must be created at same time as user
                                obj, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                                obj.save(bypass_verify=True)
                                save_sigs(sigs)
                                if has_method(obj, 'boot'):
                                    obj.boot()
                                new_upk_valid = verify_data(get_signing_data(obj), i['signed'])
                                prnt('new_upk_valid?',new_upk_valid)
                                is_new = False
                        else:
                            val_err += '3'
                            obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)

                elif not force_sync and is_locked(obj) and not has_field(obj, 'lastUpdate'):
                    valid_obj = True
                    val_err += 'X'
                else:
                    val_err += 'H'
                    try:
                        if 'func' in i and 'created' in i:
                            pos = f"{i['func']}_{i['created']}"
                        else:
                            pos = f"{i['created']}"
                        if pos not in opBlock_dict:
                            val_err += '1' # was causing issues with getting maintainers/intelligence/all
                        opBlock_dict['index'][i['id']] = pos
                        if has_field(obj, 'proposed_modification'):
                            val_err += '4'
                            obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                            if has_field(obj, 'Update_obj'):
                                obj.Update_obj = None
                            if has_field(obj, 'Validator_obj'):
                                obj.Validator_obj = None
                            if has_field(obj, 'Block_obj'):
                                obj.Block_obj = None
                            val_err += f"_{valid_obj}_{updatedDB}_"
                            mod_obj = get_dynamic_model(obj._meta.object_name, proposed_modification=obj.id)
                            if mod_obj and mod_obj.created <= string_to_dt(obj.lastUpdate):
                                prnt('delete1',mod_obj.id)
                                modded_chain = Blockchain.objects.filter(genesisId=mod_obj.id).first()
                                if modded_chain:
                                    super(get_model(modded_chain._meta.object_name), modded_chain).delete()
                                post = Post.objects.filter(pointerId=mod_obj.id).first()
                                if post:
                                    post.validated = False
                                    post.delete()
                                super(get_model(mod_obj._meta.object_name), mod_obj).delete()
                            Post.objects.filter(pointerId=obj.id, validated=True).update(validated=False, blockId=None)
                        else:
                            val_err += '3'
                            obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                            if has_field(obj, 'Update_obj'):
                                obj.Update_obj = None
                            if has_field(obj, 'Validator_obj'):
                                obj.Validator_obj = None
                            if has_field(obj, 'Block_obj'):
                                obj.Block_obj = None
                            val_err += f"_{valid_obj}_{updatedDB}_"

                        if valid_obj and obj._meta.object_name == 'UserVote':
                            userVotes.append(obj)

                    except Exception as e:
                        prntDebug('---fail5937564, val_err:',val_err,str(e),str(i)[:1000])
                        logError(e, code='482764', func='processed_received_data', extra=str(i)[:1000])
                if valid_obj and obj._meta.object_name == 'Validator':
                    val_err += 'I'
                    if obj not in validators:
                        if obj.validatorType != 'Block' or is_new:
                            val_err += 'a'
                            validators.append(obj)
                        elif obj.validatorType == 'Block':
                            val_err += 'b'
                            val_block = Block.objects.filter(id__in=obj.data).first()
                            if val_block and val_block.validated == None or val_block and override_completed or not val_block:
                                val_err += 'c'
                                validators.append(obj) # check_block_consensus()
                            elif val_block and val_block.validated:
                                val_err += 'd'
                                if 'unsupported_chain' in val_block.notes or 'problem_idens' in val_block.notes or 'found_idens' not in val_block.notes:
                                    validators.append(obj) # check_block_contents()
                                    val_err += 'e'
                if not valid_obj:
                    received_invalids.append({i['id']:val_err,'updatedDB':updatedDB})
                elif updatedDB:
                    if obj._meta.object_name == 'Region': # ParentRegion_obj must be saved before bulk update
                        val_err += 'J'
                        obj.save(sigs)
                        save_sigs(sigs)
                    else:
                        bulk_update_items[obj.id] = {'is_new':is_new,'updatedDB':updatedDB,'obj':obj, 'sigs':sigs}
                    synced_idens.append(obj.id)
                    
                elif has_field(obj, 'Validator_obj') and not obj.Validator_obj:
                    synced_idens.append(obj.id)
                elif override_completed:
                    synced_idens.append(obj.id)
                if not databaseUpdated and valid_obj and updatedDB:
                    databaseUpdated = True
                prnt('process data progress:',val_err,'len(bulk_update_items)',len(bulk_update_items))
            except Exception as e:
                prntDebug('-process data fail593, err:',val_err,str(e),str(i)[:1000])
                logError(e, code='09863', func='processed_received_data', extra={'err':str(e),'i':str(i)[:1000]})

        if received_invalids:
            # logError('received_invalids', code='4684', func='processed_received_data', extra={'received_invalids_count':len(received_invalids),'received_invalids':received_invalids[:500]})
            pass

        if bulk_update_items:
            prnt('bulk_update_items p2', len(bulk_update_items))
            save_to_db(bulk_update_items)
            
        prnt('stage3-',databaseUpdated)
        func = 'process_received_data'
        v_list = {key:None for key in synced_idens}
        validated_obj_idens = []
        prnt('validators:',len(validators))
        if validators:
            prnt('validators...')
            now = now_utc()
            chain_list = {}
            validIds = []
            
            prnt('vals step1a',validators)
            from network.models import Validator
            for validator in validators:
                if validator.validatorType != 'Block' and validator.is_valid:
                    for key, value in validator.data.items():
                        if key in synced_idens:
                            validIds.append(key)
                            v_list[key] = validator
                    if validator.networkChain not in chain_list:
                        blockchain = Blockchain.objects.filter(id=validator.networkChain).first()
                        if blockchain:
                            chain_list[validator.networkChain] = blockchain
                    if validator.networkChain in chain_list:
                        chain_list[validator.networkChain].add_item_to_queue(validator)                
            
            validated_idens = [i for i in validIds if not i.startswith(get_model_prefix('Update')) and not i.startswith(get_model_prefix('Notification'))]
            prnt('vals step2a',len(validated_idens))

            # masterData = get_relevant_nodes(dt=job_dt, blockchain=validator.networkChain, plugin_id=plugin_id, sublist='maintainer')
            # def get_opData(networkChain, data):
            #     if not networkChain in data:
            #         data[networkChain] = get_relevant_nodes(dt=job_dt, blockchain=networkChain, plugin_id=plugin_id, sublist='maintainer')
            #     return data[networkChain], data
            
            if validated_idens:
                q = 13
                for model_name, id_list in seperate_by_type(validated_idens).items():
                    prnt('model_name',model_name)
                    q = 131
                    to_queue = {}
                    objIdens = id_list
                    while objIdens:
                        q = 132
                        objs = list(get_dynamic_model(model_name, list=True, id__in=objIdens[:500]))
                        del objIdens[:500]
                        bulk_update = []
                        for obj in objs:
                            prnt('obj',obj)
                            try:
                                if obj.id not in v_list:
                                    prnt('obj not with validator list', obj.id)
                                else:
                                    if has_field(obj, 'Validator_obj'):
                                        if obj.Validator_obj and obj.Validator_obj.is_valid:
                                            prnt('previously validated', obj.id)
                                            validated_obj_idens.append(obj.id)
                                            # objs.remove(obj)
                                        else:
                                            prnt('else',obj.id)
                                            pos = None
                                            # if has_field(obj, 'func'):
                                            #     pos = f"{obj.func}_{dt_to_string(obj.created)}"
                                            # if pos and pos in opBlock_dict:
                                            #     # pos = opBlock_dict['index'][obj.id]
                                            #     target_opBlock = opBlock_dict[pos]
                                            # elif has_field(obj, 'created') and has_field(obj, 'blockchainId') and obj.blockchainId:
                                            #     opBlock_data = get_relevant_nodes(dt=string_to_dt(obj.created), blockchain=obj.blockchainId)
                                            #     opBlock_dict[pos] = {'node_ids':[n for n in opBlock_data['relevant_nodes']],'number_of_peers':opBlock_data['opData']['number_of_peers'],'relevant_nodes':opBlock_data['relevant_nodes']}
                                            #     opBlock_dict['index'][obj.id] = pos
                                            #     target_opBlock = opBlock_dict[pos]
                                            # else:
                                            target_opBlock = {}
                                            obj = validate_obj(obj=obj, pointer=obj, opBlock_data=target_opBlock, save_obj=False, update_pointer=False)
                                            if obj and obj.Validator_obj:
                                                obj.updated_on_node = now
                                                validated_obj_idens.append(obj.id)
                                                if has_field(obj, 'networkChain') and obj.networkChain:
                                                    if obj.networkChain not in to_queue:
                                                        to_queue[obj.networkChain] = []
                                                    to_queue[obj.networkChain].append(obj)
                                                
                                                if has_method(obj, 'upon_validation'):
                                                    obj.upon_validation()
                                                if has_method(obj, 'on_confirmation'):
                                                    i = obj.on_confirmation()
                                                    if i:
                                                        obj = i
                                                bulk_update.append(obj)
                            except Exception as e:
                                prnt('***ERROR*** 9898',str(e))
                        dynamic_bulk_update(model_name, items_field_update=['Validator_obj','updated_on_node'], items=bulk_update) 
                        q = 133
                        objs.clear()
                    if to_queue:
                        ...
                        # for chainId, objs in to_queue.items():
                        #     if chainId not in chain_list:
                        #         blockchain = Blockchain.objects.filter(id=chainId).first()
                        #         if blockchain:
                        #             chain_list[chainId] = blockchain
                        #     if chainId in chain_list:
                        #         chain_list[chainId].add_item_to_queue(objs)
                    to_queue.clear()
        if synced_idens:
            pointerIdens = [i for i in validated_obj_idens if not i.startswith(get_model_prefix('Update')) and not i.startswith(get_model_prefix('Notification')) and not i.startswith(get_model_prefix('BillText'))]
            prnt('vals step2.5a',len(pointerIdens))
            from posts.models import update_post
            while pointerIdens:
                q = 121
                prnt('pointerIdens[:1000]',len(pointerIdens[:500]),pointerIdens[:500])
                bulk_update = []
                fields = []
                posts = Post.all_objects.filter(pointerId__in=pointerIdens[:500]).exclude(validated=True)
                del pointerIdens[:500]
                prnt('posts len',posts.count())
                for p in posts:
                    try:
                        # if p.pointerId in opBlock_dict['index']: # was causing issues with getting maintainers/intelligence/all
                        #     pos = opBlock_dict['index'][p.pointerId]
                        #     target_opBlock = opBlock_dict[pos]
                        # else:
                        target_opBlock = {}
                        if validate_obj(obj=p, pointer=None, opBlock_data=target_opBlock, save_obj=False, update_pointer=False, verify_validator=False):
                            p.validated = True
                            p.updated_on_node = now
                            p, updated_fields = update_post(p=p, save_p=False)
                            bulk_update.append(p)
                            if updated_fields:
                                fields += [f for f in updated_fields if f not in fields]
                    except Exception as e:
                        prnt('***ERROR*** 7888',str(e))
                posts = None
                q = 122
                prnt('process data bulk_update posts',bulk_update)
                if bulk_update:
                    dynamic_bulk_update(model=Post, items_field_update=['validated','updated_on_node']+fields, items=bulk_update)
                q = 123
            q = 124
            updateIdens = [u for u in synced_idens if u.startswith(get_model_prefix('Update'))]
            prnt('vals step3a',len(updateIdens))
            if updateIdens:
                q = 14
                prnt('updateIdens',updateIdens)
                while updateIdens:
                    bulk_update = []
                    to_queue = {}
                    updates = Update.objects.filter(id__in=updateIdens[:500]).exclude(validated=True).order_by('id')
                    del updateIdens[:500]
                    for u in updates:
                        prnt('u',u)
                        try:
                            if u.id not in v_list:
                                prnt('obj not with validator list', u.id)
                            else:
                                if not is_locked(u, skip=['Validator_obj']):
                                    # if u.id in opBlock_dict['index']: # was causing issues with getting maintainers/intelligence/all
                                    #     pos = opBlock_dict['index'][u.id]
                                    #     target_opBlock = opBlock_dict[pos]
                                    # else:
                                    target_opBlock = {}
                                    u = validate_obj(obj=u, pointer=None, opBlock_data=target_opBlock, save_obj=False, verify_validator=False, update_pointer=False)
                                    if u and u.Validator_obj:
                                        u.validated = True
                                        u.updated_on_node = now
                                        validated_idens.append(u.id)
                                        if has_method(u, 'upon_validation'):
                                            u.upon_validation()
                                        if has_method(u, 'on_confirmation'):
                                            i = u.on_confirmation()
                                            if i:
                                                u = i
                                        bulk_update.append(u)
                                        if has_field(u, 'networkChain') and u.networkChain:
                                            if u.networkChain not in to_queue:
                                                to_queue[u.networkChain] = []
                                            to_queue[u.networkChain].append(u)
                                else:
                                    prnt('locked', convert_to_dict(u))
                        except Exception as e:
                            prnt('***ERROR*** 6787',str(e))
                    updates = None
                    q = 141
                    if bulk_update:
                        items = dynamic_bulk_update(model=Update, items_field_update=['validated', 'Validator_obj','updated_on_node'], items=bulk_update, return_items=True)
                        
                    if to_queue:
                        ...
                        # for chainId, objs in to_queue.items():
                        #     if chainId not in chain_list:
                        #         blockchain = Blockchain.objects.filter(id=chainId).first()
                        #         if blockchain:
                        #             chain_list[chainId] = blockchain
                        #     if chainId in chain_list:
                        #         chain_list[chainId].add_item_to_queue(objs)
                    to_queue.clear()

            q = 142
            from accounts.models import Notification
            notiIdens = [u for u in synced_idens if u.startswith(get_model_prefix('Notification'))]
            prnt('vals step3.5a',len(notiIdens))
            if notiIdens:
                q = 15
                prnt('notiIdens',notiIdens)
                bulk_update = []
                to_queue = {}
                notifications = Notification.objects.filter(id__in=notiIdens).exclude(validated=True)
                for n in notifications:
                    try:
                        # if not is_locked(n):
                        # if has_field(n, 'func'):
                        #     pos = f"{n.func}_{dt_to_string(n.created)}" # was causing issues with getting maintainers/intelligence/all
                        # if pos and pos in opBlock_dict:
                        #     # target_opBlock = opBlock_data[n.created]
                        #     # pos = opBlock_dict['index'][n.id]
                        #     target_opBlock = opBlock_dict[pos]
                        # elif has_field(n, 'created'):
                        #     opBlock_data = get_relevant_nodes(dt=string_to_dt(n.created), genesisId=_OperationsChain_genesisId)
                        #     opBlock_dict[pos] = {'node_ids':[n for n in opBlock_data['relevant_nodes']],'number_of_peers':opBlock_data['opData']['number_of_peers'],'relevant_nodes':opBlock_data['relevant_nodes']}
                        #     opBlock_dict['index'][n.id] = pos
                        #     target_opBlock = opBlock_dict[pos]
                        # else:
                        target_opBlock = {}
                        n = validate_obj(obj=n, pointer=None, opBlock_data=target_opBlock, save_obj=False, update_pointer=False)
                        if n and n.Validator_obj:
                            n.validated = True
                            n.updated_on_node = now
                            if has_method(n, 'upon_validation'):
                                n.upon_validation()
                            if has_method(n, 'on_confirmation'):
                                i = n.on_confirmation()
                                if i:
                                    n = i
                            bulk_update.append(n)
                            if has_field(n, 'networkChain') and n.networkChain:
                                if n.networkChain not in to_queue:
                                    to_queue[n.networkChain] = []
                                to_queue[n.networkChain].append(n)
                    except Exception as e:
                        prnt('***ERROR*** 8965',str(e))
                notifications = None
                prnt('bulk_update',bulk_update)
                if bulk_update:
                    dynamic_bulk_update(model=Notification, items_field_update=['validated', 'Validator_obj','updated_on_node'], items=bulk_update)
                    if to_queue:
                        ...
                        # for chainId, objs in to_queue.items():
                        #     if chainId not in chain_list:
                        #         blockchain = Blockchain.objects.filter(id=chainId).first()
                        #         if blockchain:
                        #             chain_list[chainId] = blockchain
                        #     if chainId in chain_list:
                        #         chain_list[chainId].add_item_to_queue(objs)
                    to_queue.clear()

            transIdens = [i for i in synced_idens if i.startswith(get_model_prefix('Transaction'))]
            prnt('vals step4a',len(transIdens))
            transactions = Transaction.objects.filter(id__in=transIdens).exclude(validated=True)
            for t in transactions:
                t.assess_validation()
            transactions = None

            chains = {}
            prnt('vals step6a')
            for m in script_created_modifiable_models:
                mIdens = [u for u in synced_idens if u.startswith(get_model_prefix(m))]
                if mIdens:
                    objs = get_dynamic_model(m, list=True, id__in=mIdens)
                    for o in objs:
                        chain, o, secondChain = find_or_create_chain_from_object(o)
                        if chain:
                            if chain not in chains:
                                chains[chain] = []
                            chains[chain].append(o)
                    objs = None
            prnt('vals step7a')
            if chains:
                for chain in chains:
                    chain.add_item_to_queue(chains[chain])
            val_block = None
            node_data = None
            for v in validators:
                prntDebug('v2',v)
                if v.validatorType == 'Block' and check_consensus:
                    # for key in v.data:
                    try:
                        if not val_block or v.jobId.startswith(get_model_prefix('Block')) and val_block.id != v.jobId:
                            val_block = Block.objects.filter(id=v.jobId).first()
                        prnt('val_block',val_block)
                        if val_block:
                            if v.id not in val_block.validations:
                                val_block.validations[v.id] = get_commit_data(v)
                                val_block.save()
                            if not val_block.validated and len(val_block.validations) >= val_block.get_required_validator_count() or not val_block.validated and val_block.networkChain == _OperationsChain_genesisId:
                                prev_block = Block.objects.filter(networkChain=val_block.networkChain, hash=val_block.prv_hash, validated=True).first()
                                if not prev_block:
                                    latest_block = val_block.Blockchain_obj.get_last_block(is_validated=True, do_not_return_self=True)
                                    if latest_block:
                                        start = latest_block.index + 1
                                    else:
                                        start = val_block.prv_hash
                                if not downstream_worker or testing():
                                    if not prev_block and val_block.index > 1:
                                        retrieve_missing_blocks(blockchain=val_block.Blockchain_obj, starting_point=start, items_to_get=2, downstream_worker=downstream_worker)
                                    check_validation_consensus(val_block, block_id=val_block.id, downstream_worker=downstream_worker, get_missing_blocks=get_missing_blocks)
                                else:
                                    queue = django_rq.get_queue('high')
                                    if not prev_block and val_block.index > 1:
                                        if not exists_in_worker('retrieve_missing_blocks', blockchain=val_block.Blockchain_obj, starting_point=start):
                                            queue.enqueue(retrieve_missing_blocks, blockchain=val_block.Blockchain_obj, starting_point=start, items_to_get=2, job_timeout=300, result_ttl=7200)
                                    if not exists_in_worker('check_validation_consensus', block_id=val_block.id):
                                        queue.enqueue(check_validation_consensus, val_block, block_id=val_block.id, broadcast_if_unknown=False, get_missing_blocks=get_missing_blocks, job_timeout=420, result_ttl=7200)
                            elif val_block.validated and not v.Block_obj:
                                if v.id in val_block.extraData and check_commit_data(v, val_block.extraData[v.id]) or v.id in val_block.data and check_commit_data(v, val_block.data[v.id]):
                                    prnt('adding val_block to val:',v.id,val_block)
                                    Validator.objects.filter(id=v.id).update(Block_obj=val_block)

                            if val_block.validated:
                                if 'unsupported_chain' in val_block.notes or 'problem_idens' in val_block.notes or 'found_idens' not in val_block.notes:
                                    try:
                                        if not node_data:
                                            operatorData = get_operatorData()
                                            node_data = operatorData['myNodes'][operatorData['local_nodeId']] # use operator_data instead of self_node to allow sync by node software while node is deactivated
                                            operatorData.clear()
                                        if 'chainData' in node_data['meta'] and 'supported' in node_data['meta']['chainData'] and node_data['meta']['chainData']['supported'] != '':
                                            if val_block.Blockchain_obj.genesisId in node_data['meta']['chainData']['supported'] or val_block.Blockchain_obj.genesisType in node_data['meta']['chainData']['supported']:
                                                if val_block.Blockchain_obj.genesisId != _OperationsChain_genesisId:
                                                    retrieve_missing=False
                                                    operatorData = get_operatorData()
                                                    node_data = operatorData['myNodes'][operatorData['local_nodeId']]
                                                    if 'do_sync_block_content' in node_data['meta']:
                                                        retrieve_missing = True
                                                    check_block_contents(val_block, retrieve_missing=retrieve_missing, update_items=True, log_missing=True, downstream_worker=downstream_worker)
                                    except Exception as e:
                                        prnt('err 5617', str(e))
                    except Exception as e:
                        prnt('***ERROR*** 4433',str(e))

            validators.clear()
        if userVotes: # not used
            prnt('userVotes...')
            postIds = []
            for v in userVotes:
                if v.postId not in postIds:
                    postIds.append(v.postId)
            posts = Post.objects.filter(id__in=postIds)
            for p in posts:
                scoreMe(p)
        if log:
            log.completed()
    except Exception as e:
        prnt('***fail process data 9374***',str(e))
        if log:
            log.completed(str(e))
    prnt('done process received data databaseUpdated',databaseUpdated)
    if return_updated_objs or return_updated_ids:
        return updated_objs
    elif return_updated_count:
        return updated_count
    return databaseUpdated         
            
def process_data_packet(received_json):
    prnt('--process_data_packet')
    from network.models import DataPacket, Block, Blockchain, Node, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay, get_node_assignment

    if e_brake(2):
        return 
    result = process_received_dp(received_json, 'process_data_packet')
    prnt('reslut:',str(result)[:1000])
    if result and 'dp' in result:
        dp = result['dp']
        received_json = result['data']
        if 'senderId' in received_json:
            node = Node.objects.filter(id=received_json['senderId']).first()
        elif 'headers' in received_json and 'Senderid' in received_json['headers']:
            node = Node.objects.filter(id=received_json['headers']['Senderid']).first()
        else:
            node = None
        if node:
            node.accessed()
        
    elif result and 'data' in result:
        received_json = result['data']
        dp = None
    else:
        received_json = []
        dp = None

    if dp and isinstance(dp, models.Model):
        if 'completed' in dp.func:
            prnt('previously completed')
            return 'previously completed'

    if 'opBlock_id' in received_json:
        prnt('opBlock_id1')
        opBlock = Block.objects.filter(id=received_json['opBlock_id']).first()
        prnt('opBlock_id2',opBlock)
        if not opBlock:
            prnt('opBlock_id3')
            create_job(retrieve_missing_blocks, job_timeout=200, worker='high', genesisId=_OperationsChain_genesisId, target_node=received_json['senderId'], starting_point=received_json['opBlock_id'])
        elif not opBlock.validated or opBlock.hash != received_json['opBlock_hash'] and opBlock.validated:
            prnt('opBlock_id4')
            create_job(send_missing_blocks, job_timeout=60, worker='main', blockchain=opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=received_json['senderId'])
        elif 'opBlock_not_latest' in received_json:
            prnt('opBlock_id5')
            pass
        elif opBlock and opBlock.index != opBlock.Blockchain_obj.chain_length:
            prnt('opBlock_id6')
            sent_dt = string_to_dt(received_json['dt'])
            latest_opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=sent_dt, validated=True).order_by('-index', 'created').first()
            prnt('opBlock_id7 latest_opBlock',latest_opBlock)
            if latest_opBlock and latest_opBlock != opBlock:
                prnt('opBlock_id8')
                create_job(send_missing_blocks, job_timeout=60, worker='main', blockchain=latest_opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=received_json['senderId'])
    else:
        prnt('opBlock not included')
    
    updated = False
    prnt('next1')
    if 'type' in received_json and received_json['type'] == 'DataPacket':
        sender_node = Node.objects.filter(id=received_json['senderId']).first()
        if sender_node == get_self_node():
            if dp:
                dp.completed()
        else:
            if dp:
                updated = process_received_data(dp, return_updated_count=True, skip_log_check=True)
            else:
                updated = process_received_data(received_json, return_updated_count=True, skip_log_check=True)
        prnt('done process datapacket, updated:',updated)



def rebroadcast_dp(dp_id, override_completed=False):
    prnt('-rebroadcast_dp',dp_id)
    if e_brake(2):
        return 
    
    from network.models import Node, DataPacket, universalChains
    dp = DataPacket.objects.filter(id=dp_id).first()

    if ('completed' in dp.func or 'chunked' in dp.func) and not override_completed:
        prnt('dp.func',dp.func)
        return

    queue = django_rq.get_queue("main")
    if not exists_in_worker('process_data_packet', queue=queue, id=dp_id):
        prnt('add to main worker')
        queue.enqueue(process_data_packet, dp_id, job_timeout=240, result_ttl=3600)

    if dp.rebroadcast_dt and dp.rebroadcast_dt > now_utc() - datetime.timedelta(hours=2):
        prnt('already broadcast')
        return

    if dp.headers['Senderid'] != get_operator_obj('self_nodeId'):
        if 'chainId' not in dp.headers or dp.headers['chainId'] != get_operator_obj('self_nodeId'):
            result = process_received_dp(dp, 'process_data_packet', override_completed=True)
            prnt('reslut:',str(result)[:1000])
            if result and 'dp' in result:
                received_json = result['data']
            elif result and 'data' in result:
                received_json = result['data']
            else:
                received_json = []
            if received_json:


                from utils.locked import get_broadcast_list
                if 'Seedid' in dp.headers and dp.headers['Seedid'] != get_operator_obj('self_nodeId'):
                    prnt('dp.headers',dp.headers)
                    include_relays = False
                    if 'chainId' in dp.headers and dp.headers['chainId'] in universalChains:
                        include_relays = True
                    broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], all_nodes=True, dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Chainid'], plugin_id=dp.headers['Pluginid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays)
                    downstream_broadcast(broadcast_list, 'network/receive_data_packet', received_json, headers=dp.headers, skip_self=True)
                    dp.rebroadcast_dt = now_utc()
                    dp.save()

                else: # shouldnt ever be used
                    prnt('rebroadcast_dp_Packet-Id',dp.headers['Packet-Id'])
                    # broadcast_list = get_broadcast_list(packet_id, dt=now, region_id=self.chainId, seed_nodes=[self_node_id])
                    broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Chainid'], plugin_id=dp.headers['Pluginid'], seed_nodes=[dp.headers['Senderid']])
                    downstream_broadcast(broadcast_list, 'network/receive_data_packet', received_json, headers=dp.headers, exclude=[dp.headers['Senderid']], skip_self=True)
                    dp.rebroadcast_dt = now_utc()
                    dp.save()

def rebroadcast_block(dp_id):
    prnt('-rebroadcast_block',dp_id)
    if e_brake(2):
        return 
    
    dp = DataPacket.objects.filter(id=dp_id).first()

    if 'completed' in dp.func or 'chunked' in dp.func:
        prnt('dp.func',dp.func)
        return
        
    def process_blocks(dp):
        prnt('-process_blocks',dp.headers['Index'])
        if dp.headers.get("Genesisid") == _OperationsChain_genesisId:
            queue = django_rq.get_queue('high')
            worker = 'high'
        else:
            queue = django_rq.get_queue('main')
            worker = 'main'
        if not exists_in_worker('process_received_blocks', queue=queue, id=dp.id):
            prnt(f'add worker job {worker}')
            queue.enqueue(process_received_blocks, dp.id, job_timeout=500, result_ttl=3600)
            
    if dp.rebroadcast_dt and dp.rebroadcast_dt > now_utc() - datetime.timedelta(hours=2):
        prnt('already broadcast')
        process_blocks(dp)
        return
    
    if 'Rebroadcast' in dp.headers and str(dp.headers['Rebroadcast']) == 'True':
        broadcast_list = {}
        from utils.locked import get_broadcast_list, get_relevant_nodes, get_node_assignment
        prnt("dp.headers",dp.headers)
        prnt('Rebroadcast...')

        result = process_received_dp(dp, 'process_blocks', override_completed=True)
        if result and 'dp' in result:
            prnt('dp in result')
            received_json = dp.data
        elif result and 'data' in result:
            prnt('data in result')
            received_json = result['data']
            # dp = None
        else:
            prnt('no dp or data in result')
            received_json = []
            # dp = None
        if received_json:
            prnt('received_json')
            if dp.headers['Genesisid'] == _OperationsChain_genesisId:
                # check if already received latest opBlock, if so, consult get_node_assignment and keep lowest on list. rebroadcast lowest block on current packet_id
                current_blocks = Block.objects.filter(networkChain=dp.headers['Blockchainid'], index=int(dp.headers['Index'])).exclude(validated=False).defer('data','extraData','notes')
                prnt('current_blocksxxx',current_blocks)
                if current_blocks:
                    prnt('block.CreatorNode_obj.id,',[block.CreatorNode_obj.id for block in current_blocks])
                
                if string_to_dt(dp.headers['Blockdt']) > now_utc():
                    is_good = False
                    prev_block = Block.objects.filter(networkChain=dp.headers['Blockchainid'], hash=dp.headers['Prevhash'], validated=True).values('id').first()
                    latest_block = Block.objects.filter(networkChain=dp.headers['Blockchainid'], validated=True).values('id').order_by('-index').first()
                    prnt('prev_block x',prev_block)
                    if prev_block and latest_block:
                        if prev_block['id'] == latest_block['id']:
                            is_good = True
                    if not is_good:
                        if 'hash_history' in received_json:
                            prnt("received_json['hash_history']",len(received_json['hash_history']))
                            hash_list = received_json['hash_history'].copy()

                            prnt('hash_list len:',len(hash_list))
                            local_hash_history = [i['hash'] for i in Block.objects.filter(Blockchain_obj=dp.headers['Blockchainid'], hash__in=hash_list).exclude(validated=False).values('hash')]
                            prnt('local_hash_history len:',len(local_hash_history))
                            missing_hashes = [i for i in hash_list if i not in local_hash_history]
                            prnt('missing_hashes hashes',missing_hashes)
                            if missing_hashes:
                                if not retrieve_missing_blocks(genesisId=dp.headers['Genesisid'], target_node=dp.headers['Packet-Creator'], starting_point=missing_hashes[0], items_to_get=len(missing_hashes)):
                                    prnt('failed to retrieve prior blocks 9434',missing_hashes)
                                    note = 'missing_prior_blocks1'
                                    for block in current_blocks:
                                        block.is_not_valid(note=note, mark_strike=False)
                                        creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=False)
                                        if get_operator_obj('self_nodeId') in validator_list:
                                            from utils.locked import validate_block
                                            is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
                                    if dp:
                                        dp.completed(note)
                                    return False


                prnt("dp.headers['Seedid']",dp.headers['Seedid'])
                if current_blocks and 'Seedid' in dp.headers and any(block.CreatorNode_obj.id != dp.headers['Seedid'] for block in current_blocks):
                    prnt('pz1')
                    new_block = None
                    for block in current_blocks:
                        block_dt = block.DateTime
                        opBlock_data = get_relevant_nodes(dt=(block.DateTime-datetime.timedelta(minutes=20)), genesisId=block.Blockchain_obj.genesisId, include_relays=True)
                        creator_nodes, validator_nodes = get_node_assignment(block, opBlock_data=opBlock_data, full_creator_list=True)
                        prnt('creator_nodes',creator_nodes)
                        new_index = 1
                        current_index = 0
                        try:
                            new_index = creator_nodes.index(dp.headers['Seedid'])
                            current_index = creator_nodes.index(block.CreatorNode_obj.id)
                        except Exception as e:
                            prnt('err xa',str(e))
                            if block.CreatorNode_obj.id in creator_nodes and dp.headers['Seedid'] not in creator_nodes:
                                new_index = 1
                                current_index = 0
                            elif dp.headers['Seedid'] in creator_nodes and block.CreatorNode_obj.id not in creator_nodes:
                                new_index = 0
                                current_index = 1
                            elif dp.headers['Seedid'] not in creator_nodes and block.CreatorNode_obj.id not in creator_nodes:
                                node = Node.objects.filter(id=dp.headers['Seedid'], expelled_dt=None).first()
                                if node and node.activated_dt < block.CreatorNode_obj.activated_dt:
                                    new_index = 0
                                    current_index = 1
                                else:
                                    new_index = 1
                                    current_index = 0
                            prnt('current_index',current_index)
                            prnt('new_index',new_index)
                        if new_index < current_index:
                            prnt('replace current block')
                            # keep new block, delete current
                            block.delete()
                            if not new_block:
                                if 'block_list' in received_json:
                                    block_list = decompress_data(received_json['block_list'])
                                    try:
                                        block_list = json.loads(block_list)
                                    except:
                                        pass
                                    for b in block_list:
                                        try:
                                            block_dict = json.loads(b['block_dict'])
                                        except:
                                            block_dict = b['block_dict']
                                        if block_dict['id'] in dp.headers['Blockid']:
                                            blockchain = Blockchain.objects.filter(genesisId=dp.headers['Genesisid']).first()
                                            new_block = blockchain.create_block(block_dict=block_dict)
                            
                            broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], plugin_id=dp.headers['Pluginid'], seed_nodes=[dp.headers['Seedid']], include_relays=True, peer_count=10, loop=False, all_nodes=True)
                            received_data = received_json.copy()
                            headers = dp.headers
                            # del received_data['headers']
                        elif current_index < new_index:
                            prnt('keep current block')
                            # keep current block
                            competing_dp = DataPacket.objects.filter(Node_obj__id=block.CreatorNode_obj.id, func__contains=f"received_blocks:{block.id}").first()
                            result = process_received_dp(competing_dp, 'process_blocks', override_completed=True, skip_log_check=True)
                            if result and 'dp' in result:
                                prnt('rebroadcast')
                                log = result['dp']
                                received_data = log.data.copy()
                                headers = dp.headers
                                broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], plugin_id=dp.headers['Pluginid'], seed_nodes=[dp.headers['Seedid']], include_relays=True, peer_count=10, loop=False, all_nodes=True)
                                # del received_data['headers']
                            else:
                                prnt('no dp')
                                if dp:
                                    dp.completed('received_blocks_non_winner2')
                                return False
                            received_json = {}
                        
                    if not block or now_utc() < (string_to_dt(block_dt) - datetime.timedelta(minutes=10)):
                        prnt('wait to process block')
                        received_json = {} # do not begin validations until 10 minutes from block.DateTime
                    else:
                        process_blocks(dp)
                    if dp.headers['Seedid'] != get_operator_obj('self_nodeId'):
                        downstream_broadcast(broadcast_list, 'network/receive_blocks', received_data, headers=headers, skip_self=True)
                    dp.rebroadcast_dt = now_utc()
                    dp.save()
                elif 'Seedid' in dp.headers:
                    prnt('pz2')
                    received_data = received_json.copy()
                    headers = dp.headers
                    include_relays = False
                    if 'Genesisid' in headers and headers['Genesisid'] in universalChains:
                        include_relays = True
                    if 'Validators-Only' in dp.headers and dp.headers['Validators-Only'] == 'True':
                        prnt('validators only')
                        broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], loop=True, all_nodes=False, dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], plugin_id=dp.headers['Pluginid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays)
                    else:
                        prnt('not validators only')
                        broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], plugin_id=dp.headers['Pluginid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays, peer_count=10, loop=False, all_nodes=True)
                    # del received_data['headers']
                    
                    prnt('now_utc() < (block.DateTime + datetime.timedelta(minutes=1))')
                    prnt(now_utc())
                    if current_blocks:
                        prnt((current_blocks[0].DateTime + datetime.timedelta(minutes=1)))
                    if current_blocks and now_utc() < (current_blocks[0].DateTime - datetime.timedelta(minutes=10)):
                        prnt('pz3')
                        received_json = {} # do not begin validations until 10 minutes from block.DateTime
                    else:
                        process_blocks(dp)
                    downstream_broadcast(broadcast_list, 'network/receive_blocks', received_data, headers=headers)
                    dp.rebroadcast_dt = now_utc()
                    dp.save()
                    prnt('blockblocks,',current_blocks)
            elif 'Seedid' in dp.headers and dp.headers['Seedid'] != get_operator_obj('self_nodeId'):
                process_blocks(dp)
                include_relays = False
                if 'Genesisid' in dp.headers and dp.headers['Genesisid'] in universalChains:
                    include_relays = True
                prnt('dp.headers',dp.headers)
                if 'Validators-Only' in dp.headers and dp.headers['Validators-Only'] == 'True':
                    prnt('validators only')
                    opBlock_data = get_relevant_nodes(dt=string_to_dt(dp.headers['Dt']), blockchain=dp.headers['Blockchainid'], strings_only=True, first_block_override=True)

                    creator_nodes, validator_list = get_node_assignment(func=dp.headers['Packet-Id'],dt=string_to_dt(dp.headers['Dt']), chainId=dp.headers['Blockchainid'], plugin_id=dp.headers['Pluginid'], opBlock_data=opBlock_data)
                    broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], relevant_nodes=validator_list, loop=True, all_nodes=False, dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], plugin_id=dp.headers['Pluginid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays, opBlock_data=opBlock_data)
                else:
                    prnt('not validators only')
                    broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], seed_nodes=[dp.headers['Seedid']], plugin_id=dp.headers['Pluginid'], include_relays=include_relays)
                downstream_broadcast(broadcast_list, 'network/receive_blocks', received_json, headers=dp.headers, skip_self=True)
                dp.rebroadcast_dt = now_utc()
                dp.save()
            else:
                prnt('else1')
                process_blocks(dp)
    else:
        prnt('else2')
        process_blocks(dp)


def process_received_blocks(received_json, get_missing_blocks=True, resend_missing_blocks=True, return_result=False, force_check=False, rebroadcast=True, downstream_worker=True, override_completed=False):
    prntn('--process_received_blocks now_utc:',now_utc())
    from network.models import Node, DataPacket, Block, Blockchain, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay, universalChains
    from utils.locked import get_broadcast_list, check_validation_consensus, get_relevant_nodes, get_node_assignment, hash_obj_id, get_signing_data
    prnt()
    if e_brake(2):
        return 
    
    result = process_received_dp(received_json, 'process_blocks', override_completed=override_completed)
    if result and 'dp' in result:
        prnt('x1')
        log = result['dp']
        received_json = result['data']
        if 'senderId' in received_json:
            node = Node.objects.filter(id=received_json['senderId']).first()
        elif 'headers' in received_json and 'Senderid' in received_json['headers']:
            node = Node.objects.filter(id=received_json['headers']['Senderid']).first()
        else:
            node = None
        if node:
            node.accessed()
    elif result and 'data' in result:
        prnt('x2')
        received_json = result['data']
        log = None
    else:
        prnt('x3')
        received_json = []
        log = None
    completed = False
    prntn('received_json snippet:',str(received_json)[:4000])
    if not received_json or 'genesisId' not in received_json:
        if log:
            log.completed('no_data')
        return completed

    if 'headers'in received_json and 'Packet-Creator' in received_json['headers']:
        if received_json['headers']['Packet-Creator'] == get_operator_obj('self_nodeId') and Node.objects.filter(activeNode=True).count() > 10:
            if log:
                log.completed('self_seeded')
            return completed
    packet_creator = None
    if 'headers'in received_json and 'Packet-Creator' in received_json['headers']:
        packet_creator = received_json['headers']['Packet-Creator']
    sender_node = received_json['senderId']
    if 'opBlock' in received_json and received_json['opBlock']:
        if 'opBlock_hash' in received_json:
            opBlock = Block.objects.filter(hash=received_json['opBlock_hash']).first()
        else:
            opBlock = Block.objects.filter(id=received_json['opBlock']).first()
        prnt('opBlock??',opBlock)
        if not opBlock:
            retrieve_missing_blocks(genesisId=_OperationsChain_genesisId, target_node=packet_creator if packet_creator else sender_node, starting_point=received_json['opBlock'])
            opBlock = Block.objects.filter(id=received_json['opBlock']).first()
            if not opBlock:
                if log:
                    log.completed('missing_opBlock')
                return completed
        elif not opBlock.validated and opBlock.hash == received_json['opBlock_hash']:
            block_is_valid, consensus_found, validations = check_validation_consensus(opBlock, block_id=opBlock.id, backcheck=force_check, get_missing_blocks=True)
            if not block_is_valid and consensus_found and resend_missing_blocks:
                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=packet_creator if packet_creator else sender_node)
        elif not opBlock.validated or opBlock.hash != received_json['opBlock_hash'] and opBlock.validated:
            if resend_missing_blocks:
                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=packet_creator if packet_creator else sender_node)
        elif 'opBlock_not_latest' in received_json:
            pass
        elif opBlock and opBlock.index != opBlock.Blockchain_obj.chain_length:
            sent_dt = string_to_dt(received_json['dt'])
            latest_opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=sent_dt, validated=True).order_by('-index', 'created').first()
            if latest_opBlock and latest_opBlock != opBlock and resend_missing_blocks:
                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=latest_opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=packet_creator if packet_creator else sender_node)
    else:
        prnt('opBlock not included')

    if 'headers' in received_json and 'Genesisid' in received_json['headers']:
        blockchain = Blockchain.objects.filter(genesisId=received_json['headers']['Genesisid']).defer('queuedData').first()
        prntDebug('blockchain1',blockchain)
    elif 'genesisId' in received_json:
            blockchain = Blockchain.objects.filter(genesisId=received_json['genesisId']).defer('queuedData').first()
            prntDebug('blockchain1',blockchain)
    elif 'blockchainId' in received_json:
        blockchain = Blockchain.objects.filter(id=received_json['blockchainId']).defer('queuedData').first()
        prntDebug('blockchain2',blockchain)

    if 'force_check' in received_json:
        force_check = received_json['force_check']
    blocks = {}
    if 'block_list' in received_json:
        block_list = decompress_data(received_json['block_list'])
        try:
            block_list = json.loads(block_list)
        except:
            pass
        for b in block_list:
            try:
                block_dict = json.loads(b['block_dict'])
            except:
                block_dict = b['block_dict']
            blocks[block_dict['index']] = b
    elif 'block_dict' in received_json:
        blocks[received_json['block_dict']['index']] = received_json
    prnt('number of blocks',len(blocks))

    from utils.locked import calculate_reward, verify_obj_to_data, convert_to_dict
    from accounts.models import UserPubKey
    from network.models import Validator, _OperationsChain_genesisId
    import operator
    for index, b in sorted(blocks.items(), key=operator.itemgetter(0)):
        try:
            new_block_dict = json.loads(b['block_dict'])
        except:
            new_block_dict = b['block_dict']
        prnt('process:',new_block_dict['index'],new_block_dict['id'])

    try:
        prnt('process block into database')
        added_blocks = []
        received_hashes = []
        full_nodeData = None
        operatorData = get_operatorData()
        node_data = operatorData['myNodes'][operatorData['local_nodeId']]
        operatorData.clear()
        if not 'do_not_sync_block_content' in node_data['meta'] and 'chainData' in node_data['meta']:
            supported = node_data['meta']['chainData'].get('supported_regions', []) + node_data['meta']['chainData'].get('supported_plugins', [])
        else:
            supported = []
        for index, b in sorted(blocks.items(), key=operator.itemgetter(0)):
            try:
                new_block_dict = json.loads(b['block_dict'])
            except:
                new_block_dict = b['block_dict']
            transaction = None
            if verify_obj_to_data(Block(), new_block_dict):
                prntDebugn('new_block',new_block_dict['id'])
                block_transaction = b['block_transaction']
                prntDebug('block_transaction',block_transaction)
                try:
                    block_transaction = json.loads(block_transaction)
                except:
                    pass
                if new_block_dict['networkChain'] == _OperationsChain_genesisId:
                    specific_data = {'objType':'Block','networkChain':new_block_dict['networkChain'],'DateTime':new_block_dict['DateTime'],'CreatorNode_obj':new_block_dict['CreatorNode_obj']}
                else:
                    specific_data = {'objType':'Block','networkChain':new_block_dict['networkChain'],'DateTime':new_block_dict['DateTime']}
                if True:
                    if 'opBlockId' in new_block_dict and not value_is_none(new_block_dict['opBlockId']):
                        opBlock = Block.objects.filter(id=new_block_dict['opBlockId']).exists()
                        if not opBlock:
                            updated_objs = request_items([new_block_dict['opBlockId']], return_updated_objs=True, downstream_worker=False, get_missing_blocks=get_missing_blocks, override_completed=get_missing_blocks)
                    transaction_signature_verified = False
                    if not block_transaction:
                        prntDebug('no reward')
                        proceed_to_check_consensus = True
                        transaction = None
                    else:
                        prntDebug('process reward')
                        proceed_to_check_consensus = False
                        # if block_transaction['token_value'] == calculate_reward(block_transaction['created']):
                        sig_data = get_sigData(block_transaction, first_key=True)
                        pkey = sig_data['pk']
                        if is_id(pkey):
                            iden = pkey
                        else:
                            iden = hash_upk_id(pkey)
                        upk = UserPubKey.objects.filter(id=iden, keyType='node').only('publicKey','end_life_dt').first()
                        if upk:
                            transaction_signature_verified = upk.verify(get_signing_data(block_transaction), sig_data['sig'], publicKey=block_transaction['signed'])
                        prntDebug('transaction_signature_verified',transaction_signature_verified)
                        if transaction_signature_verified:
                            transaction = get_or_create_model('Transaction', id=block_transaction['id'])
                            transaction, sigs, proceed_to_check_consensus, transaction_updatedDB = sync_model(transaction, block_transaction, get_missing_blocks=get_missing_blocks)
                                
                    prnt('proceed_to_check_consensus',proceed_to_check_consensus)
                    prnt('supported',supported)
                    prnt("get_pointer_type(new_block_dict['networkChain'])",get_pointer_type(new_block_dict['networkChain']))
                    if get_pointer_type(new_block_dict['networkChain']) not in ['Region','Plugin']:
                        prnt("get_pointer_type(new_block_dict['networkChain']) not in ['Region','Plugin']")
                    prnt('blockchain.genesisId',blockchain.genesisId)
                    if blockchain.genesisId in supported:
                        prnt('blockchain.genesisId in supported')
                    if proceed_to_check_consensus and (get_pointer_type(new_block_dict['networkChain']) not in ['Region','Plugin'] or blockchain.genesisId in supported):
                        block = Block.objects.filter(hash=new_block_dict['hash']).defer('data','extraData').first()
                        if not block or block.signed != new_block_dict['signed']:
                            block = blockchain.create_block(block_dict=b, dummy_block=block)
                        prnt('transactionx',transaction)
                        if block and block.signed:
                            prnt('block.Transaction_obj',block.Transaction_obj)
                            if transaction and transaction_signature_verified and transaction == block.Transaction_obj:
                                if block.id == transaction.senderBlockId:
                                    if transaction.SenderBlock_obj != block:
                                        transaction.SenderBlock_obj = block
                                        transaction.save()
                                elif transaction.ReceiverBlock_obj != block:
                                    transaction.ReceiverBlock_obj = block
                                    transaction.save()
                            received_hashes.append(block.hash)
                            added_blocks.append(b)
                            if b['validations']:
                                if isinstance(b['validations'], str):
                                    vals_dict = json.loads(b['validations'])
                                else:
                                    vals_dict = b['validations']
                                val_ids = [v['id'] for v in vals_dict if v['objType'] == 'Validator' and v['jobId'] == new_block_dict['id']]
                                prnt('CHECK VALIDATIONS HERE3',val_ids)
                                current_vals = Validator.objects.filter(id__in=val_ids).exclude(signed={}).values('id')
                                prnt('current_vals G',len(current_vals),len(val_ids))
                                if len(current_vals) < len(val_ids):
                                    process_received_data([v for v in vals_dict if v['id'] in val_ids+[i['id'] for i in current_vals]], check_consensus=False, get_missing_blocks=get_missing_blocks)
                    elif transaction:
                        transaction.boot()
        if 'hash_history' in received_json:
            prnt("received_json['hash_history']",len(received_json['hash_history']))
            hash_list = received_json['hash_history'].copy()

            prnt('hash_list len:',len(hash_list))
            local_hash_history = [i['hash'] for i in Block.objects.filter(Blockchain_obj=blockchain, hash__in=hash_list).exclude(validated=False).values('hash')]
            prnt('local_hash_history len:',len(local_hash_history))
            missing_hashes = [i for i in hash_list if i not in local_hash_history and i not in received_hashes]
            prnt('missing_hashes hashes',missing_hashes)
            if missing_hashes:
                if not retrieve_missing_blocks(genesisId=blockchain.genesisId, target_node=packet_creator if packet_creator else sender_node, starting_point=missing_hashes[0], items_to_get=len(missing_hashes), downstream_worker=downstream_worker):
                    prnt('failed to retrieve prior blocks 9432',missing_hashes)
                    note = 'missing_prior_blocks2'
                    block.is_not_valid(note=note, mark_strike=False)
                    creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=False)
                    if get_operator_obj('self_nodeId') in validator_list:
                        from utils.locked import validate_block
                        is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
                    if log:
                        log.completed(note)
                    return False
                
        prnt('check block validity')
        block_num = 0
        for b in added_blocks:
            prnt('b:',b)
            block_num += 1
            if block_num < len(added_blocks) or downstream_worker == False:
                downstream_worker = False
            else:
                downstream_worker = True
            completed = False
            try:
                new_block_dict = json.loads(b['block_dict'])
            except:
                new_block_dict = b['block_dict']
            block_transaction = b['block_transaction']
            prntDebug('block_transaction',block_transaction)
            try:
                block_transaction = json.loads(block_transaction)
            except:
                pass
            block = Block.objects.filter(id=new_block_dict['id']).defer('data','extraData').first()
            if block and block.validated != None and 'block_is_valid' in b and b['block_is_valid'] != block.validated: # block.validation result does not match received block.validation
                prnt('block recheck: received.is_valid:',block.id,b['block_is_valid'],'block.validated:',block.validated)
                if b['validations']:
                    vals = [v['id'] for v in b['validations'] if v['objType'] == 'Validator' and v['jobId'] == block.id]
                    prnt('CHECK VALIDATIONS HERE3',vals)
                    current_vals = Validator.objects.filter(id__in=vals).exclude(signed={}).count()
                    prnt('current_vals B',current_vals,len(vals))
                    if current_vals < len(vals):
                        process_received_data(vals, check_consensus=False, get_missing_blocks=get_missing_blocks, downstream_worker=downstream_worker)
                    block_is_valid, consensus_found, validations = check_validation_consensus(block, block_id=block.id, backcheck=True, get_missing_blocks=get_missing_blocks, downstream_worker=downstream_worker)
            elif block and block.validated != None and not force_check:
                prnt('block already processed and validated',block.id)
                if b['validations']:
                    if isinstance(b['validations'], str):
                        vals_dict = json.loads(b['validations'])
                    else:
                        vals_dict = b['validations']
                    val_ids = [v['id'] for v in vals_dict if v['objType'] == 'Validator' and v['jobId'] == new_block_dict['id']]
                    prnt('CHECK VALIDATIONS HERE',val_ids)
                    current_vals = Validator.objects.filter(id__in=val_ids).exclude(signed={}).values('id')
                    prnt('current_vals C',len(current_vals),len(val_ids))
                    if len(current_vals) < len(val_ids):
                        process_received_data([v for v in vals_dict if v['id'] in val_ids+[i['id'] for i in current_vals]], check_consensus=True, get_missing_blocks=get_missing_blocks)

            else:
                prnt('block not validated or force check:',new_block_dict['id'],block,force_check) # force_check if datapacket is send_missing_block or self_node ran block retrieval
                
                signature_verified = False
                if b['validations']:
                    if isinstance(b['validations'], str):
                        vals_dict = json.loads(b['validations'])
                    else:
                        vals_dict = b['validations']
                    val_ids = [v['id'] for v in vals_dict if v['objType'] == 'Validator' and v['jobId'] == new_block_dict['id']]
                    prnt('CHECK VALIDATIONS HERE2',val_ids)
                    current_vals = Validator.objects.filter(id__in=val_ids).exclude(signed={}).values('id')
                    prnt('current_vals C',len(current_vals),len(val_ids))
                    if len(current_vals) < len(val_ids):
                        process_received_data([v for v in vals_dict if v['id'] in val_ids+[i['id'] for i in current_vals]], check_consensus=False, get_missing_blocks=get_missing_blocks)
                        signature_verified = True
                        
                def handle_competitions(competing_blocks):
                    winning_block, validations = resolve_block_differences(block, competing_blocks=competing_blocks)
                    prnt('winning_blockxxw',convert_to_dict(winning_block))
                    prnt('blockxxw',convert_to_dict(block))
                    if winning_block and not winning_block.validated:
                        block_is_valid, consensus_found, validations = check_validation_consensus(winning_block, block_id=winning_block.id, backcheck=force_check, get_missing_blocks=get_missing_blocks, downstream_worker=downstream_worker)

                    if winning_block and winning_block.hash == block.hash:
                        prnt('pd continue')
                        return True
                    else:
                        prnt('pd1')
                        if winning_block and resend_missing_blocks:
                            prnt('pd3')
                            create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=blockchain, missing_blocks=[winning_block], send_to=packet_creator if packet_creator else sender_node)
                        if winning_block and winning_block.hash != block.hash and block.validated != False :
                            note = f'lost_competition1_{winning_block.id}'
                            block.is_not_valid(note=note, mark_strike=False)
                            prntDebug(f'invalidatey1:',block.id)
                            creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=False)
                            if get_operator_obj('self_nodeId') in validator_list:
                                from utils.locked import validate_block
                                is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
                        return False
                
                if block:
                    prnt('new_block_dict',new_block_dict)
                    prev_block = Block.objects.filter(networkChain=new_block_dict['networkChain'], hash=new_block_dict['prv_hash'], validated=True).defer('data','extraData').first()
                    latest_block = blockchain.get_last_block(is_validated=True, do_not_return_self=True)
                    prnt('prev_block x',prev_block)
                    if prev_block and prev_block.index+1 == int(new_block_dict['index']) or int(new_block_dict['index']) == 1 and new_block_dict['prv_hash'] == '0000000': # if block has expected index or is first on chain
                        competing_blocks = Block.objects.filter(networkChain=new_block_dict['networkChain'], prv_hash=new_block_dict['prv_hash']).exclude(validated=False).exclude(hash=new_block_dict['hash']).defer('data','extraData')
                        
                        if competing_blocks:
                            block_is_winner = handle_competitions(competing_blocks)
                            if not block_is_winner:
                                prnt('ret 3')
                                if log:
                                    log.completed('received_blocks_non_winner')
                                return False
                                
                        elif latest_block and prev_block:
                            if prev_block.hash == latest_block.hash or prev_block.hash == latest_block.prv_hash:
                                signature_verified = True
                        elif int(new_block_dict['index']) == 1 and not latest_block and not prev_block:
                            signature_verified = True

                    else:
                        prnt('Block index not as expected')
                        if not prev_block:
                            block_is_winner = block.validated
                            if not block_is_winner:
                                competing_blocks = Block.objects.filter(networkChain=new_block_dict['networkChain'], prv_hash=new_block_dict['prv_hash']).exclude(hash=new_block_dict['hash']).defer('data','extraData')      
                                if competing_blocks:
                                    block_is_winner = handle_competitions(competing_blocks)
                            if not block_is_winner:
                                # missing blocks
                                prnt(f'prev_block not found11-- blockchain.chain_length:{blockchain.chain_length}, new_block_index:{new_block_dict["index"]}, get_missing_blocks:{get_missing_blocks}')
                                prnt('latest_block',latest_block, 'index',latest_block.index if latest_block else 0)
                                if not latest_block:
                                    if get_missing_blocks:
                                        if downstream_worker:
                                            create_job(retrieve_missing_blocks, job_timeout=200, worker='high', blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=blockchain.chain_length)
                                        else:
                                            retrieve_missing_blocks(blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=blockchain.chain_length, downstream_worker=downstream_worker)
                                elif latest_block.index < int(new_block_dict['index']) - 1:
                                    if get_missing_blocks:
                                        if downstream_worker:
                                            create_job(retrieve_missing_blocks, job_timeout=200, worker='high', blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=latest_block.index)
                                        else:
                                            retrieve_missing_blocks(blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=latest_block.index, downstream_worker=downstream_worker)
                                elif latest_block.index >= int(new_block_dict['index']) and resend_missing_blocks:
                                    create_job(send_missing_blocks, job_timeout=60, worker='main', blockchain=blockchain, starting_index=int(new_block_dict['index']), send_to=packet_creator if packet_creator else sender_node)
                                elif resend_missing_blocks:
                                    create_job(send_missing_blocks, job_timeout=60, worker='main', blockchain=blockchain, starting_index=int(new_block_dict['index'])-1, send_to=packet_creator if packet_creator else sender_node)
                                if log:
                                    log.completed('received_blocks_missing_prev_block')
                                return False
                        
                        elif prev_block and prev_block.index < int(new_block_dict['index']) - 1:
                            # missing blocks
                            if get_missing_blocks:
                                if downstream_worker:
                                    create_job(retrieve_missing_blocks, job_timeout=200, worker='high', blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=prev_block.hash)
                                else:
                                    retrieve_missing_blocks(blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=prev_block.hash, downstream_worker=downstream_worker)
                            if log:
                                log.completed('received_blocks_retrieve_missing')
                            return False
                        
                        elif prev_block and prev_block.index >= int(new_block_dict['index']):
                            # sender node is missing blocks
                            if resend_missing_blocks:
                                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=blockchain, starting_index=int(new_block_dict['index']), send_to=packet_creator if packet_creator else sender_node)
                            if log:
                                log.completed('received_blocks_send_missing')
                            return False
                        
                        elif prev_block and prev_block.index == int(new_block_dict['index']):
                            # block index discrepancy
                            prntDebug('sort out competeing blocks')
                            winning_block, validations = resolve_block_differences(block)
                            if not winning_block:
                                if log:
                                    log.completed('competing_block_p2')
                                return False 
                            if winning_block.hash != block.hash:
                                if resend_missing_blocks:
                                    block = winning_block
                                    create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=blockchain, starting_index=int(new_block_dict['index']), send_to=packet_creator if packet_creator else sender_node)
                            else:
                                # if block:
                                signature_verified = True
                                prntDebug('signature_verified22',signature_verified)
                        else:
                            prnt('not signature_verified')    
                    
                    prnt('signature_verified',signature_verified)
                    if signature_verified:
                        block_is_valid, consensus_found, validations = check_validation_consensus(block, block_id=block.id, backcheck=force_check, get_missing_blocks=get_missing_blocks, downstream_worker=downstream_worker)
                        prntDebug('-a-a-block_is_valid',block_is_valid,'consensus_found',consensus_found,'block.id',block.id)
                        if not block_is_valid and consensus_found:
                            if resend_missing_blocks:
                                prntDebug('send_missing_blocks path 1')
                                if not send_missing_blocks(blockchain=blockchain, starting_index=block.index-1, send_to=packet_creator if packet_creator else sender_node):
                                    send_missing_blocks(blockchain=blockchain, genesisId=None, missing_blocks=[block], starting_index=block.index, send_to=packet_creator if packet_creator else sender_node, force_check=True)
                            if log:
                                log.completed('invalid')
                            return False
                        else:
                            if block_is_valid and consensus_found and block_num == len(blocks): # if last item in received list
                                next_block = Block.objects.filter(networkChain=blockchain.id, prv_hash=block.hash, validated=True).first()
                                prntDebug('next_block',next_block)  
                                if next_block:
                                    next_block_is_valid, next_block_consensus_found, validations = check_validation_consensus(next_block, block_id=next_block.id, backcheck=True, get_missing_blocks=get_missing_blocks)
                                    prntDebug('-a-a-next_block_is_valid-222',next_block_is_valid,'next_block_consensus_found',next_block_consensus_found)
                            if block_is_valid and consensus_found:
                                completed = True
                    if block_num == len(added_blocks) and get_missing_blocks:
                        if 'future_block_count' in b and b['future_block_count']:
                            if (block.index + 1) not in blocks:
                                future_blocks = Block.objects.filter(networkChain=blockchain.id, index__gt=block.index, validated=True).count()
                                # next_block = Block.objects.filter(blockchainId=blockchain.id, prv_hash=block.hash).exclude(validated=False).exists()
                                # if not next_block:
                                if future_blocks < b['future_block_count']:
                                    if downstream_worker:
                                        create_job(retrieve_missing_blocks, job_timeout=300, worker='main', blockchain=block.Blockchain_obj, starting_point=block.index + 1)
                                    else:
                                        retrieve_missing_blocks(blockchain=block.Blockchain_obj, starting_point=block.index + 1, downstream_worker=downstream_worker)
                                
    except Exception as e:
        prnt('process block fail1', str(e))
        if log:
            log.completed(fail=str(e))
        return False
    if log:
        log.completed()
    return completed


def resolve_block_differences(starting_block, competing_blocks=None, validated_blocks=True, allow_divergence_discovery=True):
    prnt('\n--resolve_block_differences', starting_block)
    from network.models import Node, DataPacket, Block, Blockchain, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay
    from utils.locked import get_broadcast_list, check_validation_consensus, get_relevant_nodes, get_node_assignment

    if e_brake(2):
        return 
    common_hashes_map = {}
    discover_divergence = False
    if not competing_blocks:
        qs = Block.objects.filter(networkChain=starting_block.networkChain, index=starting_block.index).exclude(id=starting_block.id)
        if validated_blocks:
            qs = qs.filter(validated=True)
        else:
            qs = qs.exclude(validated=False)
        competing_blocks = list(qs.defer('data', 'extraData').order_by('DateTime', 'created'))

    unique_hashes = {b.hash for b in competing_blocks}
    if not unique_hashes or unique_hashes == {starting_block.hash}:
        return starting_block, []
    prnt('competing_blocks',competing_blocks)

    validation_cache = {}

    def get_validation_state(block):
        prnt('-get_validation_state')
        if block.id not in validation_cache:
            is_valid, consensus_found, validations = check_validation_consensus(block, block_id=block.id, do_mark_valid=False, create_val=False, handle_discrepancies=False)
            prnt('get_validation_state', is_valid, consensus_found)
            validation_cache[block.id] = {'is_valid': is_valid, 'consensus_found': consensus_found, 'validations': [v for v in validations if v.is_valid]}
        return validation_cache[block.id]

    def invalidate_losers(winning_block, competing_blocks):
        if winning_block:
            for block in competing_blocks:
                if block.id != winning_block.id:
                    note = f'lost_resolve_bd_{winning_block.id}'
                    block.is_not_valid(note=note, mark_strike=False)
                    prntDebug(f'invalidatex2:',block.id)
                    creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=False)
                    if get_operator_obj('self_nodeId') in validator_list:
                        from utils.locked import validate_block
                        is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
    # Precedence:
    # 1. Heuristic chain agreement
    # 2. Validator consensus
    # 3. Deterministic tie-breaks
    # 4. Timestamp
    major_candidate = None
    candidate, candidate_state = None, {}
    competing_blocks = [starting_block] + [b for b in competing_blocks]

    for block in competing_blocks:
        prnt('resolve block',block)
        if 'won_competition' in block.notes:
            if string_to_dt(block.notes['won_competition']) > now_utc() - datetime.timedelta(minutes=7):
                prnt('resolve_bd1')
                return block, get_validation_state(block)

        if candidate and block.hash == candidate.hash:
            prnt('resolve_bd2',block.id)
            continue

        state = get_validation_state(block)

        if block.DateTime > now_utc() and starting_block.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            creators, _ = get_node_assignment(block, full_creator_list=True)
            try:
                if creators.index(block.CreatorNode_obj.id) < creators.index(candidate.CreatorNode_obj.id):
                    candidate, candidate_state = block, state
                    continue
            except Exception:
                pass
            
        if not state['is_valid']:
            if state['consensus_found'] and block.validated:
                prntDebug(f'invalidatex3:',block.id)
                block.is_not_valid(note='bd_diff2', mark_strike=False)
            prnt('resolve_bd3',block.id)
            continue

        if not common_hashes_map:
            common_hashes_map, fetched_hashes = resolve_chain_fork(starting_block.networkChain, starting_hash=starting_block.prv_hash)

        if common_hashes_map:
            if block.prv_hash in common_hashes_map and block.hash in common_hashes_map[block.prv_hash]:
                if candidate and candidate.prv_hash in common_hashes_map and candidate.hash in common_hashes_map[candidate.prv_hash]:
                    prnt('resolve_bd4',block.id)
                    if common_hashes_map[block.prv_hash][block.hash] > common_hashes_map[candidate.prv_hash][candidate.hash]:
                        candidate, candidate_state = block, state
                        major_candidate = block
                        continue
                else:
                    prnt('resolve_bd5',block.id)
                    candidate, candidate_state = block, state
                    major_candidate = block
                    continue
            elif block == competing_blocks[-1]:
                if not candidate or candidate.prv_hash not in common_hashes_map or candidate.hash not in common_hashes_map[candidate.prv_hash]:
                    prnt('resolve_bd6',block.id)
                    discover_divergence = True
        
        if not major_candidate:
            if state['consensus_found'] and candidate is None or state['consensus_found'] and candidate and not candidate_state['consensus_found']:
                prnt('resolve_bd7',block.id)
                candidate, candidate_state = block, state
                continue

            if candidate and len(state['validations']) > len(candidate_state['validations']):
                prnt('resolve_bd8',block.id)
                candidate, candidate_state = block, state
                continue

            if candidate and len(state['validations']) < len(candidate_state['validations']):
                prnt('resolve_bd9',block.id)
                continue

            if candidate and string_to_dt(block.DateTime) < string_to_dt(candidate.DateTime):
                prnt('resolve_bd11',block.id)
                candidate, candidate_state = block, state
                continue

    if allow_divergence_discovery and discover_divergence:
        prnt('resolve_bd12',block.id)
        hash_map = discover_chain_divergence(starting_block.networkChain)
        fetch_blocks = []
        check_consensus = []
        for hash in hash_map:
            path_block = Block.objects.filter(networkChain=starting_block.networkChain, hash=hash).values('id','validated').first()
            if not path_block:
                fetch_blocks.append(hash)
            elif not path_block['validated']:
                check_consensus.append(path_block['id'])
        if starting_block.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            queue = django_rq.get_queue('high')
        else:
            queue = django_rq.get_queue('main')
        if fetch_blocks:
            prnt('resolve_bd13',block.id)
            if not exists_in_worker('retrieve_missing_blocks', queue_name=['main','high'], blockchain=starting_block.networkChain, starting_point=fetch_blocks, items_to_get=len(fetch_blocks)):
                queue.enqueue(retrieve_missing_blocks, blockchain=starting_block.networkChain, starting_point=fetch_blocks, items_to_get=len(fetch_blocks), job_timeout=300, result_ttl=7200)
        if check_consensus:
            prnt('resolve_bd14',block.id)
            for block in check_consensus:
                if not exists_in_worker('check_validation_consensus', queue_name=['main','high'], block_id=block.id):
                    queue.enqueue(check_validation_consensus, block, block_id=block.id, job_timeout=420, result_ttl=7200)
        if not fetch_blocks and not check_consensus:
            for block in competing_blocks:
                if state['consensus_found'] and candidate is None or state['consensus_found'] and candidate and not candidate_state['consensus_found']:
                    prnt('resolve_bd72',block.id)
                    candidate, candidate_state = block, state
                    continue

                if candidate and len(state['validations']) > len(candidate_state['validations']):
                    prnt('resolve_bd82',block.id)
                    candidate, candidate_state = block, state
                    continue

                if candidate and string_to_dt(block.DateTime) < string_to_dt(candidate.DateTime):
                    prnt('resolve_bd112',block.id)
                    candidate, candidate_state = block, state
                    continue
            if candidate:
                invalidate_losers(candidate, competing_blocks)
                prnt('resolve_bd152 Final',candidate.id)
                return candidate, candidate_state['validations']
        prnt('resolve_bd15',block.id)
        return None, {}

    winning_block = candidate
    if not winning_block:
        prnt('resolve_bd16',block.id)
        return None, {}

    winning_state = get_validation_state(winning_block)
    for block in [starting_block] + competing_blocks:
        if block.id == winning_block.id:
            prnt('resolve_bd17',block.id)
            continue

        if winning_state['consensus_found'] and block.validated is not False:
            block.is_not_valid(mark_strike=False, note=f'resolved_differences:{winning_block.id}')
        elif block.validated is True:
            block.notes['removed_validation'] = f'{dt_to_string(now_utc())}-{winning_block.id}'
            block.validated = None
            block.save(update_fields=['validated', 'notes'])

    winning_block.notes['won_competition'] = dt_to_string(now_utc())
    winning_block.save()

    invalidate_losers(winning_block, competing_blocks)
    prnt('resolve_bd Final', winning_block)
    prnt()
    return winning_block, winning_state['validations']

def retrieve_missing_blocks(blockchain=None, genesisId=None, target_node=None, starting_point=0, items_to_get=3, retrieve_following=True, downstream_worker=True):
    prntDebugn('--retrieve_missing_blocks- chainid:', blockchain,'starting_point:',starting_point)
    if e_brake(2):
        return 
    from network.models import Node, DataPacket, Block, Blockchain, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay
    from utils.locked import get_broadcast_list, check_validation_consensus, get_relevant_nodes, get_node_assignment, sign_for_sending, hash_obj_id
    if items_to_get < 3:
        items_to_get = 3
    if not blockchain and genesisId:
        blockchain = Blockchain.objects.filter(genesisId=genesisId).first()
    opBlock_data = get_relevant_nodes(genesisId=blockchain.genesisId)
    if target_node and not target_node in opBlock_data['relevant_nodes']:
        n = Node.objects.filter(id=target_node).defer('chain_array','Block_obj','User_obj','abilities','region_data').first()
        if n and n.activated_dt:
            opBlock_data['relevant_nodes'][target_node] = n.return_address()
        else:
            target_node = random.choice([n for n in opBlock_data['relevant_nodes']])
    elif not target_node:
        target_node = random.choice([n for n in opBlock_data['relevant_nodes']])

    value = opBlock_data['relevant_nodes'][target_node]
    opBlock_data['relevant_nodes'].pop(target_node)
    relevant_nodes = {target_node: value, **opBlock_data['relevant_nodes']}

    operatorData = get_operatorData()
    self_node = get_self_node(operatorData=operatorData)

    if not starting_point:
        starting_point = blockchain.chain_length
    elif is_id(starting_point):
        start_block = Block.objects.filter(networkChain=blockchain.id, id=starting_point, validated=True).first()
        if start_block:
            starting_point = start_block.index
    elif not isinstance(starting_point, int):
        start_block = Block.objects.filter(networkChain=blockchain.id, hash=starting_point, validated=True).first()
        if start_block:
            starting_point = start_block.index
    if isinstance(starting_point, int):
        prev_blocks = Block.objects.filter(networkChain=blockchain.id, index__lte=starting_point, index__gt=starting_point-50, validated=True).order_by('index').values('hash')
        hash_history = []
        if prev_blocks:
            hash_history = [b['hash'] for b in prev_blocks]
    else:
        hash_history = [b['hash'] for b in reversed(Block.objects.filter(networkChain=blockchain.id, validated=True).order_by('-index').values('hash')[:50])]
    prnt('starting_pointxxz',starting_point)
    signedRequest = json.dumps(sign_for_sending({'type':'Block', 'blockchainId' : blockchain.id, 'genesisId':blockchain.genesisId, 'include_content' : False, 'force_check':True, 'include_validators':True, 'item_count': items_to_get, 'hash_history':hash_history, 'index':starting_point}))
    prntn('signedRequest',signedRequest)
    sendingData = {'request':signedRequest, 'senderId':get_operator_obj('self_nodeId')}

    
    successes = 0
    for nodeId, addr in relevant_nodes.items():
        if nodeId != self_node.id:
            received_data = None
            content = sign_post_header(data=sendingData, operatorData=operatorData, self_node=self_node.id, post='post', target_node=nodeId)
            success, response = connect_to_node(addr, 'network/request_data', self_node=self_node, content=content, operatorData=operatorData)

            prnt('connect success',success)
            if success and response.status_code == 200:
                response_json = response.json()
                prntn('response_json666',str(response_json)[:3000])    
                if response_json['message'] == 'Success' and 'block_obj' in response_json:
                    block_list = json.dumps([{'block_dict' : response_json['block_obj'], 'block_transaction':response_json['transaction_obj'], 'block_data' : [], 'validations' : response_json['content']}])
                    received_data = {'type' : 'Blocks', 'blockchainId' : blockchain.id, 'genesisId':blockchain.genesisId, 'block_list' : block_list, 'force_check':True, 'end_of_chain' : response_json['end_of_chain']}
                elif response_json['message'] == 'Success' and 'block_list' in response_json:
                    received_data = response_json

                if received_data:
                    received_data['senderId'] = nodeId
                    received_data = sign_for_sending(received_data, operatorData=operatorData)
                    if not isinstance(starting_point, int):
                        try:
                            block_json = json.loads(response_json['block_obj'])
                            starting_point = block_json['index']
                        except Exception as e:
                            prnt('err0828', str(e))
                            block_list = json.loads(response_json['block_list'])
                            block_json = block_list[0]['block_dict']
                            starting_point = block_json['index']

                    iden = hash_obj_id('DataPacket', specific_data=str(received_data)+dt_to_string(now_utc()))
                    dp = DataPacket.objects.filter(id=iden).first()
                    if not dp:
                        dp = DataPacket(id=iden, func='process_received_blocks', created = now_utc(), data=received_data)
                        dp.save()

                    def wrong_blocks_returned(dp):
                        prnt('wrong_blocks_returned1?')
                        result = process_received_dp(dp, 'process_blocks', override_completed=True)
                        if result and 'dp' in result:
                            log = result['dp']
                            received_json = log.data
                        elif result and 'data' in result:
                            received_json = result['data']
                        else:
                            received_json = []
                        blocks = {}
                        if 'block_list' in received_json:
                            block_list = decompress_data(received_json['block_list'])
                            try:
                                block_list = json.loads(block_list)
                            except:
                                pass
                            for b in block_list:
                                try:
                                    block_dict = json.loads(b['block_dict'])
                                except:
                                    block_dict = b['block_dict']
                                blocks[block_dict['index']] = b
                        else:
                            blocks[received_json['block_dict']['index']] = received_json
                        import operator
                        for index, b in sorted(blocks.items(), key=operator.itemgetter(0)):
                            try:
                                new_block_dict = json.loads(b['block_dict'])
                            except:
                                new_block_dict = b['block_dict']
                            block = Block.objects.filter(id=new_block_dict['id']).first()
                            if block and block.validated == False:
                                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=blockchain, starting_index=int(block.index), send_to=nodeId, force_check=True)
                                prnt('true')
                                return True
                        prnt('false')
                        return False

                    if process_received_blocks(dp, get_missing_blocks=False, resend_missing_blocks=False, return_result=True, force_check=True, rebroadcast=False, downstream_worker=downstream_worker):
                        if not wrong_blocks_returned(dp):
                            successes += 1
                            try:
                                prnt("str(response_json['end_of_chain'])",str(response_json['end_of_chain']))
                            except Exception as e:
                                prnt('err9621',str(e))
                            if retrieve_following and str(response_json['end_of_chain']) == 'False':
                                create_job(retrieve_missing_blocks, job_timeout=300, worker='high', blockchain=blockchain, starting_point=int(starting_point)+successes)
                    else:
                        wrong_blocks_returned(dp)
                    prnt('retreived_blocks successes',successes)
                    break

                else:
                    prnt('pass node, retrieve_missing_blocks 23595', response_json)
    return successes

def send_missing_blocks(blockchain=None, genesisId=None, missing_blocks=None, starting_index=1, send_to='', force_check=True):
    prntn('-send_missing_blocks',starting_index,'send_to:',send_to,'missing_blocks',missing_blocks,'blockchain',blockchain,'genesisId',genesisId)
    if e_brake(2):
        return 
    from network.models import Block, Blockchain, DataPacket, Validator, _OperationsChain_genesisId
    from utils.locked import verify_obj_to_data, sort_for_sign, hash_obj_id, convert_to_dict, get_relevant_nodes, get_node_assignment, sign_for_sending
    if not blockchain and genesisId:
        blockchain = Blockchain.objects.filter(genesisId=genesisId).defer('queuedData').first()
    operatorData = get_operatorData()
    self_node_id = get_operator_obj('self_nodeId')
    success = False
    if send_to and send_to != self_node_id:
        hash_history = []
        opBlock = None
        json_data = {'type' : 'Block', 'senderId':self_node_id, 'broadcast_list': [], 'blockchainId' : blockchain.id, 'genesisId':blockchain.genesisId, 'block_list' : [], 'force_check':force_check}
        sending_blocks = []
        if not missing_blocks:
            if isinstance(starting_index, int):
                missing_blocks = Block.objects.filter(networkChain=blockchain.id, index__gte=starting_index-1, validated=True).defer("data").order_by('index')[:3]
            elif is_id(starting_index):
                block = Block.objects.filter(id=starting_index).first()
                if not block:
                    prnt(f'block not found at: {starting_index}')
                    return False
                missing_blocks = Block.objects.filter(networkChain=blockchain.id, index__gte=block.index-1, validated=True).defer("data").order_by('index')[:3]

        for return_block in missing_blocks:
            if verify_obj_to_data(return_block, return_block):
                if not hash_history:
                    hash_history = [i['hash'] for i in reversed(Block.objects.filter(networkChain=blockchain.id, index__lte=return_block.index, validated=True).exclude(id__in=[i.hash for i in missing_blocks]).values("hash").order_by('-index')[:50])]

                if return_block.index == starting_index or return_block.id == starting_index:
                    opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=return_block.DateTime, validated=True).order_by('-index', 'created').first() 

                validations = Validator.objects.filter(validatorType='Block', networkChain=return_block.networkChain, data__has_key=return_block.id)
                validator_list = [sort_for_sign(convert_to_dict(v)) for v in validations if verify_obj_to_data(v, v)]
                prnt('validator_list',validator_list)
                future_block_count = Block.objects.filter(networkChain=blockchain.id, index__gt=return_block.index, validated=True).count()
                sending_blocks.append({'block_dict' : sort_for_sign(convert_to_dict(return_block, exclude=['notes','validators'])), 'block_transaction':return_block.get_transaction_data(), 'block_data' : [], 'validations' : validator_list, 'future_block_count':future_block_count, 'block_is_valid':return_block.validated, 'opBlock':return_block.opBlockId})
        
        if sending_blocks:

            sending_blocks = json.dumps(sending_blocks)
            packet_id = hash_obj_id('DataPacket', specific_data=str(sending_blocks)+send_to)
            prnt('packet_id',packet_id)
            dp = DataPacket.objects.filter(id=packet_id).values('id','updated_on_node').first()
            if dp and dp['updated_on_node'] > now_utc() - datetime.timedelta(minutes=20):
                prnt('recently sent')
                return True
            elif not dp:
                dp = DataPacket(id=packet_id, Node_obj_id=self_node_id, func='completed_sendmissingblocks', networkChain=blockchain.genesisId)
                dp.save()
            if len(sending_blocks) > 1:
                sending_blocks = compress_data(sending_blocks)
            json_data['block_list'] = sending_blocks
            json_data['hash_history'] = hash_history
            if not opBlock:
                opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).order_by('-index', 'created').first() 
            if opBlock:
                json_data['opBlock_id'] = opBlock.id
                json_data['opBlock_hash'] = opBlock.hash
                if opBlock.index != opBlock.Blockchain_obj.chain_length:
                    json_data['opBlock_not_latest'] = True
            json_data = sign_for_sending(json_data, operatorData=operatorData)
            headers = {'packet-id':packet_id, 'packet-origin-dt':dt_to_string(now_utc()), 'senderId':self_node_id, 'func':'sendmissingblocks', 'packet-creator':get_operator_obj('self_nodeId'), 'dt':dt_to_string(now_utc()), 'blockchainId' : return_block.networkChain, 'Genesisid':return_block.Blockchain_obj.genesisId, 'blockId':return_block.id, 'index':str(return_block.index)}
            success, response = connect_to_node(get_node(id=send_to), 'network/receive_blocks', json_data, headers=headers, operatorData=operatorData)
            if success:
                dp = DataPacket.objects.filter(id=packet_id).values('id','notes').first()
                if 'history' not in dp['notes']:
                    dp['notes']['history'] = []
                dp['notes']['history'].append({'sendMissing':dt_to_string(now_utc()), 'send_to':send_to})
                DataPacket.objects.filter(id=dp['id']).update(updated_on_node=now_utc(), notes=dp['notes'])
    return success

def retrieve_transaction(tx=None, block_type='all', target_node=None):
    prntDebugn('--retrieve_transaction- tx:', tx,'target_node:',target_node)
    if e_brake(2):
        return 
    if not tx:
        return
    elif isinstance(tx, models.Model):
        tx = tx.id
    from network.models import DataPacket, Node, Block
    from transactions.models import Transaction
    from utils.locked import get_relevant_nodes, get_node_assignment, sign_for_sending, hash_obj_id
    opBlock_data = get_relevant_nodes()
    if target_node and not target_node in opBlock_data['relevant_nodes']:
        n = Node.objects.filter(id=target_node).defer('chain_array','Block_obj','User_obj','abilities','region_data').first()
        if n and n.activated_dt:
            opBlock_data['relevant_nodes'][target_node] = n.return_address()
        else:
            target_node = random.choice([n for n in opBlock_data['relevant_nodes']])
    elif not target_node:
        target_node = random.choice([n for n in opBlock_data['relevant_nodes']])

    value = opBlock_data['relevant_nodes'][target_node]
    opBlock_data['relevant_nodes'].pop(target_node)
    relevant_nodes = {target_node: value, **opBlock_data['relevant_nodes']}

    operatorData = get_operatorData()
    self_node = get_self_node(operatorData=operatorData)


    signedRequest = json.dumps(sign_for_sending({'type':'Transaction', 'iden':tx, 'block_type':block_type}))
    prntn('signedRequest',signedRequest)
    sendingData = {'request':signedRequest, 'senderId':get_operator_obj('self_nodeId')}

    
    successes = 0
    for nodeId, addr in relevant_nodes.items():
        if nodeId != self_node.id:
            received_data = None
            content = sign_post_header(data=sendingData, operatorData=operatorData, self_node=self_node.id, post='post', target_node=nodeId)
            success, response = connect_to_node(addr, 'network/request_data', self_node=self_node, content=content, operatorData=operatorData)

            prnt('connect success',success)
            if success and response.status_code == 200:
                response_json = response.json()
                prntn('response_json666777',str(response_json)[:3000])    
                if response_json['message'] == 'Success' and 'block_list' in response_json:
                    received_data = response_json

                if received_data:
                    received_data['senderId'] = nodeId
                    iden = hash_obj_id('DataPacket', specific_data=str(received_data)+dt_to_string(now_utc()))
                    dp = DataPacket.objects.filter(id=iden).first()
                    if not dp:
                        dp = DataPacket(id=iden, func='process_received_blocks', created = now_utc(), data=received_data)
                        dp.save()

                    def wrong_blocks_returned(dp):
                        prnt('wrong_blocks_returned2?')
                        result = process_received_dp(dp, 'process_blocks', override_completed=True)
                        if result and 'dp' in result:
                            log = result['dp']
                            received_json = log.data
                        elif result and 'data' in result:
                            received_json = result['data']
                        else:
                            received_json = []
                        blocks = {}
                        if 'block_list' in received_json:
                            block_list = decompress_data(received_json['block_list'])
                            try:
                                block_list = json.loads(block_list)
                            except:
                                pass
                            for b in block_list:
                                try:
                                    block_dict = json.loads(b['block_dict'])
                                except:
                                    block_dict = b['block_dict']
                                blocks[block_dict['index']] = b
                        else:
                            blocks[received_json['block_dict']['index']] = received_json
                        import operator
                        for index, b in sorted(blocks.items(), key=operator.itemgetter(0)):
                            try:
                                new_block_dict = json.loads(b['block_dict'])
                            except:
                                new_block_dict = b['block_dict']
                            block = Block.objects.filter(id=new_block_dict['id']).first()
                            if block and block.validated == False:
                                prnt('true')
                                return True
                        prnt('false')
                        return False

                    if process_received_blocks(dp, get_missing_blocks=True, resend_missing_blocks=False, return_result=True, force_check=True, rebroadcast=False):
                        if not wrong_blocks_returned(dp):
                            successes += 1
                    else:
                        wrong_blocks_returned(dp)
                    prnt('retreived_tx_blocks successes',successes)
                    break

                else:
                    prnt('pass node, retrieve_missing_blocks 5921', response_json)
    return successes


def get_most_common_hashes(lists):
    if not lists:
        return []

    # Count occurrences weighted by length past the hash
    results = {}
    for lst in lists:
        for idx, h in enumerate(lst):
            weight = len(lst) - idx  # only count blocks after this one
            results[h] = results.get(h, 0) + weight

    if not results:
        return []
    prnt('results:',results)
    max_weight = max(results.values())
    prnt('max_weight',max_weight)
    top_hashes = [h for h, w in results.items() if w == max_weight]
    return top_hashes

def find_most_occuring_paths(most_common_hash, lists):
    results = {}
    for lst in lists:
        get_next = False
        for candidate_hash in lst:
            if get_next:
                results[candidate_hash] = results.get(candidate_hash, 0) + 1
                break
            elif candidate_hash == most_common_hash:
                get_next = True

    if not results:
        return []

    MIN_QUORUM = max(2, len(lists) // 3)
    max_count = max(results.values())
    if max_count < MIN_QUORUM:
        return []
    return {h:c for h, c in results.items() if c == max_count}


def resolve_chain_fork(chainId, request_count=50, node_count=50, starting_hash=None):
    prnt('--resolve_chain_fork', chainId, 'starting_hash', starting_hash)
    from utils.locked import get_relevant_nodes

    self_node = get_self_node()
    operatorData = get_operatorData()
    node_data = get_relevant_nodes(blockchain=chainId, exclude_list=[self_node.id], strings_only=False)

    k = min(node_count * 2, len(node_data['relevant_nodes']))
    node_list = dict(
        random.sample(list(node_data['relevant_nodes'].items()), k)
    )

    anchored_paths = []
    for node_id, node in node_list.items():
        success, response = connect_to_node(node,'network/request_chain_path',data={'blockchainId': chainId,'count': request_count,'start': starting_hash},self_node=self_node,operatorData=operatorData)
        if success:
            data = response.json()
            if data.get('message') == 'Success':
                path = json.loads(data['result'])
                if starting_hash: # enforce anchoring
                    if starting_hash not in path:
                        continue

                anchored_paths.append(path)
                if len(anchored_paths) >= node_count:
                    break

    if not anchored_paths:
        prnt('no anchored_paths')
        return {}, []

    if starting_hash:
        most_common_hashes = [starting_hash]
        winning_path_hashes = find_most_occuring_paths(starting_hash, anchored_paths)
        hash_map = {starting_hash:winning_path_hashes}
    else:
        most_common_hashes = get_most_common_hashes(anchored_paths)
        hash_map = {}
        for common_hash in most_common_hashes:
            winning_path_hashes = find_most_occuring_paths(common_hash, anchored_paths)
            hash_map[common_hash] = winning_path_hashes
    prnt('returning hash_map:',hash_map)
    return hash_map, anchored_paths

def discover_chain_divergence(chainId, local_hash_list=None, request_count=100, node_count=50, node_list=None, peer_hash_lists=None):
    prnt('--discover_chain_divergence', chainId)
    from network.models import Block
    from utils.locked import get_relevant_nodes

    if not local_hash_list:
        blocks = Block.objects.filter(networkChain=chainId, validated=True).values('hash').order_by('-index')[:request_count]
        local_hash_list = [b['hash'] for b in reversed(blocks)]

    if not peer_hash_lists:
        self_node = get_self_node()
        operatorData = get_operatorData()
        if not node_list:
            node_data = get_relevant_nodes(blockchain=chainId, exclude_list=[self_node.id], strings_only=False)

            k = min(node_count * 2, len(node_data['relevant_nodes']))
            node_list = dict(
                random.sample(list(node_data['relevant_nodes'].items()), k)
            )
        
        peer_hash_lists = []
        for node in node_list:
            try:
                resp = connect_to_node(node, 'network/request_chain_path', data={'blockchainId': chainId, 'count': request_count, 'hash_history':local_hash_list}, self_node=self_node, operatorData=operatorData)
                success, response = resp
                if success:
                    received = response.json()
                    if received.get('message') == 'Success':
                        peer_list = json.loads(received['result'])
                        prnt('peer_list',peer_list)
                        peer_hash_lists.append(peer_list)
                        if len(peer_hash_lists) >= node_count:
                            break
            except Exception as e:
                prnt('Peer request failed:', node.id, str(e))
                continue

    if not peer_hash_lists:
        prnt('No peer responses received')
        return {}

    blocks = Block.objects.filter(networkChain=chainId, validated=True, hash__in=[h for h in [lst for lst in peer_hash_lists]]).values('hash').order_by('-index')[:request_count]
    local_hash_list = [b['hash'] for b in reversed(blocks)]
    all_hash_lists = peer_hash_lists + [local_hash_list]

    most_common_hashes = get_most_common_hashes(all_hash_lists)
    prnt('most_common_hashes',most_common_hashes)

    hash_map = {}
    for common_hash in most_common_hashes:
        winning_path_hashes = find_most_occuring_paths(common_hash, all_hash_lists)
        hash_map[common_hash] = winning_path_hashes
    prnt('returned hash_map:',hash_map)
    return hash_map

