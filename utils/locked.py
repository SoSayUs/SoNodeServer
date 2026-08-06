

import uuid
import hashlib
import datetime
import json
import platform
import base64


# DO NOT CHANGE THIS FILE
# WILL BREAK ALL VALIDATIONS

def process_gathered_data(received_data, override_completed=False):
    from utils.models import process_received_dp, decompress_data,prnt, now_utc, e_brake, get_self_node, get_node, string_to_dt
    prnt('--process_gathered_data now_utc:',now_utc(),'pForV',str(received_data)[:300], override_completed)
    if e_brake(3):
        return 
    from django.db import models
    result = process_received_dp(received_data, 'process_gathered_data', override_completed=override_completed)
    if result and 'dp' in result:
        dp = result['dp']
        received_data = result['data']
    else:
        received_data = {}
        dp = None

    # make note of received job

    if dp and isinstance(dp, models.Model):
        if not override_completed and 'process' not in dp.func:
            return 'previously completed'
    if not received_data or not dp:
        prnt('no content')
        return 'no content'

    if 'raw' in received_data:
        received_data = received_data['raw']
    
    prnt(str(received_data)[:2000])
    if 'content' in received_data:
        content = decompress_data(received_data['content'])
    else:
        content = decompress_data(received_data)

    from network.models import DataPacket, EventLog

    sender_node = get_node(id=received_data['senderId'])
    func = dp.headers['Func']
    prnt('func',func)
    job_id = dp.headers['Job-Id']
    prnt('job_id1',job_id)
    job_dt = string_to_dt(dp.headers['Job-Dt'])
    prnt('job_dt1',dt_to_string(job_dt))
    validator_node = received_data['validator']

    log = EventLog.objects.filter(jobId=job_id, created=job_dt, func__contains=f"assigned_job:{func}", Node_obj=sender_node).only('func').first()
    if log:
        log.func = log.func.replace('assigned','completed')
        iden_list = []
        for obj in content:
            iden_list.append(obj['id'])
        log.data = {'iden_list':iden_list}
        log.save(update_fields=['func','data'])
        iden_list = None

    self_node = get_self_node()
    if not DataPacket.objects.filter(jobId=dp.jobId, task=dp.task, func__contains=f"job:{func}", Node_obj=self_node).exists():
        prnt('waiting for self')
        if dp.added_to_node <= now_utc() - datetime.timedelta(minutes=30):
            prnt('bypass for time')
        else: 
            return
    created = 0
    matches = 0
    mismatches = []
    skipped_items = []
    validated_idens = []
    invalid_idens = []
    total = 'x'
    region_name = 'unknown'
    scrape_job = {}
    return_dp = None
    q = '00'
    w = '00'
    if received_data and received_data['type'] == 'for_validation':
        from posts.models import Update, Post, Region
        from legis.models import Government
        from legis.utils import get_scrape_duty
        from network.models import Validator, Blockchain, script_created_modifiable_models,max_validation_window, _OperationsChain_genesisId, intelligence_funcs
        from utils.models import logError, logEvent,request_items, value_is_none, testing, check_missing_data, prntDebugn, prntDebug, is_locked, has_field, has_method, convert_to_datetime, sigData_to_hash,get_or_create_model,super_sync,get_model,exists_in_worker,create_dynamic_model,dynamic_bulk_update,seperate_by_type,get_model_prefix,debugging, get_dynamic_model, rgetattr
        
        gov = None
        gov_level = received_data['gov_level']
        region_name = received_data['region_name']
        region_id = received_data['region_id']
        region = Region.objects.filter(id=region_id).first()

        blockchain = Blockchain.objects.filter(genesisId=region_id).only('id','genesisType','genesisId').first()
        v_id = hash_obj_id('Validator', specific_data=f"{dt_to_string(job_dt)}-{func}-{region.id}-{dp.task}-{self_node.id}-{sender_node.id}")
        validator = Validator.objects.filter(id=v_id, is_valid=True).order_by('-created').first()
        if not validator:
            validator = Validator(id=v_id, networkChain=blockchain.genesisId, jobId=job_id, CreatorNode_obj=self_node, created=job_dt, validatorType='scraper_comparison', func=func, is_valid=True)
            validator.save(skip_check=True)
            validator.boot()
        prnt('scrape val created',validator.id, dt_to_string(now_utc()))

        bypass = False

        if not job_dt:
            created_string = content[0]['created']
            job_dt = dt_to_string(created_string)
            prnt('job_dt2',dt_to_string(job_dt))
            prnt('job_dt2a',content[0]['id'])
        total = len(content)
        matched_idens = []
        model_types = []
        exceptions = ['Update'] # these do not need to be stated in scraper approved_models

        # check that Update.pointerType is included in approved_models
        # perhaps created time should match job_dt?

        for z in content:
            if z['objType'] not in exceptions and z['objType'] not in model_types:
                model_types.append(z['objType'])
        z = None
        if bypass and testing():
            scraper_list = [{'function_name':func, 'region_id':region_id, 'scraping_order':[sender_node.id], 'validators':[self_node.id]}]
            approved_funcs = [func]
        elif func in intelligence_funcs:
            scrapers, validators = get_node_assignment(chainId=region_id, func=func, dt=job_dt, nodeType='intelligence')
            approved_funcs = []
            if self_node.id in scrapers or self_node.id in validators:
                approved_funcs = [func]
            scraper_list = [{'function_name':func, 'region_id':region_id, 'scraping_order':[sender_node.id], 'validators':[validators[0]]}]
        else:
            scraper_list, approved_models = get_scrape_duty(gov=gov, receivedDt=job_dt, region=region, gov_level=gov_level, func=func)
            approved_funcs = []
            for key, value in approved_models.items():
                value.append('Update')
                result = all(item in value for item in model_types)
                if result:
                    approved_funcs.append(key)
        prntDebugn('scraper_list',scraper_list)
        q = str({'func':func,'approved_funcs':approved_funcs,'model_types':model_types})
        if func in approved_funcs:
            q += '1'
            for scrape_job in scraper_list:
                q += '2'
                if scrape_job['function_name'] == func and region_id == scrape_job['region_id']:
                    q += 'a'
                    if sender_node.id in scrape_job['scraping_order'] and self_node.id in scrape_job['scraping_order']:
                        q += 'b'

                        local_datapacket = DataPacket.objects.filter(jobId=dp.jobId, task=dp.task, func__contains=f"job:{func}", Node_obj=self_node).first()
                        if not local_datapacket:
                            prnt('waitng for local job')
                            return
                        result = process_received_dp(local_datapacket, 'process_gathered_data', override_completed=True)
                        if result and 'data' in result:
                            local_data = result['data']
                        else:
                            local_data = {}
                        if 'raw' in local_data:
                            local_data = local_data['raw']
                        
                        prnt(str(local_data)[:2000])
                        if 'content' in local_data:
                            local_data = decompress_data(local_data['content'])
                        else:
                            local_data = decompress_data(local_data)
                        prnt('localData:',str(local_data)[:1000])
                            
                        q += '3'
                        if local_data and isinstance(local_data, list):
                            q += '4'
                            for received_obj in content:
                                try:
                                    prntDebug('received_obj_item_id',received_obj['id'])
                                    w = f"{received_obj['id']}_"
                                except:
                                    prntDebug('received_obj_item',str(z)[:100])
                                    w = f"{str(received_obj)[:25]}_"
                                try:
                                    w += 'c'
                                    if any(n == received_obj['CreatorNode_obj'] for n in scrape_job['scraping_order']) and received_obj['id'] not in ['None', None, 'Val:N']:
                                        w += 'd'
                                        w += 'e'
                                        proceed = True
                                        if received_obj['func'] != func:
                                            w += 'f1'
                                            proceed = False
                                        if received_obj['id'] != hash_obj_id(received_obj):
                                            w += 'f2'
                                            prnt('BIGFAIL 2')
                                            prnt(hash_obj_id(received_obj, print_data=True))
                                            prnt(received_obj)
                                            proceed = False
                                        if proceed and verify_obj_to_data(None, received_obj, user=sender_node.User_obj):
                                            w += 'g'

                                            if any(i['id'] == received_obj['id'] for i in local_data):
                                                local_obj = {}
                                                for i in local_data:
                                                    if i['id'] == received_obj['id']:
                                                        local_obj = i
                                                    
                                                if proceed and convert_to_datetime(received_obj['created']) < now_utc() - datetime.timedelta(days=max_validation_window):
                                                    proceed = False
                                                    w += 'c'
                                                prntDebug('proceed',proceed)
                                                if proceed:
                                                    w += '6'
                                                    mismatch = False
                                                    bypass_fields = ['lastUpdate','CreatorNode_obj','created','signed','func'] + skip_sign_fields
                                                    for field in received_obj:
                                                        local_attr = None
                                                        received_attr = None
                                                        try:
                                                            local_attr = local_obj[field]
                                                            local_attr = dt_to_string(local_attr)
                                                        except Exception as e:
                                                            pass
                                                        try:
                                                            received_attr = received_obj[field]
                                                            received_attr = dt_to_string(received_attr)
                                                        except Exception as e:
                                                            pass
                                                        if field == 'prevVersion':
                                                            if received_attr:
                                                                prev_ver = get_dynamic_model(received_attr, id=received_attr)
                                                                if not prev_ver:
                                                                    request_items(requested_items=[received_attr], nodes=[received_obj['CreatorNode_obj']], downstream_worker=False)
                                                            elif local_attr:
                                                                # check if latest valid version, if not send
                                                                if not return_dp:
                                                                    return_dp = DataPacket(chainId=received_obj['CreatorNode_obj'], chainName=received_obj['CreatorNode_obj'], func='share', Node_obj=self_node)
                                                                    return_dp.save()
                                                                return_dp.add_item_to_share(local_attr)
                                                        if field not in bypass_fields and local_attr and received_attr and sort_for_sign(local_attr) != sort_for_sign(received_attr):
                                                            prnt('mismatch break!','field:',field,'\n-database_attr:',sort_for_sign(local_attr, print_data=False),'\n-received_attr:',sort_for_sign(received_attr, print_data=False))
                                                            mismatch = True
                                                            break
                                                        elif value_is_none(local_attr) and not value_is_none(received_attr) or value_is_none(received_attr) and not value_is_none(local_attr):
                                                            prnt('mismatch break2!','field:',field,'local_attr:',local_attr,'received_attr:',received_attr)
                                                            mismatch = True
                                                            break
                                                    if mismatch:
                                                        w += '7'
                                                        def compare_texts(text1, text2, context=10):
                                                            min_length = min(len(text1), len(text2))
                                                            result = ''
                                                            count = 0
                                                            for y in range(min_length):
                                                                if text1[i] != text2[i]:
                                                                    if count < 20:
                                                                        start = max(0, y - context)
                                                                        end = min(len(text1), len(text2), y + context + 1)
                                                                        snippet1 = text1[start:end]
                                                                        snippet2 = text2[start:end]
                                                                        
                                                                        result += f"pos:{y}:Text1:...{snippet1}...Text2: ...{snippet2}..."
                                                                    count += 1
                                                            result = f'count:{count}: {result}'
                                                            if len(text1) != len(text2):
                                                                longer_text, shorter_text = (text1, text2) if len(text1) > len(text2) else (text2, text1)
                                                                result += f"Extra characters in longer text: {longer_text[len(shorter_text):]}"
                                                            return result
                                                        prnt('---items do not match', received_obj)
                                                        mismatches.append(received_obj['id'])
                                                        err_data = {'id':received_obj['id'],'now':dt_to_string(now_utc()),'mismatch_field':field, 'z-valid':verify_obj_to_data(None, received_obj, user=sender_node.User_obj), 'obj-valid':verify_obj_to_data(None, local_obj, user=sender_node.User_obj),'field_comparison': compare_texts(str(sort_for_sign(local_attr)),str(sort_for_sign(received_attr)))}

                                                    else:
                                                        w += '8'
                                                        prnt('---items match', received_obj)
                                                        matches += 1
                                                        w += 'a'
                                                        prnt('get_signing_data:',get_signing_data(received_obj, print_data=True))
                                                        obj_hash = sigData_to_hash(received_obj, exclude_fields=['CreatorNode_obj', 'Validator_obj', 'signed'])
                                                        validator.data[received_obj['id']] = obj_hash
                                                        matched_idens.append(received_obj['id'])
                                                        w += 'b'
                                            else:
                                                w += 'f12'
                                                invalid_idens.append(received_obj['id'])
                                            
                                        else:
                                            w += 'f13'
                                            invalid_idens.append(received_obj['id'])
                                            
                                    else:
                                        w += 'f15'
                                        prntDebug('break3 - created by wrong node or self not assigned validator')
                                        if dp:
                                            dp.completed('incorrect assigned scraper or validator')
                                        if validator:
                                            validator.delete()
                                        break
                                except Exception as e:
                                    prntDebug('fail484',str(e))
                                    if 'id' in received_obj:
                                        iden = received_obj['id']
                                    else:
                                        iden = str(received_obj)[:100]
                                prnt('W:',w)
                    break

    q += '19'
    from utils.models import get_data, connect_to_node
    validator = sign_obj(validator)
    obj_list = [convert_to_dict(validator)]
    for i in content:
        if i['id'] in matched_idens:
            obj_list.append(i)
    content = None

    job_time = obj_list[0]['created']
    compressed_data = json.dumps(obj_list)
    if scrape_job:
        validator_node = scrape_job['validators'][0]
    packet_id = hash_obj_id('DataPacket', specific_data=str(obj_list)+self_node.id)
    sending_data = {'type':'for_validation', 'packet_id':packet_id, 'job_id':job_id, 'job_dt':dt_to_string(job_time), 'func':func, 'packet-creator':self_node.id, 'Seedid':self_node.id, 'senderId':self_node.id, 'region_id':region.id, 'gov_level':gov_level, 'validator':validator_node, 'region_name':region.Name, 'content_length':len(obj_list), 'content': compressed_data}
    headers = {'Packet-Id':packet_id, 'Senderid':self_node.id, 'Job-Id':job_id, 'Task':str(dp.task), 'Job-Dt':dt_to_string(job_time), 'Dt':dt_to_string(now_utc()), 'Func':func, 'Region-Id':region.id if region else None}
    sending_data = sign_for_sending(sending_data)
    prnt('send for validation job_id:',job_id, 'task:',dp.task, 'packet_id:',packet_id)

    if validator_node == self_node.id:
        new_dp = DataPacket(id=packet_id, func='process_posts_for_validating', Node_obj=self_node)
        new_dp.data = sending_data
        new_dp.headers = headers
        new_dp.notes['history'] = []
        new_dp.notes['history'].append({'received':dt_to_string(now_utc()), 'sender':self_node.id, 'packet_creator':self_node.id})
        new_dp.save()
        iden = new_dp.id
        new_dp = None
        import django_rq
        queue = django_rq.get_queue('low')
        queue.enqueue(process_posts_for_validating, iden, job_timeout=600, result_ttl=3600)
        prnt('added to low worker')
    else:
        completed, response = connect_to_node(validator_node, 'network/receive_posts_for_validating', sending_data, headers=headers)
    
    dp.completed()
    result = f'ComparePosts result: {region_name} {func} q:{q}, total:{total}, matched_idens:{len(matched_idens)}, matches:{matches},mismatches:{mismatches}, skipped_items:{skipped_items}, invalid_idens:{invalid_idens}, missing:{total - matches - len(mismatches) - len(skipped_items) - created - len(invalid_idens)}'
    prnt('done comparing posts',result)
    dp.notes[dt_to_string(now_utc())] = {'result':result}
    dp.save(update_fields=['notes'])          



def process_posts_for_validating(received_json, override_completed=False):
    from utils.models import process_received_dp, decompress_data,prnt, now_utc, e_brake
    prnt('--process_posts_for_validating now_utc:',now_utc(),'pForV',str(received_json)[:300], override_completed)
    if e_brake(3):
        return 
    from django.db import models
    result = process_received_dp(received_json, 'process_posts_for_validating', override_completed=override_completed)
    if result and 'dp' in result:
        log = result['dp']
        received_json = result['data']
    elif result and 'data' in result:
        received_json = result['data']
        log = None
    else:
        received_json = {}
        log = None
    if log and isinstance(log, models.Model):
        if not override_completed and 'process' not in log.func:
            return 'previously completed'
    if not received_json:
        return 'no content'

    if 'raw' in received_json:
        received_json = received_json['raw']
    
    prnt(str(received_json)[:2000])
    if 'content' in received_json:
        content = decompress_data(received_json['content'])
    else:
        content = decompress_data(received_json)

    no_post = []
    created = 0
    matches = 0
    mismatches = []
    skipped_items = []
    validated_idens = []
    invalid_idens = []
    waiting_for_self_scrape = []
    val_objs = []
    extra_vals = []
    total = 'x'
    region_name = 'unknown'
    func = 'unknown'
    data_creator = None
    return_dp = None
    q = '00'
    w = '00'
    if received_json and received_json['type'] == 'for_validation':
        from posts.models import Update, Post, Region
        from legis.models import Government
        from legis.utils import get_scrape_duty
        from network.models import Validator, Blockchain, DataPacket, script_created_modifiable_models,max_validation_window, _OperationsChain_genesisId, intelligence_funcs
        from utils.models import logError, logEvent,request_items, get_model_prefix, get_self_node, get_node, find_or_create_chain_from_object, get_latest_dataPacket, data_sort_priority, testing, check_missing_data, prntDebugn, prntDebug, is_locked, has_field, has_method, convert_to_datetime, sigData_to_hash,get_or_create_model,super_sync,get_model,exists_in_worker,create_dynamic_model,dynamic_bulk_update,seperate_by_type,get_model_prefix,debugging,string_to_dt, get_dynamic_model, rgetattr, value_is_none, get_objType
        validator = None
        invalid_validator = None
        val_obj = None
        add_val_to_obj = []
        self_node = get_self_node()
        sender_node = get_node(id=received_json['senderId'])
        func = received_json['func']
        job_dt = None
        job_id = log.headers['Job-Id']
        prnt('job_id1',job_id)
        job_dt = string_to_dt(log.headers['Job-Dt'])
        prnt('job_dt1',dt_to_string(job_dt))
        network_chain = None
        dataPacket = None
        gov = None

        gov_level = received_json['gov_level']
        region_name = received_json['region_name']
        region_id = received_json['region_id']
        region = Region.objects.filter(id=region_id).first()

        bypass = False

        if not job_dt:
            created_string = content[0]['created']
            job_dt = dt_to_string(created_string)
            prnt('job_dt2',dt_to_string(job_dt))
            prnt('job_dt2a',content[0]['id'])
        prnt('content',str(content)[:100000])
        sorted_content = sorted(content, key=data_sort_priority)
        prnt('sorted_content',str(sorted_content)[:1000])
        received_validators = [i for i in sorted_content if i['objType'] == 'Validator']
        prnt('received_validators',received_validators)
        sorted_content = [i for i in sorted_content if i not in received_validators]
        total = len(sorted_content)
        previously_validated = []
        validated_idens = []
        matched_idens = []
        model_types = []
        exceptions = ['Update'] # these do not need to be stated in scraper approved_models

        # check that Update.pointerType is included in approved_models
        # perhaps created time should match job_dt?

        for i in sorted_content:
            if i['objType'] not in exceptions and i['objType'] not in model_types:
                # prntDebug('--accepted',i)
                model_types.append(i['objType'])
                if not data_creator:
                    data_creator = i['CreatorNode_obj']
        if bypass and testing():
            prnt('p1')
            scraper_list = [{'function_name':func, 'region_id':region_id, 'scraping_order':[sender_node.id], 'validators':[self_node.id]}]
            approved_funcs = [func]
        elif func in intelligence_funcs:
            prnt('p2')
            scrapers, validators = get_node_assignment(chainId=region_id, func=func, dt=job_dt, nodeType='intelligence')
            prnt('scrapers',scrapers)
            prnt('validators',validators)
            prnt('self_node.id',self_node.id)
            approved_funcs = []
            if self_node.id in scrapers or self_node.id in validators:
                prnt('p2a')
                approved_funcs = [func]
            scraper_list = [{'function_name':func, 'region_id':region_id, 'scraping_order':[sender_node.id], 'validators':[validators[0]]}]
        else:
            prnt('p3')
            scraper_list, approved_models = get_scrape_duty(gov=gov, receivedDt=job_dt, region=region, gov_level=gov_level, func=func)
            approved_funcs = []
            for key, value in approved_models.items():
                value.append('Update')
                result = all(item in value for item in model_types)
                if result:
                    approved_funcs.append(key)
        prntDebugn('scraper_list',scraper_list)
        required_matches = 'x'
        q = str({'func':func,'approved_funcs':approved_funcs,'model_types':model_types})
        if func in approved_funcs:
            q += '1'
            try:
                processed_data = {'obj_ids':[],'hashes':{}}
                for i in scraper_list:
                    q += '2'
                    if i['function_name'] == func and region_id == i['region_id']:
                        q += 'a'
                        required_matches = (len(i['scraping_order']) * 2/3) if len(i['scraping_order']) >= 2 else 1
                        prnt('required_matches',required_matches)
                        if sender_node.id in i['scraping_order'] and (self_node.id in i['validators'] or self_node.id in i['scraping_order']):
                            q += 'b'
                            self_is_validator = False
                            if all(z['validatorNodeId'] == self_node.id for z in sorted_content):
                                # each scraper validates other scrapers before sending to final validator
                                q += 'c'
                                if received_validators:
                                    q += 'd'
                                    self_is_validator = True
                                    received_validator = received_validators[0]
                                    if received_validator['CreatorNode_obj'] in i['scraping_order']:
                                        q += 'e'
                                        if received_validator['func'] == func and received_validator['is_valid'] == True and received_validator['jobId'] == job_id:
                                            q += 'g'
                                            prnt('axxx:',convert_to_dict(received_validator))
                                            if verify_obj_to_data(None, received_validator, user=sender_node.User_obj):
                                                q += 'h'
                                                if not Validator.objects.filter(id=received_validator['id'], signed=received_validator['signed']).exists():
                                                    q += 'i'
                                                    val_obj = get_or_create_model(received_validator['objType'], id=received_validator['id'])
                                                    prnt('created val_obj',val_obj)
                                                    val_obj, sigs = super_sync(val_obj, received_validator, do_save=True)
                                                val_objs = Validator.objects.filter(jobId=job_id, CreatorNode_obj__in=i['scraping_order'])
                                                prnt('len val_objs',len(val_objs))
                                                q += 'j'
                            q += '3'
                            for z in sorted_content:
                                try:
                                    prntDebug('zitem_id',z['id'])
                                    w = f"{z['id']}_"
                                except:
                                    prntDebug('zitem',str(z)[:100])
                                    w = f"{str(z)[:25]}_"
                                try:
                                    w += 'c'
                                    if any(n == z['CreatorNode_obj'] for n in i['scraping_order']) and z['id'] != '0' and z['validatorNodeId'] == self_node.id:
                                        w += 'd'
                                        if True:
                                            w += 'e'
                                            proceed = True
                                            if z['func'] != func:
                                                w+= 'f1'
                                                prnt('BIGFAIL 1')
                                                prnt(func)
                                                prnt(z)
                                                proceed = False
                                            if z['id'] != hash_obj_id(z):
                                                w += 'f2'
                                                prnt('BIGFAIL 2')
                                                prnt(hash_obj_id(z, print_data=True))
                                                prnt(z)
                                                proceed = False
                                            if proceed and verify_obj_to_data(None, z, user=sender_node.User_obj):
                                                w += 'g'
                                                exclude = {}
                                                obj = get_dynamic_model(z['objType'], exclude=exclude, id=z['id'])
                                                prnt('obj',obj)
                                                if obj:
                                                    prnt('dict:',convert_to_dict(obj))
                                                if obj and obj.signed:
                                                    w += '4'
                                                    if not network_chain:
                                                        network_chain, obj, commit_chain = find_or_create_chain_from_object(obj)
                                                        dataPacket = get_latest_dataPacket(network_chain)
                                                    if obj and has_field(obj, 'Validator_obj') and (not obj.Validator_obj or not obj.Validator_obj.signed or not obj.Validator_obj.is_valid):
                                                        w += 'a'
                                                        if obj.CreatorNode_obj.id not in i['scraping_order'] or (self_is_validator and obj.validatorNodeId != self_node.id) or obj.created != string_to_dt(z['created']):
                                                            from utils.models import superDelete
                                                            superDelete(obj) # obj is from different failed scrape_job
                                                            obj = None
                                                            w += 'b'
                                                        else:
                                                            w += 'c'
                                                            if not validator and len(val_objs) >= required_matches:
                                                                w += 'd'
                                                                validator = Validator(networkChain=network_chain.genesisId, jobId=job_id, CreatorNode_obj=self_node, created=job_dt, validatorType='scraper', func=func, is_valid=True)
                                                                validator.save(skip_check=True)
                                                                prnt('process posts val created 1',validator.id, dt_to_string(now_utc()))
                                                                if validator and is_locked(validator):
                                                                    w += 'e'
                                                                    for e in sorted_content:
                                                                        try:
                                                                            if e['id'] in validator.data and e['id'] not in matched_idens:
                                                                                matched_idens.append(e['id'])
                                                                        except:
                                                                            pass
                                                                    break
                                                    elif obj and has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj.signed and obj.Validator_obj.is_valid:
                                                        w += 'g'
                                                        previously_validated.append(z['id'])
                                                        
                                                if obj and obj.signed and has_field(obj, 'Validator_obj') and (not obj.Validator_obj or not obj.Validator_obj.signed or not obj.Validator_obj.is_valid):
                                                    w += '5'
                                                    if has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.id in obj.Validator_obj.data and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj) and obj.Validator_obj.dt_appropriate(obj):
                                                        skipped_items.append(obj.id)
                                                    else:
                                                        proceed = True
                                                        if has_method(obj, 'required_for_validation'):
                                                            for c in obj.required_for_validation():
                                                                if '.' in c:
                                                                    attr = rgetattr(obj, c)
                                                                    prnt('attr',attr)
                                                                    if not attr:
                                                                        proceed = False
                                                                        w += 'a'
                                                                        prnt('failed require for validation:',c,z)
                                                                        break
                                                                elif c not in z or not z[c]:
                                                                    proceed = False
                                                                    w += 'b'
                                                                    prnt('failed require for validation:',c,z)
                                                                    break
                                                        if proceed and convert_to_datetime(z['created']) < now_utc() - datetime.timedelta(days=max_validation_window):
                                                            proceed = False
                                                            w += 'c'
                                                        prntDebug('proceed',proceed)
                                                        if proceed:
                                                            w += '6'
                                                            mismatch = False
                                                            fields = obj._meta.fields
                                                            bypass_fields = ['lastUpdate','CreatorNode_obj','created','signed','func'] + skip_sign_fields
                                                            db_obj = convert_to_dict(obj)
                                                            for f in fields:
                                                                attr = None
                                                                z_field = None
                                                                try:
                                                                    attr = db_obj[f.name]
                                                                    attr = dt_to_string(attr)
                                                                except Exception as e:
                                                                    pass
                                                                try:
                                                                    z_field = z[f.name]
                                                                    z_field = dt_to_string(z_field)
                                                                except Exception as e:
                                                                    pass
                                                                if f.name == 'prevVersion':
                                                                    if z_field:
                                                                        prev_ver = get_dynamic_model(z_field, id=z_field)
                                                                        if not prev_ver:
                                                                            request_items(requested_items=[z_field], nodes=[z['CreatorNode_obj']], downstream_worker=False)
                                                                    elif attr:
                                                                        # check if latest valid version, if not send
                                                                        # latest_ver = get_model(obj._meta.object_name).objects.exclude(Validator_obj=None).values('id').order_by('-created').first()
                                                                        # if latest_ver and latest_ver['id'] != z_field:
                                                                        if not return_dp:
                                                                            return_dp = DataPacket(chainId=z['CreatorNode_obj'], chainName=z['CreatorNode_obj'], func='share', Node_obj=self_node)
                                                                            return_dp.save()
                                                                        return_dp.add_item_to_share(attr)
                                                                if f.name not in bypass_fields and attr and z_field and sort_for_sign(attr) != sort_for_sign(z_field):
                                                                    prnt('mismatch break!','field:',f.name,'\n-database_attr:',sort_for_sign(attr, print_data=False),'\n-received_attr:',sort_for_sign(z_field, print_data=False))
                                                                    mismatch = True
                                                                    break
                                                                elif value_is_none(attr) and not value_is_none(z_field) or value_is_none(z_field) and not value_is_none(attr):
                                                                    prnt('mismatch break2!','field:',f,'attr:',attr,'z_field:',z_field)
                                                                    mismatch = True
                                                                    break
                                                            if mismatch:
                                                                w += '7'
                                                                def compare_texts(text1, text2, context=10):
                                                                    # print('compare_texts')
                                                                    min_length = min(len(text1), len(text2))
                                                                    result = ''
                                                                    count = 0
                                                                    for i in range(min_length):
                                                                        if text1[i] != text2[i]:
                                                                            if count < 20:
                                                                                start = max(0, i - context)
                                                                                end = min(len(text1), len(text2), i + context + 1)
                                                                                snippet1 = text1[start:end]
                                                                                snippet2 = text2[start:end]
                                                                                
                                                                                result += f"pos:{i}:Text1:...{snippet1}...Text2: ...{snippet2}..."
                                                                            count += 1
                                                                    result = f'count:{count}: {result}'
                                                                    if len(text1) != len(text2):
                                                                        # prnt("Texts have different lengths.")
                                                                        longer_text, shorter_text = (text1, text2) if len(text1) > len(text2) else (text2, text1)
                                                                        result += f"Extra characters in longer text: {longer_text[len(shorter_text):]}"
                                                                    return result
                                                                prnt('---items do not match', obj)
                                                                mismatches.append(z['id'])
                                                                err_data = {'id':z['id'],'now':dt_to_string(now_utc()),'mismatch_field':f.name, 'z-valid':verify_obj_to_data(None, z, user=sender_node.User_obj), 'obj-valid':verify_obj_to_data(None, obj, user=sender_node.User_obj),'field_comparison': compare_texts(str(sort_for_sign(attr)),str(sort_for_sign(z_field)))}

                                                            else:
                                                                w += '8'
                                                                prnt('---items match', obj)
                                                                matches += 1
                                                                if not self_is_validator:
                                                                    w += 'A'
                                                                else:
                                                                    w += 'B'
                                                                    if val_objs:
                                                                        w += 'b'
                                                                        obj_hash = sigData_to_hash(z, exclude_fields=['CreatorNode_obj', 'Validator_obj', 'signed'])
                                                                        prnt('obj_hash', obj_hash)
                                                                        matched_hashes = []
                                                                        for val in val_objs:
                                                                            if z['id'] in val.data:
                                                                                prnt('val',val.CreatorNode_obj.id,val.data[z['id']])
                                                                                if val.data[z['id']] == obj_hash:
                                                                                    matched_hashes.append(val)
                                                                        prnt('matched_hashes', len(matched_hashes))
                                                                        prnt('required_matches', required_matches)
                                                                        if len(matched_hashes) >= required_matches:

                                                                            w += 'c'
                                                                            
                                                                            try:
                                                                                new_index = i['scraping_order'].index(z['CreatorNode_obj'])
                                                                                w += str(new_index)
                                                                                current_index = i['scraping_order'].index(obj.CreatorNode_obj.id)
                                                                            except Exception as e:
                                                                                prnt('err 4434',str(e))
                                                                                new_index = 1
                                                                                current_index = 0
                                                                            if new_index < current_index:
                                                                                w += 'C'
                                                                                do_sync = True
                                                                                if has_field(obj, 'proposed_modification') and obj.proposed_modification:
                                                                                    w += 'a'
                                                                                    prnt('proposed_modification')
                                                                                    modded_obj = obj
                                                                                    obj = get_or_create_model(get_objType(modded_obj), id=modded_obj.proposed_modification)
                                                                                    if not obj.signed or obj.signed != modded_obj.signed:
                                                                                        w += 'b'
                                                                                        if not has_field(obj, 'lastUpdate') or not obj.lastUpdate or string_to_dt(obj.lastUpdate) < string_to_dt(modded_obj.created):
                                                                                            w += 'c'
                                                                                            obj, sigs = super_sync(obj, convert_to_dict(modded_obj), skip_fields=['id','created'])
                                                                                            if obj.Validator_obj:
                                                                                                extra_vals.append(obj.Validator_obj.id)
                                                                                                if obj.Validator_obj.Validator_array:
                                                                                                    for vi in obj.Validator_obj.Validator_array:
                                                                                                        extra_vals.append(vi)
                                                                                            obj.proposed_modification = None
                                                                                            obj.Validator_obj = None
                                                                                            if has_field(obj, 'Block_obj'):
                                                                                                obj.Block_obj = None
                                                                                            obj = sign_obj(obj, signing_dt=modded_obj.created)
                                                                                            obj_hash = sigData_to_hash(obj)
                                                                                            validator.data[obj.id] = obj_hash
                                                                                            validator.data[modded_obj.id] = sigData_to_hash(modded_obj)
                                                                                            matched_idens.append(obj.id)
                                                                                            matched_idens.append(modded_obj.id)
                                                                                            do_sync = False
                                                                                            modded_chain = Blockchain.objects.filter(genesisId=modded_obj.id).first()
                                                                                            if modded_chain:
                                                                                                super(get_model(get_objType(modded_chain)), modded_chain).delete()
                                                                                            Post.objects.filter(pointerId=obj.id, validated=True).update(validated=False, blockId=None)
                                                                                        else:
                                                                                            w += 'd'
                                                                                            do_sync = False
                                                                                
                                                                                if do_sync and not is_locked(obj):
                                                                                    w += 'e'
                                                                                    if validator and validator.dt_appropriate(obj):
                                                                                        w += 'g'
                                                                                        obj, sigs = super_sync(obj, z, do_save=True)
                                                                            w += 'h'
                                                                            if validator and obj.id not in validator.data:
                                                                                prnt('get_signing_data:',get_signing_data(obj, print_data=True))
                                                                                obj_hash = sigData_to_hash(obj)
                                                                                validator.data[obj.id] = obj_hash
                                                                                if obj.id not in matched_idens:
                                                                                    matched_idens.append(obj.id)
                                                                                w += 'i'

                                                elif obj and has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj.is_valid and obj.Validator_obj.dt_appropriate(obj):
                                                    w += '9'
                                                    matches += 1
                                                    if obj.id not in matched_idens:
                                                        previously_validated.append(obj.id)
                                                elif not obj or not obj.signed:
                                                    w += '11'
                                                    create_obj = False
                                                    if self_is_validator and val_obj and z['CreatorNode_obj'] != val_obj.CreatorNode_obj:
                                                        w += 'a'
                                                        create_obj = True
                                                    if create_obj:
                                                        w += 'c'
                                                        if not obj:
                                                            obj = get_or_create_model(z['objType'], id=z['id'])
                                                        prnt('created item',obj)
                                                        obj, sigs = super_sync(obj, z, do_save=True)
                                                        if has_method(obj, 'boot'):
                                                            obj.boot()
                                                        created += 1
                                                        w += 'd'
                                                        if required_matches == 1:
                                                            w += 'e'
                                                            if not is_locked(obj):
                                                                w += 'g'
                                                                if not network_chain:
                                                                    network_chain, obj, commit_chain = find_or_create_chain_from_object(obj)
                                                                    dataPacket = get_latest_dataPacket(network_chain)
                                                                if not validator and len(val_objs) >= required_matches:
                                                                    w += 'h'
                                                                    if job_id:
                                                                        validator = Validator.objects.filter(jobId=job_id, CreatorNode_obj=self_node, func=func, is_valid=True, validatorType='scraper').order_by('-created').first()
                                                                    else:
                                                                        validator = Validator.objects.filter(CreatorNode_obj=self_node, func=func, is_valid=True, validatorType='scraper').order_by('-created').first()
                                                                    if not validator:
                                                                        validator = Validator(networkChain=network_chain.genesisId, jobId=job_id, CreatorNode_obj=self_node, created=job_dt, validatorType='scraper', func=func, is_valid=True)
                                                                        validator.save(skip_check=True)
                                                                    prnt('process posts val created 2',validator.id, dt_to_string(now_utc()))
                                                                    if validator and is_locked(validator):
                                                                        w += 'i'
                                                                        break
                                                            
                                                                w += 'j'
                                                                if validator and validator.dt_appropriate(obj):
                                                                    w += 'k'
                                                                    obj, sigs = super_sync(obj, z, do_save=True)
                                                                    obj_hash = sigData_to_hash(obj)
                                                                    validator.data[obj.id] = obj_hash
                                                                    matched_idens.append(obj.id)
                                                                    w += 'l'
                                                else:
                                                    w += '12'
                                                    try:
                                                        prntDebug('xitem',z['id'])
                                                        skipped_items.append(z['id'])
                                                    except:
                                                        prntDebug('xitem',str(z)[:100])
                                                        skipped_items.append(str(z)[:50])
                                                    
                                            else:
                                                w += 'f13'
                                                invalid_idens.append(z['id'])
                                    else:
                                        w += '15'
                                        prntDebug('break3 - created by wrong node or self not assigned validator')
                                        if log:
                                            log.completed('incorrect assigned scraper or validator')
                                        if validator:
                                            validator.delete()
                                        break
                                except Exception as e:
                                    prntDebug('fail48274',str(e))
                                    if 'id' in z:
                                        iden = z['id']
                                    else:
                                        iden = str(z)[:100]
                                prnt('W:',w)
                sorted_content.clear()
                now = now_utc()

                if previously_validated:
                    if dataPacket:
                        dataPacket.add_item_to_share(previously_validated)
            
                prnt('self_is_validator',self_is_validator)
                prnt('validator',validator)
                prnt('val_objs',val_objs)
                prnt('required_matches',required_matches)
                
                if self_is_validator and validator and validator.data:
                    q += '21'
                    if len(val_objs) >= required_matches:
                        q += 'a'
                        if not validator.Validator_array:
                            validator.Validator_array = []
                        for val_obj in val_objs:
                            validator.data[val_obj.id] = sigData_to_hash(val_obj)
                            validator.Validator_array.append(val_obj.id)
                        for val_id in extra_vals:
                            validator.Validator_array.append(val_id)
                        validator = sign_obj(validator)
                        if verify_obj_to_data(validator, validator):
                            q += 'b'
                            validators = [validator] + [v for v in val_objs] + [v for v in Validator.objects.filter(id__in=extra_vals)]
                            if network_chain:
                                network_chain.add_item_to_queue([validator] + [v for v in val_objs])

                            opBlock_data = get_relevant_nodes_from_block(dt=job_dt, blockchain=validator.networkChain, sublist='maintainer')

                            prntDebug(f'val posts step1')
                            verifiedIdens = [i for i in matched_idens if not i.startswith(get_model_prefix('Update')) and not i.startswith(get_model_prefix('Notification'))]
                            if verifiedIdens:
                                q += '22'
                                for model_name, id_list in seperate_by_type(verifiedIdens).items():
                                    prnt('model_name',model_name)
                                    q += 'a'
                                    objIdens = id_list.copy()
                                    while objIdens:
                                        q += 'b'
                                        bulk_update = []
                                        for i in get_dynamic_model(model_name, list=True, id__in=objIdens[:200]):

                                            if validate_obj(obj=i, pointer=i, validators=validators, opBlock_data=opBlock_data, save_obj=False, update_pointer=False):
                                                i.Validator_obj = validator
                                                i.updated_on_node = now
                                                validated_idens.append(i.id)
                                                bulk_update.append(i)
                                                try:
                                                    if has_method(i, 'upon_validation'):
                                                        i.upon_validation()
                                                    if has_method(i, 'on_confirmation'):
                                                        i = i.on_confirmation()
                                                except Exception as e:
                                                    prnt('***ERROR*** 8545',str(e))
                                                
                                        if bulk_update:
                                            dynamic_bulk_update(model=get_model(model_name), update_data={}, items_field_update=[], items=bulk_update, compensate_save=True, return_items=False, retrieve_missing=False)

                                        q += 'c'
                                        if network_chain:
                                            q += 'd'
                                            network_chain.add_item_to_queue(objIdens[:200])
                                        del objIdens[:200]
                                    
                            q += '23'
                            prntDebug(f'val posts step2')
                            pointerIdens = sorted([i for i in matched_idens if not i.startswith(get_model_prefix('Update')) and not i.startswith(get_model_prefix('Notification')) and not i.startswith(get_model_prefix('BillText'))])
                            no_post = pointerIdens.copy()
                            from posts.models import update_post
                            while pointerIdens:
                                prnt('pointerIdens[:500]',len(pointerIdens[:1000]),pointerIdens[:500])
                                q += 'a'
                                bulk_update = []
                                fields = []
                                posts = Post.all_objects.filter(pointerId__in=pointerIdens[:500]).exclude(validated=True).order_by('id')
                                prnt('posts len',posts.count())
                                del pointerIdens[:500]
                                for p in posts:
                                    try:
                                        if validate_obj(obj=p, pointer=None, validators=validators, opBlock_data=opBlock_data, save_obj=False, verify_validator=False, update_pointer=False):
                                            p.validated = True
                                            p.updated_on_node = now
                                            p, updated_fields = update_post(p=p, save_p=False)
                                            if p.pointerId not in validated_idens:
                                                validated_idens.append(p.pointerId)
                                            bulk_update.append(p)
                                            if updated_fields:
                                                fields += [f for f in updated_fields if f not in fields]
                                    except Exception as e:
                                        prnt('***ERROR*** 8243',str(e))
                                    
                                    no_post.remove(p.pointerId)
                                posts = None
                                q += 'b' 
                                prnt(f'val posts bulk_update: {str(bulk_update)[:100]}')
                                prnt(f'val posts bulk_update len: {len(bulk_update)}')
                                prnt(f'val posts pointerIdens len: {len(pointerIdens)}')
                                if bulk_update:
                                    dynamic_bulk_update(model=Post, items_field_update=['validated', 'updated_on_node'] + fields, items=bulk_update)
                                    network_chain.add_item_to_queue(bulk_update)
                                prnt('val posts x path 1 current len:',{len(pointerIdens)})
                            q += '24'
                            prntDebug(f'val posts step3')
                            updateIdens = sorted([u for u in matched_idens if u.startswith(get_model_prefix('Update'))])
                            if updateIdens:
                                q += 'a'
                                while updateIdens:
                                    bulk_update = []
                                    updates = Update.objects.filter(id__in=updateIdens[:500]).exclude(validated=True).order_by('id')
                                    del updateIdens[:500]
                                    for u in updates:
                                        try:
                                            if not is_locked(u, skip=['Validator_obj']):
                                                if validate_obj(obj=u, pointer=None, validators=validators, opBlock_data=opBlock_data, save_obj=False, verify_validator=False, update_pointer=False):
                                                    u.validated = True
                                                    u.Validator_obj = validator
                                                    u.updated_on_node = now
                                                    validated_idens.append(u.id)
                                                    if has_method(u, 'upon_validation'):
                                                        u.upon_validation()
                                                    if has_method(u, 'on_confirmation'):
                                                        i = u.on_confirmation()
                                                        if i:
                                                            u = i
                                                    bulk_update.append(u)
                                        except Exception as e:
                                            prnt('***ERROR*** 8232',str(e))
                                    updates = None
                                    q += 'b'
                                    if bulk_update:
                                        items = dynamic_bulk_update(model=Update, items_field_update=['validated', 'Validator_obj','updated_on_node'], items=bulk_update, return_items=True)
                                        if network_chain:
                                            network_chain.add_item_to_queue(items)
                            q += '25'
                                
                            prntDebug(f'val posts step4')
                            from accounts.models import Notification
                            notiIdens = sorted([u for u in matched_idens if u.startswith(get_model_prefix('Notification'))])
                            if notiIdens:
                                q += 'a'
                                while notiIdens:
                                    bulk_update = []
                                    notifications = Notification.objects.filter(id__in=notiIdens[:500]).exclude(validated=True).order_by('id')
                                    del notiIdens[:500]
                                    for n in notifications:
                                        try:
                                            if not is_locked(n):
                                                if validate_obj(obj=n, pointer=None, validators=validators, opBlock_data=opBlock_data, save_obj=False, update_pointer=False, verify_validator=False, add_to_queue=False):
                                                    n.validated = True
                                                    n.Validator_obj = validator
                                                    n.updated_on_node = now
                                                    validated_idens.append(n.id)
                                                    if has_method(n, 'upon_validation'):
                                                        n.upon_validation()
                                                    if has_method(n, 'on_confirmation'):
                                                        i = n.on_confirmation()
                                                        if i:
                                                            n = i
                                                    bulk_update.append(n)
                                        except Exception as e:
                                            prnt('***ERROR*** 8113',str(e))
                                    notifications = None
                                    if bulk_update:
                                        items = dynamic_bulk_update(model=Notification, items_field_update=['validated', 'Validator_obj','updated_on_node'], items=bulk_update, return_items=True)
                                        if network_chain:
                                            network_chain.add_item_to_queue(items)


                            prntDebug(f'val posts step5')
                            chains = {}
                            q += '26'
                            for m in script_created_modifiable_models:
                                mIdens = [u for u in matched_idens if u.startswith(get_model_prefix(m))]
                                if mIdens:
                                    while mIdens:
                                        objs = get_dynamic_model(m, list=True, id__in=mIdens[:500])
                                        del mIdens[:500]
                                        for o in objs:
                                            chain, o, secondChain = find_or_create_chain_from_object(o)
                                            if chain:
                                                if chain not in chains:
                                                    chains[chain] = []
                                                chains[chain].append(o)
                                        objs = None
                            if chains:
                                for chain in chains:
                                    if chain != network_chain:
                                        chain.add_item_to_queue(chains[chain])
                            if dataPacket:
                                dataPacket.add_item_to_share(validated_idens + [validator.id] + [v.id for v in val_objs])


                            prntDebug(f'val posts step6')

                            if not exists_in_worker('broadcast_dp', queue_name=['chat','low'], iden=dataPacket.id):
                                import django_rq
                                django_rq.get_queue('low').enqueue(dataPacket.broadcast_dp, iden=dataPacket.id, job_timeout=300, result_ttl=7200)
            except Exception as e:
                prnt('fail3920567',str(e),'q',q,'w',w)
                logError(f'ValidatePosts fail {str(e)}', code='83745', func='processes_posts_for_validating', extra={'q':q,"log":log.id if log else'none'})
                if log:
                    log.completed(f'err:{q}:{str(e)}')
                result = f'ValidatePosts result: err:{q}:{str(e)}'
                if log:
                    log.notes[dt_to_string(now_utc())] = {'result':result}
                    log.save()
                return result
            prnt('RESULT:func',func,'task',log.task,'creator',data_creator,'sender',sender_node.id,'-created',created,'matches',matches,'validated',len(validated_idens),'previously_validated',len(previously_validated),'mismatches',len(mismatches),'missing:',total - matches - len(mismatches) - len(skipped_items) - created - len(invalid_idens),'invalid_idens',len(invalid_idens))
            prnt('mismatches:',mismatches)
        prnt('q',str(q))
    if log:
        prnt('has log',log)
        log.completed()
    else:
        prnt('does not have log')
    prnt('done validating posts')
    result = f'ValidatePosts result: {region_name} {func} q:{q}, total:{total}, validated_idens:{len(validated_idens)}, matches:{matches},mismatches:{mismatches},created:{created},no_post:{len(no_post)}, skipped_items:{skipped_items}, invalid_idens:{invalid_idens}, waiting_for_self_scrape:{waiting_for_self_scrape}, missing:{total - matches - len(mismatches) - len(skipped_items) - created - len(invalid_idens)}, log:{str(convert_to_dict(log))[:200]}'
    if log:
        log.notes[dt_to_string(now_utc())] = {'result':result}
        log.save()
    if return_dp:

        import django_rq
        chat_queue = django_rq.get_queue("chat")
        if not exists_in_worker('broadcast_dp', queue=chat_queue, iden=return_dp.id, target_node=sender_node.id):
            from network.models import DataPacket
            prnt('add to chat worker')
            chat_queue.enqueue(return_dp.broadcast_dp, iden=return_dp.id, target_node=sender_node.id, job_timeout=360, result_ttl=3600)

    return result

def check_validation_consensus(block=None, do_mark_valid=True, create_val=True, broadcast_if_unknown=False, downstream_worker=True, handle_discrepancies=True, backcheck=False, get_missing_blocks=True, next_block=None, next_block_must_val=True, only_if_unkown=False, block_id=None):
    from utils.models import get_objType, prntDebug, create_job, sigData_to_hash, get_operator_obj, now_utc, prnt, string_to_dt, e_brake, logEvent, resolve_block_differences, retrieve_missing_blocks, send_missing_blocks, request_items, get_chain_id
    prnt('---check_validation_consensus',block, now_utc(),do_mark_valid,handle_discrepancies,'next_block:',next_block)
    from network.models import Blockchain, Block, Validator, Node, _OperationsChain_genesisId
    # return is_valid, consensus_found, validators
    if e_brake(2):
        return 
    if isinstance(block, str):
        block = Block.objects.filter(id=block).defer('data','extraData','notes').first()
    if not block or (only_if_unkown and block.validated != None):
        prnt('return only_if_unkown',block)
        return None, True, []
    is_new_validation = False
    prev_block = None
    b_dt = string_to_dt(block.DateTime)
    b_ct = string_to_dt(block.created)
    def invalidate(block, note=None, strike=True, opBlock_data={}):
        if not block.validated == False and do_mark_valid:
            block.is_not_valid(note=note, mark_strike=strike)
            prntDebug(f'invalidatex: {note}',block.id)
            creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(opBlock_data=opBlock_data, fetch_broadcast_list=False)
            if get_operator_obj('self_nodeId') in validator_list:
                is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
        else:
            prntDebug('not valid',note,block.id)

    if not block.signed:
        if not block.validated == False:
            prntDebug('p000 block no sig',block.id)
            invalidate(block, note='no_sig', strike=False)
            return False, True, []
    opChainId = get_chain_id(_OperationsChain_genesisId)
    prnt('opChainId',opChainId)
    if block.opBlockId:
        opBlock = Block.objects.filter(id=block.opBlockId, networkChain=_OperationsChain_genesisId, validated=True).values('opData','id').first()
    else:
        opBlock = Block.objects.filter(networkChain=_OperationsChain_genesisId, validated=True).values('opData','id').order_by('-DateTime').first()
    if opBlock:
        prnt('opBlockAAA',opBlock)
        try:
            prnt('opBlock.opData',opBlock['opData'])
            block_creation_times = opBlock['opData']['block_creation_times']
            if block.Blockchain_obj.genesisType == 'Wallet' and 'walletBlock_time_delay' in opBlock['opData']:
                block_delay = opBlock['opData']['walletBlock_time_delay']
                region_block_delay = opBlock['opData']['block_time_delay']
            else:
                block_delay = opBlock['opData']['block_time_delay']
            opBlock_dt_delay = opBlock['opData']['opBlock_time_delay']
        except Exception as e:
            if 'id' in opBlock:
                opBlock = Block.objects.filter(id=opBlock['id']).first()
                if opBlock:
                    opBlock.is_not_valid(note=f'opData1-err:{e}', mark_strike=False)
            invalidate(block, note=f'opData2-err:{e}', strike=False, opBlock_data={})
            return False, True, []
    else:
        from network.models import _block_creation_times, _block_creator_count, block_time_delay
        block_creation_times = _block_creation_times
        block_delay = block_time_delay(block)
        opBlock_dt_delay = block_time_delay('operations')

    if block.networkChain == _OperationsChain_genesisId:
        if block and now_utc() < (string_to_dt(block.DateTime) - datetime.timedelta(minutes=10)):
            return None, False, []
        block_delay = opBlock_dt_delay
        if b_dt.minute != 50 or abs(b_ct - b_dt) > datetime.timedelta(minutes=20): # block created greater than 20 minutes from block Datetime
            prnt('abs(b_ct - b_dt) < datetime.timedelta(minutes=20)',abs(b_ct - b_dt) < datetime.timedelta(minutes=20))
            if not block.validated == False:
                prntDebug('p01 created_at_wrong_time1',block.id)
                invalidate(block, note='wrong_datetime_data1', strike=True, opBlock_data={})
            return False, True, []
    elif block.Blockchain_obj.genesisType != 'Wallet':

        prnt('abs(b_ct - b_dt) < datetime.timedelta(minutes=10)',abs(b_ct - b_dt) < datetime.timedelta(minutes=10))
        if b_dt.minute not in block_creation_times or abs(b_ct - b_dt) > datetime.timedelta(minutes=10): # block created greater than 10 minutes from block Datetime
            if not block.validated == False:
                prntDebug('p02 created_at_wrong_time2',block.id)
                invalidate(block, note='wrong_datetime_data2', strike=True, opBlock_data={})
            return False, True, []
    
    if backcheck and block.index > 1:
        prev_block = Block.objects.filter(networkChain=block.networkChain, index=block.index-1, validated=True).exclude(id=block.id).defer('data','extraData').first()
    elif backcheck:
        prev_block = None
    else:
        prev_block = Block.objects.filter(networkChain=block.networkChain, hash=block.prv_hash).exclude(id=block.id).defer('data','extraData').order_by('created').first()
    prntDebug('prev_block',prev_block)
    # prnt('new_block2 ==',convert_to_dict(block))
    if (prev_block and prev_block.hash != block.prv_hash) or sigData_to_hash(block, exclude_fields=['signed']) != block.hash:
        prnt(f'prev_block.hash:{prev_block.hash if prev_block else "0"}, block.prv_hash:{block.prv_hash}, sigData_to_hash(block):{sigData_to_hash(block, exclude_fields=["signed"])}, block.hash:{block.hash}')
        carry_on = False
        if handle_discrepancies and prev_block:
            if int(prev_block.index) == int(block.index):
                winning_block, validations = resolve_block_differences(block)
                if winning_block and block.hash != winning_block.hash:
                    create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=block.Blockchain_obj, starting_index=winning_block.index, send_to=block.CreatorNode_obj.id)
                    
                if winning_block and block.hash != winning_block.hash and not winning_block.validated:
                    invalidate(block, note='did_not_pass_discrepancies1', strike=False, opBlock_data={})
                    block = winning_block
                    if block.get_previous_hash() == block.prv_hash and sigData_to_hash(block, exclude_fields=['signed']) == block.hash:
                        prev_block = block.get_previous_block(is_validated=True)
                        carry_on = True
                elif not winning_block:
                    invalidate(block, note='did_not_pass_discrepancies2', strike=False, opBlock_data={})
                    return False, True, []

            elif int(prev_block.index) < int(block.index) - 1:
                if get_missing_blocks:
                    create_job(retrieve_missing_blocks, job_timeout=150, worker='high', blockchain=block.Blockchain_obj, target_node=block.CreatorNode_obj.id, starting_point=prev_block.index + 1)
            elif int(prev_block.index) > int(block.index):
                # problem if blocks are not valid, should check previous blocks?
                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=block.Blockchain_obj, starting_index=block.index, send_to=block.CreatorNode_obj.id)
            elif int(prev_block.index) + 1 == int(block.index):
                if get_missing_blocks:
                    create_job(retrieve_missing_blocks, job_timeout=150, worker='high', blockchain=block.Blockchain_obj, target_node=block.CreatorNode_obj.id, starting_point=prev_block.index)

        if not carry_on:
            invalidate(block, note='did_not_pass_discrepenacies3', strike=True, opBlock_data={})
            return False, True, []
    
    if prev_block and get_objType(prev_block) != 'Blockchain' and prev_block.validated == None:
        prntDebug('p1.2 waiting on prev_block',prev_block.id,'block.id',block.id)
        return None, False, []
    if prev_block and get_objType(prev_block) == 'Block' and prev_block.hash == block.prv_hash and prev_block.validated == False:
        prntDebug('p1.5 prev_block_not_valid1',prev_block.id,'block.id',block.id)
        invalidate(block, note='prev_block_not_valid', strike=False, opBlock_data={})
        return False, True, []
    if prev_block and get_objType(prev_block) != 'Blockchain' and prev_block.index != block.index - 1:
        prntDebug('p1.3 wrong_index',block.id)
        invalidate(block, note='wrong_index', strike=False, opBlock_data={})
        return False, True, []
    if not prev_block and block.index > 1:
        prntDebug('p1.4 no_prev_block',block.id)
        if get_missing_blocks:
            if not retrieve_missing_blocks(blockchain=block.Blockchain_obj, genesisId=None, target_node=None, starting_point=block.prv_hash, items_to_get=2, retrieve_following=False):
                check_validation_consensus(block, do_mark_valid=do_mark_valid, broadcast_if_unknown=broadcast_if_unknown, downstream_worker=downstream_worker, handle_discrepancies=handle_discrepancies, backcheck=backcheck, get_missing_blocks=False, next_block=next_block)
                return False, False, []
        prntDebug('p1.4.2 no_prev_block',block.id)
        invalidate(block, note='no_prev_block', strike=False, opBlock_data={})
        return False, True, []
    if prev_block:
        prev_required_validators = prev_block.get_required_validator_count()
        prev_required_consensus = prev_block.get_required_consensus()
        prev_creator_nodes, prev_validator_list, prev_broadcast_list = prev_block.get_assigned_nodes(fetch_broadcast_list=False)
        prnt('prev_validator_list',prev_validator_list)
        prnt('prev_creator_nodes',prev_creator_nodes)
        prnt('prev_block.id',prev_block.id)
        prnt('prev_block.networkChain',prev_block.networkChain)
        prnt('prev_required_validators',prev_required_validators)
        if prev_block.networkChain == _OperationsChain_genesisId:
            max_val_dt_full = prev_block.DateTime
            prev_validator_list = prev_creator_nodes
            prev_required_validators = len(prev_creator_nodes)
        else:
            from network.models import block_time_delay
            max_val_dt_full = string_to_dt(prev_block.created) + datetime.timedelta(minutes=(block_time_delay(prev_block)))
        prev_validators = list(Validator.objects.filter(jobId=prev_block.id, validatorType='Block', networkChain=prev_block.networkChain).filter(CreatorNode_obj__id__in=prev_validator_list[:prev_required_validators], created__gte=string_to_dt(prev_block.created), created__lt=max_val_dt_full).distinct('CreatorNode_obj__id').order_by('CreatorNode_obj__id','created'))
        prnt('prev_validators',len(prev_validators))

        if prev_block.validations and len(prev_block.validations) > len(prev_validators):
            prnt('prev_block.validations',prev_block.validations)
            other_vals = Validator.objects.filter(id__in=[key for key in prev_block.validations], created__gte=string_to_dt(prev_block.created)).exclude(id__in=[v.id for v in prev_validators]).only('id')
            found_vals = [v.id for v in prev_validators] + [v.id for v in other_vals]
            missing_vals = [val_id for val_id in prev_block.validations if val_id not in found_vals]
            prnt('missing_vals',missing_vals)
            if missing_vals:
                retreived_vals_list = request_items(missing_vals, supported_chain_list=prev_block.networkChain, return_updated_objs=True, check_consensus=False, get_missing_blocks=False, override_completed=False)
                prnt('retreived_vals_list',retreived_vals_list)
                if retreived_vals_list:
                    prev_validators += [v for v in retreived_vals_list if v.CreatorNode_obj.id in validator_list[:required_validators] and v not in validations]
        
        if block.extraData:
            prnt('block.extraData',block.extraData)
            from utils.models import get_pointer_type
            if any(v for v in block.extraData if get_pointer_type(v) == 'Validator' and v not in [v.id for v in prev_validators]):
                fetch = [v for v in block.extraData if get_pointer_type(v) == 'Validator' and v not in [v.id for v in prev_validators]]
                existing_vals = Validator.objects.filter(id__in=fetch).values('id')
                fetch = [i for i in fetch if i not in [v['id'] for v in existing_vals]]
                if not fetch:
                    retreived = request_items(requested_items=fetch, nodes=[prev_block.CreatorNode_obj], request_validators=False, return_updated_count=True, return_updated_ids=True, return_missing=False, check_consensus=False, downstream_worker=False, get_missing_blocks=False, override_completed=True)
                    if retreived:
                        prev_validators = Validator.objects.filter(jobId=prev_block.id, validatorType='Block', networkChain=prev_block.networkChain).filter(CreatorNode_obj__id__in=prev_validator_list[:prev_required_validators], created__gte=string_to_dt(prev_block.created), created__lt=max_val_dt_full).distinct('CreatorNode_obj__id').order_by('CreatorNode_obj__id','created')
                        prnt('retreived prev_validators',len(prev_validators))
        prev_validations = []
        for v in prev_validators:
            if not check_commit_data(prev_block, v.data[prev_block.id]):
                prnt('vax1',v.id)
                pass
            elif v.CreatorNode_obj.expelled_dt and v.CreatorNode_obj.expelled_dt < prev_block.created:
                prnt('vax2',v.CreatorNode_obj.expelled_dt,v.id)
                pass
            elif v.id in block.extraData:
                prnt('va1',v.id)
                if check_commit_data(v, block.extraData[v.id]):
                    prev_validations.append(v)
                else:
                    prnt('vax4')
            else:
                prnt('vax3',v.id)
        prev_is_valid_vals = [v for v in prev_validations if v.is_valid]
        prnt('is_valid_vals',len(prev_is_valid_vals))
        prev_total = len(prev_validations)
        if prev_block.networkChain == _OperationsChain_genesisId:
            prev_required_validators = prev_total
        if len(prev_is_valid_vals):
            prev_percent = len(prev_is_valid_vals) / prev_total * 100
        else:
            prev_percent = 0
        prnt('prev_percent1',prev_percent, 'prev_total',prev_total,'prev_required_validators',prev_required_validators,'(prev_required_consensus*100)',(prev_required_consensus*100))
        if prev_total < prev_required_validators or prev_percent < (prev_required_consensus*100):
            invalidate(block, note='prevBlock_val_fail', strike=False, opBlock_data={})
            return False, True, []
    
    
    if handle_discrepancies:
        competing_index = Block.objects.filter(Blockchain_obj=block.Blockchain_obj, index=block.index, validated=True).exclude(id=block.id).defer('data','extraData','notes')
        if competing_index:
            winning_block, validations = resolve_block_differences(block, competing_blocks=competing_index)
            if winning_block:
                if winning_block != block:
                    create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=block.Blockchain_obj, starting_index=winning_block.index, send_to=block.CreatorNode_obj.id)
                    
                    if winning_block.validated:
                        return True, True, validations
                    else:
                        from utils.models import exists_in_worker
                        if not exists_in_worker('check_validation_consensus', queue_name=['main','high'], block=winning_block):
                            import django_rq
                            if winning_block.networkChain == _OperationsChain_genesisId:
                                queue = django_rq.get_queue('high')
                            else:
                                queue = django_rq.get_queue('main')
                            queue.enqueue(check_validation_consensus, winning_block, job_timeout=300, result_ttl=7200)
                        invalidate(block, note='did_not_pass_discrepenacies4', strike=False, opBlock_data={})
                        return False, True, []
            else:
                invalidate(block, note='did_not_pass_discrepenacies5', strike=False, opBlock_data={})
                return False, True, []
    
    def check_validators(val_obj, inputted_data={}, do_mark_valid=True, opBlock_data={}, broadcast_if_unknown=False):
        prnt('-check_validators',val_obj)
        is_new_validation = False
        is_valid = None
        if get_objType(val_obj) == 'Block':
            obj_is_block = True
            networkChainId = val_obj.networkChain
            block_id = val_obj.id
            block_created_dt = string_to_dt(val_obj.created)
            block_dt = string_to_dt(val_obj.DateTime)
            creator_nodes = inputted_data['creator_nodes']
            validator_list = inputted_data['validator_list']
            required_validators = inputted_data['required_validators']
            required_consensus = inputted_data['required_consensus']
            block_delay = inputted_data['block_delay']
            broadcast_list = inputted_data['broadcast_list']
            next_block = inputted_data['next_block']
            prnt('block -- ',inputted_data )
        else:
            obj_is_block = False
            if val_obj.SenderBlock_obj and val_obj.SenderBlock_obj.validated == False and val_obj.SenderBlock_obj != inputted_data['block']:
                is_valid, consensus_found, validations = check_validation_consensus(val_obj.SenderBlock_obj, do_mark_valid=True, handle_discrepancies=False, backcheck=False, get_missing_blocks=False, downstream_worker=False)
                if not is_valid and consensus_found:
                    prnt('hard false')
                    return False, True, []
            genesis_id = val_obj.ReceiverWallet_obj.id
            networkChainId = val_obj.senderChainGenId
            block_id = val_obj.senderBlockId
            block_created_dt = string_to_dt(val_obj.created)
            block_dt = block_created_dt
            obj_commit_data = get_commit_data(val_obj)
            temp_block = Block(id=block_id, Transaction_obj=val_obj, DateTime=val_obj.created, Blockchain_obj=Blockchain.objects.filter(genesisId=val_obj.regarding['GenesisId']).first())
            
            next_block = inputted_data['next_block']
            block_delay = inputted_data['block_delay']

            required_validators = temp_block.get_required_validator_count() # do not pass opBlock_data here, may need different block
            required_consensus = temp_block.get_required_consensus()
            creator_nodes, validator_list, broadcast_list = temp_block.get_assigned_nodes(fetch_broadcast_list=False)

            prnt('transaction -- creator_nodes',creator_nodes,'validator_list',validator_list,'block_dt',block_dt,'block_created_dt',block_created_dt,'block_id',block_id,'blockchainId',networkChainId,'next_block',next_block)
        
        
        self_node_id = get_operator_obj('self_nodeId')
        prnt('-proceed to check consensus')
        obj_commit_data = get_commit_data(val_obj)
        prnt('obj_commit_data',obj_commit_data)
        obj_commit_data = json.loads(json.dumps(obj_commit_data, sort_keys=True))
        prnt('obj_commit_data2',obj_commit_data)
        prnt('networkChainId',networkChainId)
        prnt('val_obj.id',val_obj.id)
        prnt('validator_list[:required_validators]',validator_list[:required_validators])
        prnt('block_created_dt',block_created_dt)
        if obj_is_block and val_obj.networkChain == _OperationsChain_genesisId:
            max_val_dt_half = val_obj.DateTime
            max_val_dt_full = val_obj.DateTime
            validator_list = creator_nodes
            required_validators = len(validator_list)
            prnt('validator_list[:required_validators]',validator_list[:required_validators])
        else:
            max_val_dt_half = block_created_dt + datetime.timedelta(minutes=(block_delay/2))
            max_val_dt_full = block_created_dt + datetime.timedelta(minutes=(block_delay))
        prnt('max_val_dt_half',max_val_dt_half)
        prnt('next_block',next_block)

        validations = list(Validator.objects.filter(jobId=block_id, validatorType='Block', networkChain=networkChainId).filter(data__has_key=val_obj.id).filter(CreatorNode_obj__id__in=validator_list[:required_validators], created__gte=block_created_dt, created__lt=max_val_dt_full).distinct('CreatorNode_obj__id').order_by('CreatorNode_obj__id','created'))
        prnt('validations',len(validations))

        if val_obj.validations and len(val_obj.validations) > len(validations):
            prnt('val_obj.validations',val_obj.validations)
            other_vals = Validator.objects.filter(id__in=[key for key in val_obj.validations], created__gte=block_created_dt).exclude(id__in=[v.id for v in validations]).only('id')
            found_vals = [v.id for v in validations] + [v.id for v in other_vals]
            missing_vals = [val_id for val_id in val_obj.validations if val_id not in found_vals]
            prnt('missing_vals',missing_vals)
            if missing_vals:
                retreived_vals_list = request_items(missing_vals, supported_chain_list=networkChainId, return_updated_objs=True, check_consensus=False, get_missing_blocks=False, override_completed=False)
                prnt('retreived_vals_list',retreived_vals_list)
                if retreived_vals_list:
                    validations += [v for v in retreived_vals_list if v.CreatorNode_obj.id in validator_list[:required_validators] and v not in validations]
        if len(validations) < required_validators and now_utc() > max_val_dt_half:
            prnt('max_val_dt_half',max_val_dt_half,'now_utc()',now_utc())
            requests = [n for n in validator_list[:required_validators] if n not in [v.CreatorNode_obj.id for v in validations]]
            if requests:
                for n in requests:
                    retreived_vals_list = request_items([val_obj.id], nodes=[n], request_validators=True, supported_chain_list=networkChainId, return_updated_objs=True, check_consensus=False, get_missing_blocks=False, override_completed=False)
                    prnt('retreived_vals_list2',retreived_vals_list)
                    if retreived_vals_list:
                        validations += [v for v in retreived_vals_list if v.CreatorNode_obj.id in validator_list[:required_validators] and v not in validations]


        def check_is_valid(validations, val_obj, creator_nodes, validator_list, required_validators, broadcast_list, block_created_dt, max_val_dt_full, block_delay, do_mark_valid, obj_is_block, broadcast_if_unknown):
            prnt('check_is_valid validations',len(validations))
            is_valid_vals = [v for v in validations if v.is_valid]
            prnt('is_valid_vals',len(is_valid_vals))
            total = len(validations)
            if len(is_valid_vals):
                percent = len(is_valid_vals) / total * 100
            else:
                percent = 0
            prnt('percent1',percent, 'total',total,'required_validators',required_validators)
            if total < required_validators:
                if obj_is_block and val_obj.networkChain != _OperationsChain_genesisId:
                    if do_mark_valid and obj_is_block and now_utc() >= (block_created_dt + datetime.timedelta(minutes=9)) and now_utc() < max_val_dt_full and val_obj.validated == None:
                        # rebraodcast blcok to all missing validators
                        prnt(f're broadcasting block {block_id}, total vals:{total}, required_validators:{required_validators}')
                        broadcast_block_to = [n for n in validator_list[:required_validators] if n not in [v.CreatorNode_obj.id for v in validations]]
                        val_obj.broadcast(broadcast_list=broadcast_list, validator_list=broadcast_block_to, validations=validations, validators_only=True, target_node_id=None)

                
                elif obj_is_block and val_obj.networkChain == _OperationsChain_genesisId:
                    if now_utc() >= (block_dt - datetime.timedelta(minutes=1)) and total:
                        required_validators = total
            try:
                prnt(f'total:{total}, required_validators:{required_validators}, (block_created_dt + datetime.timedelta(minutes=(block_delay))):{(block_created_dt + datetime.timedelta(minutes=(block_delay)-1.5))}')
            except Exception as e:
                prnt('err 4932',str(e))

            if total < required_validators and now_utc() > (block_created_dt + datetime.timedelta(minutes=(block_delay)-1.5)):
                if obj_is_block and do_mark_valid:
                    val_obj.is_not_valid(note='timed_out')
                prntDebug('p6 timed_out',block_id)
                return False, True, []
            prntDebug('check consensus stage3')
            save_block = False
            for v in validations:
                if v.id not in val_obj.validations:
                    val_obj.validations[v.id] = get_commit_data(v)
                    save_block = True
            if save_block:
                val_obj.save(update_fields=['validations'])

            prnt(f'percent2:{percent} total:{total} required_validators:{required_validators} required_consensus:{(required_consensus)}')
            if total >= required_validators and percent >= (required_consensus*100):
                prntDebug('stage3 opt1',obj_is_block,do_mark_valid,val_obj)
                completed_validation = True
                save_block = False
                for validator in validations:
                    if validator.id not in val_obj.validations:
                        val_obj.validations[validator.id] = get_commit_data(validator)
                        save_block = True
                if save_block:
                    val_obj.save(update_fields=['validations'])
                if obj_is_block and do_mark_valid:
                    completed_validation = val_obj.mark_valid(downstream_worker=downstream_worker)
                if do_mark_valid and obj_is_block and not val_obj.validated and now_utc() < (block_created_dt + datetime.timedelta(hours=3)):
                    val_obj.broadcast(validations=validations, validators_only=False, target_node_id=None)
                return completed_validation, True, validations
            elif total >= required_validators and percent < (required_consensus*100):
                prntDebug(f'stage3 opt2, total:{total}, required_validators:{required_validators}')
                if obj_is_block and val_obj.validated != False and do_mark_valid:
                    prnt("now_utc() < (block_created_dt + datetime.timedelta(hours=24))", now_utc(), (block_created_dt + datetime.timedelta(hours=24)),val_obj.id)
                    val_obj.is_not_valid(note='failed_by_validators')
                    if now_utc() < max_val_dt_full and do_mark_valid:
                        if any(v for v in validations if string_to_dt(v.created) > block_created_dt + datetime.timedelta(minutes=(block_delay/2))):
                            prnt('xa1')
                            val_obj.broadcast(validator_list=validator_list, validations=validations, validators_only=False, target_node_id=None)
                        else:
                            prnt('xa2')
                            validator_list += creator_nodes
                            val_obj.broadcast(validator_list=validator_list, validations=[v for v in validations if v.CreatorNode_obj.id == self_node_id], validators_only=True, target_node_id=None)
                return False, True, validations
            
            if obj_is_block:
                if broadcast_if_unknown and now_utc() < max_val_dt_full and val_obj.validated == None:
                    # broadcast to all nodes
                    prnt('re broadcast_if_unknown',broadcast_if_unknown)
                    val_obj.broadcast(validations=validations, validators_only=False, target_node_id=None)
            prnt('end check_validators',val_obj)
            return is_valid, False, validations
        

        def val_is_val(v, val_obj, validations, next_block):
            if not check_commit_data(val_obj, v.data[val_obj.id]):
                prnt('vx1')
                pass
            elif v.CreatorNode_obj.expelled_dt and v.CreatorNode_obj.expelled_dt < val_obj.created:
                prnt('vx2',v.CreatorNode_obj.expelled_dt)
                pass
            elif next_block and v.id in next_block.extraData:
                prnt('v2')
                if check_commit_data(v, next_block.extraData[v.id]):
                    if verify_obj_to_data(v, v):
                        validations.append(v)
            elif not next_block:
                prnt('v4')
                if verify_obj_to_data(v, v):
                    validations.append(v)
            else:
                prnt('else')
                prnt(convert_to_dict(v))
            return validations
        # vals must be on next_block if next_block or block.Block_obj
        if next_block:
            next_blocks = [next_block]
        else:
            if next_block_must_val or do_mark_valid:
                next_blocks = list(Block.objects.filter(networkChain=block.networkChain, prv_hash=block.hash, validated=True).only('extraData'))
            else:
                next_blocks = list(Block.objects.filter(networkChain=block.networkChain, prv_hash=block.hash).exclude(validated=False).only('extraData'))
        initial_vals_list = []
        if block.Block_obj and block.Block_obj.validated:
            for v in validations:
                initial_vals_list = val_is_val(v, val_obj, initial_vals_list, block.Block_obj)
        if not next_blocks:
            validations_list = initial_vals_list
            for v in validations:
                prnt('v_id1',v.id)
                validations_list = val_is_val(v, val_obj, validations_list, None)
            return check_is_valid(validations_list, val_obj, creator_nodes, validator_list, required_validators, broadcast_list, block_created_dt, max_val_dt_full, block_delay, do_mark_valid, obj_is_block, broadcast_if_unknown)
        else:
            prnt('next_blocks len',len(next_blocks))
            any_is_valid = False
            greatest_validations = []
            for next_block in next_blocks:
                prnt('next_block val check',next_block)
                validations_list = initial_vals_list
                for v in validations:
                    prnt('v_id2',v.id)
                    validations_list = val_is_val(v, val_obj, validations_list, next_block)

                is_valid, consensus_found, validations_list = check_is_valid(validations_list, val_obj, creator_nodes, validator_list, required_validators, broadcast_list, block_created_dt, max_val_dt_full, block_delay, do_mark_valid, obj_is_block, broadcast_if_unknown)
                if is_valid:
                    any_is_valid = True
                    if len(validations_list) > len(greatest_validations):
                        greatest_validations = validations_list
                if is_valid and consensus_found:
                    return is_valid, next_block.id, validations_list
            if any_is_valid:
                return True, False, greatest_validations
            else:
                prnt('none is valid')
                return False, True, []

            
    prntDebug('next stage')
    required_validators = block.get_required_validator_count()
    required_consensus = block.get_required_consensus()
    self_node_id = get_operator_obj('self_nodeId')
    prntDebug('required_validators',required_validators)
    prntDebug('required_consensus',required_consensus)
    prntDebug('block_delay',block_delay)

    creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=True)
        
    prntDebug(f"-creator_nodes:{creator_nodes}, -broadcast_list:{broadcast_list}, -validator_list:{validator_list}")
    prntDebug('validator_list[:required_validators]',validator_list[:required_validators],'self_node.id',self_node_id)
    prnt(f'now_utc:{now_utc()} ---(b_ct + datetime.timedelta(minutes=(block_delay*(3/4))+1)): {(b_ct + datetime.timedelta(minutes=(block_delay*(3/4))+1))}')

    if block.networkChain != _OperationsChain_genesisId and block.CreatorNode_obj.id not in creator_nodes:
        prntDebug(f'p3 wrong_creator, block.CreatorNode_obj.id:{block.CreatorNode_obj.id}, creator_nodes:{creator_nodes}',block.id)
        invalidate(block, note='wrong_creator', strike=True)
        return False, True, []
    if create_val and self_node_id in validator_list[:required_validators]:
        prnt(f'self assigned as validator, {(b_ct + datetime.timedelta(minutes=(block_delay/2)+1))}')
        prnt({f"data__{block.id}": get_commit_data(block)})
        validator = Validator.objects.filter(validatorType='Block', networkChain=block.networkChain, jobId=block.id).filter(CreatorNode_obj__id=self_node_id).exists()
        if not validator and now_utc() < (b_ct + datetime.timedelta(minutes=(block_delay/2)+1)):
            is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes)
            if is_new_validation:
                validator_list = validator_list + [block.CreatorNode_obj.id]

    if block.Transaction_obj:
        if not block.Transaction_obj.SenderWallet_obj:
            carry_on = False
            if 'BlockReward' in block.Transaction_obj.regarding:
                if block.Transaction_obj.regarding['BlockReward'] == block.id:
                    # inputted region block with reward
                    carry_on = True
                    if not block.Transaction_obj.SenderBlock_obj:
                        block.Transaction_obj.SenderBlock_obj = block
                        block.Transaction_obj.save(update_fields=['SenderBlock_obj'])
                elif block.Blockchain_obj.genesisId == block.Transaction_obj.ReceiverWallet_obj.id:
                    # inputted wallet reward block
                    # below will check validators of corresponding region block
                    transaction_is_valid, transaction_consensus_found, transaction_validators = check_validators(block.Transaction_obj, {'block_delay':region_block_delay,'next_block':next_block,'block':block}, do_mark_valid=False, broadcast_if_unknown=broadcast_if_unknown)
                    prnt('transaction_is_valid',transaction_is_valid,'transaction_consensus_found',transaction_consensus_found)
                    if not transaction_consensus_found:
                        return False, False, []
                    if transaction_is_valid and transaction_consensus_found:
                        carry_on = True
                    
            if not carry_on:
                prnt('p2 transaction_err1',block.id)
                invalidate(block, note='transaction_err1', strike=True)
                return False, True, []
            
    return check_validators(block, {'creator_nodes':creator_nodes,'validator_list':validator_list,'required_validators':required_validators,'required_consensus':required_consensus,'block_delay':block_delay,'broadcast_list':broadcast_list, 'next_block':next_block}, do_mark_valid=do_mark_valid, broadcast_if_unknown=broadcast_if_unknown)


def validate_block(block, creator_nodes=None, opBlock_data={}, create_validator=True, fail_reason=None):
    from utils.models import get_operator_obj, get_objType, sigData_to_hash,now_utc,prnt,dt_to_string,is_id, get_chain_id, toBroadcast
    prnt('---validate_block', block, now_utc(),'fail_reason',fail_reason)
    from network.models import Validator, Block, _OperationsChain_genesisId, _block_creation_times, reward_models
    self_node_id = get_operator_obj('self_nodeId')
    if block.Block_obj:
        return None, None, None
    validator = Validator.objects.filter(validatorType='Block', networkChain=block.networkChain, jobId=block.id, CreatorNode_obj__id=self_node_id).defer('data').first()
    if validator:
        is_new_validation = False
        fail_reason = 0
    else:
        validated = False
        prnt('create val')
        if not fail_reason:
            transaction_type = None
            fail_reason = 1
            hard_pass = False
            proceed_to_valid = False
            prev_block = block.get_previous_block(is_validated=True, return_chain=False)
            if not block.networkChain and block.DateTime.minute not in _block_creation_times:
                hard_pass = True
                fail_reason = 751
            elif not block.data and not block.Transaction_obj: # not sure if all transaction blocks will contain data
                hard_pass = True
                fail_reason = 752
            elif not prev_block or get_objType(prev_block) == 'Blockchain' or prev_block.validated:
                pass
            elif prev_block.validated == False:
                hard_pass = True
                fail_reason = 76
            elif prev_block.validated == None:
                return None, None, None # wait for result of prev_block
            if not hard_pass and block.Transaction_obj:
                carry_on = False
                if 'BlockReward' in block.Transaction_obj.regarding:
                    

                    if block.Transaction_obj.regarding['BlockReward'] == block.id and 'Rewards' in block.Transaction_obj.ReceiverWallet_obj.Name:
                        if block.Transaction_obj.token_value == calculate_reward(block.DateTime, prev_block):
                            from posts.models import Region
                            if not Region.objects.filter(id=block.Blockchain_obj.genesisId, Block_obj__validated=True, is_supported=True).exists():
                                hard_pass = True
                                fail_reason = 760
                                prnt('fail_reason',fail_reason)
                            else:
                                hard_pass = False
                                transaction_type = 'sender'

                                if any(prefix for prefix in reward_models if block.Blockchain_obj.genesisId.startswith(prefix)):
                                    from legis.models import Government
                                    gov = Government.objects.filter(id=block.Blockchain_obj.genesisId, Validator_obj__is_valid=True, Region_obj__is_supported=True, Region_obj__Validator_obj__is_valid=True).first()
                                    if not gov or not gov.StartDate:
                                        hard_pass = True
                                        fail_reason = 761
                                        prnt('fail_reason',fail_reason)
                                    
                                    from network.models import Blockchain
                                    future_govs = Government.objects.filter(Region_obj=gov.Region_obj, StartDate__gte=gov.StartDate, Validator_obj__is_valid=True).values('id')
                                    if future_govs and Blockchain.objects.filter(genesisId__in=[g['id'] for g in future_govs], chain_length__gt=0).exists():
                                        hard_pass = True
                                        prnt('fail_reason',fail_reason)
                                        fail_reason = 762
                                    
                                    if not future_govs and block.Blockchain_obj.chain_length == 0:
                                        prev_gov = Government.objects.filter(Region_obj=gov.Region_obj, StartDate__lt=gov.StartDate, Validator_obj__is_valid=True).order_by('-StartDate').first()
                                        if prev_gov and not prev_gov.EndDate:
                                            hard_pass = True
                                            fail_reason = 763
                                            prnt('fail_reason',fail_reason)
                                        elif prev_gov and prev_gov.EndDate:
                                            if not prev_gov.Block_obj or not (prev_gov.id in prev_gov.Block_obj.data and check_commit_data(prev_gov, prev_gov.Block_obj.data[prev_gov.id])):
                                                hard_pass = True
                                                fail_reason = 764
                                                prnt('fail_reason',fail_reason)

                    elif block.Transaction_obj.ReceiverWallet_obj and block.Transaction_obj.ReceiverWallet_obj.id == block.Blockchain_obj.genesisId and 'Rewards' in block.Transaction_obj.ReceiverWallet_obj.Name:
                        hard_pass = False
                        transaction_type = 'receiver'
                    else:
                        hard_pass = True
                        fail_reason = 72

                elif not block.Transaction_obj.SenderWallet_obj:
                    fail_reason = 73
                    hard_pass = True
                elif block.Transaction_obj.ReceiverWallet_obj == block.Blockchain_obj:
                    transaction_type = 'receiver'
                elif block.Transaction_obj.SenderWallet_obj == block.Blockchain_obj:
                    transaction_type = 'sender'
                else:
                    fail_reason = 74
                    hard_pass = True
            
            prnt(' block.get_previous_hash()', block.get_previous_hash())
            prnt('block.prv_hash',block.prv_hash)
            if not hard_pass and block.get_previous_hash() == block.prv_hash:
                fail_reason = 2
                target_hash = sigData_to_hash(block, exclude_fields=['signed'])
                received_hash = block.hash
                prnt('received_hash',received_hash,'target_hash',target_hash)
                if received_hash == target_hash:
                    fail_reason = 3
                    if not creator_nodes:
                        if block.Transaction_obj:
                            if transaction_type == 'sender':
                                creator_nodes, validator_nodes = get_node_assignment(block.Transaction_obj, opBlock_data=opBlock_data)
                            elif transaction_type == 'receiver':
                                creator_nodes, validator_nodes = get_node_assignment(block, return_receiverTransaction=True, opBlock_data=opBlock_data)
                            else:
                                creator_nodes, validator_nodes = get_node_assignment(block, opBlock_data=opBlock_data)
                        else:
                            creator_nodes, validator_nodes = get_node_assignment(block, opBlock_data=opBlock_data)
                    prnt('creator_nodes',creator_nodes,'block.CreatorNode_obj',block.CreatorNode_obj)
                    if block.CreatorNode_obj.id in creator_nodes:
                        fail_reason = 4
                        if verify_obj_to_data(block, block):
                            fail_reason = 701
                            if not block.Transaction_obj:
                                proceed_to_valid = True
                            elif verify_obj_to_data(block.Transaction_obj, block.Transaction_obj):
                                fail_reason = 702
                                proceed_to_valid = True
                            else:
                                fail_reason = 703
                    prnt('proceed to attempt validation:',proceed_to_valid)
                    if block.CreatorNode_obj.expelled_dt:
                        proceed_to_valid = False
                        fail_reason = 704

                    if not proceed_to_valid:
                        if block.Transaction_obj:
                            prnt('rewardData',convert_to_dict(block.Transaction_obj))
                    
                    if proceed_to_valid:

                        # check that prev_block validators are all acccounted for on block
                        opChainId = get_chain_id(_OperationsChain_genesisId)
                        if prev_block:
                            fail_reason = []
                            for v in Validator.objects.filter(networkChain=_OperationsChain_genesisId, validatorType='Block', jobId=prev_block.id, Block_obj=None):
                                if v.id not in block.data and v.id not in block.extraData:
                                    fail_reason.append(v.id)
                                    hard_pass = True
                                    prnt(f'v.id not in block.data fail_reason:{v.id}')
                                elif v.id in block.data and not check_commit_data(v, block.data[v.id]):
                                    fail_reason.append(v.id)
                                    hard_pass = True
                                    prnt(f'check_commit_data fail_reason:{v.id}')
                                elif v.id in block.extraData and not check_commit_data(v, block.extraData[v.id]):
                                    fail_reason.append(v.id)
                                    hard_pass = True
                                    prnt(f'check_commit_data fail_reason:{v.id}')
                        if not hard_pass:
                            fail_reason = 100
                            if block.networkChain == _OperationsChain_genesisId:
                                fail_reason = 101
                                
                                if block.Blockchain_obj.verify_new_opBlock_data(block):
                                    prnt('valid = true22 Nodes')
                                    validated = True
                                    fail_reason = 'None'
                            else:

                                found_idens, missing_idens = check_block_contents(block, retrieve_missing=True, log_missing=False, downstream_worker=False, return_missing=True, uncommitted_required=True)
                                if missing_idens or 'unsupported_chain' in block.notes:
                                    block.refresh_from_db()
                                if not found_idens:
                                    fail_reason = 103
                                    prnt('not valid 1a')
                                    validated = False

                                elif any(i for i in block.data if i not in found_idens and is_id(i)):
                                    fail_reason = 113
                                    prnt('not valid 1b')
                                    validated = False
                                    fail_reason = []
                                    for iden, commit in block.data.items():
                                        if iden != 'meta' and is_id(iden) and iden not in found_idens:
                                            validated = False
                                            fail_reason.append(iden)
                                    prnt(f'invalid contents = {str(fail_reason)[:250]}')
                                elif any(i for i in block.extraData if i not in found_idens and is_id(i)):
                                    fail_reason = 113
                                    prnt('not valid 1c')
                                    validated = False
                                    fail_reason = []
                                    for iden, commit in block.extraData.items():
                                        if iden != 'meta' and is_id(iden) and iden not in found_idens:
                                            validated = False
                                            fail_reason.append(iden)
                                    prnt(f'invalid contents = {str(fail_reason)[:250]}')
                                else:
                                    validated = True
            
        prnt('setp3 is_valid:', validated)
        validator = Validator(CreatorNode_obj_id=self_node_id, jobId=block.id, networkChain=block.networkChain, validatorType='Block', func='tasker')
        validator.data[block.id] = get_commit_data(block)
        if block.Transaction_obj:
            validator.data[block.Transaction_obj.id] = get_commit_data(block.Transaction_obj)
        if not validated:
            validator.data['fail_reason'] = fail_reason
            prnt('fail_reason',fail_reason)
        is_new_validation = True
        validator.is_valid = validated
        if create_validator:
            validator_check = Validator.objects.filter(validatorType='Block', networkChain=block.networkChain, jobId=block.id, CreatorNode_obj__id=self_node_id).defer('data').first()
            if validator_check:
                validator = validator_check
            else:
                validator.save(skip_check=True)
                validator = sign_obj(validator)
                prnt('created validator',validator, dt_to_string(now_utc()))
                block.validations[validator.id] = get_commit_data(validator)
                block.save()
                toBroadcast(validator.id, extra={'re':block.id})
                block.broadcast(validators_only=True)
        prnt('done validating block',block.id)
    prnt('validator:',validator,"is_new_validation",is_new_validation,'validator.is_valid',validator.is_valid,'fail_reason',str(fail_reason)[:300])
    return validator.is_valid, validator, is_new_validation

def calculate_reward(dt, previous_dt):
    from utils.models import prnt, now_utc, string_to_dt
    dt = string_to_dt(dt)
    prnt('-calculate_reward',dt)
    if previous_dt:
        from django.db import models
        if isinstance(previous_dt, models.Model):
            if previous_dt._meta.object_name == 'Block':
                previous_dt = previous_dt.DateTime
            else:
                previous_dt = None
        previous_dt = string_to_dt(previous_dt)
    # from blockchain.models import Sonet, _golden_ratio
    # import math
    # # 100 coins reduced by the golden ration every 4th anniversary of sonet creation
    # if not dt:
    #     dt = now_utc()
    # if not isinstance(dt, datetime.datetime):
    #     dt = string_to_dt(dt)
    # # from accounts.models import Sonet
    # sonet = Sonet.objects.only('created').first()
    # years_since = (dt.year - sonet.created.year)
    # num = math.floor(years_since / 4)
    # reward = 100
    # reward = reward / (_golden_ratio ** num)
    # prnt('reward',reward)
    # return str(reward)

    """
    Block reward for a multi-region-chain network, with supply that scales
    with adoption rather than being split by it.

    Model recap
    ------------
    - Every region runs its own chain and mints its own blocks (~hourly).
    - Each region follows the SAME per-region decay curve, independent of how
    many other regions exist -- a region's reward decays the same way a
    single mine's output declines as it's worked, regardless of how many
    other mines are open elsewhere. This is region_emission_rate() /
    block_reward(): no region-count term in either one.
    - Because every active region mints independently and undivided, total
    network-wide issuance is (roughly) proportional to how many regions are
    active: more adoption -> more parallel minting -> more total tokens.
    This is the quantity-theory-of-money idea (M*V = P*Y): if real usage
    (Y) grows as more regions come online, letting the money supply (M)
    grow with it is what keeps prices (P) from being squeezed by scarcity.
    - Total supply therefore no longer has a clean closed form (see the note
    on estimate_total_supply below) -- that's the deliberate tradeoff.
    Supply is now an emergent, adoption-driven quantity, not a predetermined
    one. On a real chain you don't need to compute it at all: it's just the
    running sum of every reward ever minted across every region's ledger.

    All times are in years since network genesis.
    """

    from decimal import Decimal
    import math
    from datetime import datetime, timezone

    # ---- Network genesis (adjust to the real launch date/time, UTC) ----
    # GENESIS_DATETIME = datetime(2020, 1, 1, tzinfo=timezone.utc)
    from network.models import Sonet
    GENESIS_DATETIME = Sonet.objects.values('created').first()['created']

    # # ---- Per-region monetary policy (this is what block_reward() actually uses) ----
    # TAU = 3.0                  # years; a region's own reward rate halves at TAU, 3*TAU, 7*TAU, ...
    #                             # (10, 30, 70, 150, 310... -- half gone within the first decade)
    # RHO_0_REGION = 26_298_000.0  # tokens/year a SINGLE region mints at genesis (-> 3,000 tokens/block)

    _golden_ratio = (1 + math.sqrt(5)) / 2
    TAU = _golden_ratio * 3
    HOURS_PER_YEAR = 8766.0                        # 365.25 * 24

    # for testing ------
    # ---- Adoption curve (informational: used for reporting/simulation, not for block_reward itself) ----
    N_0 = 3.0                        # regions active at genesis
    N_MAX = 100_000.0                 # regions once fully saturated (countries + states + cities)
    ADOPTION_MIDPOINT_YEARS = 50.0    # year at which N(t) crosses the halfway point to N_MAX
    DEFAULT_BLOCK_INTERVAL_YEARS = 1.0 / HOURS_PER_YEAR  # target ~1 hour between blocks

    _A = (N_MAX - N_0) / N_0
    _K = math.log(_A) / ADOPTION_MIDPOINT_YEARS
    # --------


    RHO_0_REGION = HOURS_PER_YEAR * 12000 # tokens/year a SINGLE region mints at genesis (-> 12,000 tokens/block)


    def active_regions(t_years: float) -> float:
        """Number of active region-chains at time t. Informational only --
        NOT used by block_reward(), only by the reporting helpers below."""
        return N_MAX / (1.0 + _A * math.exp(-_K * t_years))


    def region_emission_rate(t_years: float) -> float:
        """Instantaneous minting rate (tokens/year) for ONE region at time t.
        Every region shares this same curve regardless of how many other
        regions exist -- this is the whole design change from last time."""
        return RHO_0_REGION * TAU / (TAU + t_years)


    def region_cumulative_supply(t_years: float) -> float:
        """Total tokens ONE region would have minted from genesis through t."""
        if t_years <= 0:
            return 0.0
        return RHO_0_REGION * TAU * math.log(1.0 + t_years / TAU)


    def block_reward(current_time_years: float, previous_block_time_years: float = None) -> float:
        """
        Reward for a block produced on ONE region-chain at current_time_years.
        Depends only on this chain's own elapsed time -- not on how many other
        regions are active. (That's the point: region count now scales total
        supply by adding more independent minters, not by dividing a fixed pool.)

        previous_block_time_years:
            When this same chain last produced a block. Pass None for a
            chain's first-ever block -- assumes one target interval (1 hour)
            elapsed, so it's rewarded like a normal on-schedule block.

        Note: current_time_years must be > 0.
        """
        if current_time_years <= 0:
            raise ValueError(
                "current_time_years must be > 0 (use DEFAULT_BLOCK_INTERVAL_YEARS "
                "for the very first block)"
            )
        if previous_block_time_years is None:
            previous_block_time_years = max(0.0, current_time_years - DEFAULT_BLOCK_INTERVAL_YEARS)
        if previous_block_time_years > current_time_years:
            raise ValueError("previous_block_time_years cannot be after current_time_years")

        return region_cumulative_supply(current_time_years) - region_cumulative_supply(previous_block_time_years)


    def datetime_to_years(dt: datetime) -> float:
        """Convert a real timestamp into years-since-genesis."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt - GENESIS_DATETIME).total_seconds() / (365.25 * 24 * 3600)


    def block_reward_at_datetime(current_dt: datetime, previous_block_dt: datetime = None) -> float:
        """Same as block_reward(), but takes real datetimes."""
        current_time_years = datetime_to_years(current_dt)
        previous_block_time_years = (
            datetime_to_years(previous_block_dt) if previous_block_dt is not None else None
        )
        return block_reward(current_time_years, previous_block_time_years)


    # ---- Reporting / simulation only -- not needed by consensus, useful for planning ----

    def total_network_emission_rate(t_years: float) -> float:
        """Network-wide minting rate (tokens/year) at time t: one region's rate
        times how many regions are active. This is where 'more regions -> more
        total tokens' actually shows up."""
        return active_regions(t_years) * region_emission_rate(t_years)


    def estimate_total_supply(t_years: float, step: float = 0.01) -> float:
        """
        Numerically integrate total_network_emission_rate() from 0 to t_years.
        There's no closed form anymore -- total supply now depends on the
        actual adoption path, not just elapsed time, so it has to be
        accumulated (here, by simulation; on a real chain, by just summing
        every reward that's ever actually been minted).
        """
        total = 0.0
        t = 0.0
        while t < t_years:
            dt = min(step, t_years - t)
            total += total_network_emission_rate(t + dt / 2) * dt
            t += dt
        return total


    def run_scenario():
        milestones_years = [DEFAULT_BLOCK_INTERVAL_YEARS, 1, 2, 3, 4, 5, 7, 10, 25, 40, 50, 100, 200, 500]
        print(f"{'year':>10} {'regions':>10} {'block reward':>15} {'network/hr':>15} {'~total supply':>18}")
        for t in milestones_years:
            label = "0 (first)" if t == DEFAULT_BLOCK_INTERVAL_YEARS else str(t)
            regions = active_regions(t)
            reward = block_reward(t)
            net_per_hr = total_network_emission_rate(t) / HOURS_PER_YEAR
            supply = estimate_total_supply(t)
            print(f"{label:>10} {regions:>10.0f} {reward:>15,.0f} {net_per_hr:>15,.0f} {supply:>18,.0f}")


        reward = block_reward_at_datetime(
            current_dt=datetime(2026, 3, 6, 12, 0),
            previous_block_dt=datetime(2026, 3, 6, 11, 0),
        )
        print(f"{reward:,.0f} tokens (1)")
        reward = block_reward_at_datetime(
            current_dt=datetime(2027, 3, 6, 12, 0),
            previous_block_dt=datetime(2027, 3, 6, 11, 0),
        )
        print(f"{reward:,.0f} tokens (year 2)")
        reward = block_reward_at_datetime(
            current_dt=datetime(2036, 3, 6, 12, 0),
            previous_block_dt=datetime(2036, 3, 6, 11, 0),
        )
        print(f"{reward:,.0f} tokens (year 10)")
        reward = block_reward_at_datetime(
            current_dt=datetime(2051, 3, 6, 12, 0),
            previous_block_dt=datetime(2051, 3, 6, 11, 0),
        )
        print(f"{reward:,.0f} tokens (25)")
        reward = block_reward_at_datetime(
            current_dt=datetime(2076, 3, 6, 12, 0),
            previous_block_dt=datetime(2076, 3, 6, 11, 0),
        )
        print(f"{reward:,.0f} tokens (50)")
        reward = block_reward_at_datetime(
            current_dt=datetime(2126, 3, 6, 12, 0),
            previous_block_dt=datetime(2126, 3, 6, 11, 0),
        )
        print(f"{reward:,.0f} tokens (100)")
        print('_golden_ratio',TAU)


    reward = block_reward_at_datetime(
        current_dt=dt,
        previous_block_dt=previous_dt,
    )
    print(f"{reward:,.0f} tokens")
    return Decimal(str(reward))

def validate_obj(obj=None, pointer=None, validators=None, save_obj=True, update_pointer=True, verify_validator=True, add_to_queue=True, opBlock_data={}):
    # obj should be post
    from utils.models import prnt, now_utc, has_field
    prnt('--validate_obj now_utc:',obj,pointer, now_utc(),'save_obj',save_obj)
    validator = None
    target = None
    proceed = False
    validator_nodes = []
    err = '0'
    from posts.models import update_post, Post, Update
    if pointer and not obj and save_obj:
        obj = Post.objects.filter(pointerId=pointer.id).first()
    if obj and has_field(obj, 'validated') and not obj.validated and obj.id or pointer and update_pointer and not pointer.Validator_obj or obj and obj.id and has_field(obj, 'Validator_obj') and not obj.Validator_obj:
        from utils.models import prntDebug, sigData_to_hash, string_to_dt, find_or_create_chain_from_object, has_method, get_model, logEvent, declare_var, round_time, get_timeData, request_items, get_objType
        from network.models import Validator, max_validation_window
        validators = declare_var(validators, {})
        if obj and get_objType(obj) == 'Post':
            if not pointer:
                pointer, obj = obj.get_pointer(return_self=True, do_save=False)
            if pointer:
                target = pointer
        elif obj:
            target = obj
        elif pointer:
            target = pointer
        if target:
            prnt('target',target.id)
            if has_field(target, 'proposed_modification') and target.proposed_modification:
                prnt('target is proposed_modification')
                return False
        
        if target and not proceed:
            if validators:
                prnt('has validators', validators)
                if all(validator.func.lower() == 'super' and validator.CreatorNode_obj.User_obj.assess_super_status(dt=string_to_dt(validator.created)) for validator in validators):
                    validator = None
                    validator_nodes = [validator.CreatorNode_obj.id for validator in validators]
                    for val in validators:
                        if val.CreatorNode_obj.id == validator_nodes[0]:
                            prnt('val',val.id,'is in validator_nodes')
                            validator = val
                    if validator:
                        proceed = True
                else:
                
                    creator_nodes, validator_nodes = get_node_assignment(dt=round_time(dt=string_to_dt(get_timeData(target, sort=['lastUpdate','created']))), func=target.func, chainId=target.networkChain, opBlock_data=opBlock_data, nodeType='maintainer')
                    prnt('creator_nodes',creator_nodes)
                    prnt('validator_nodes',validator_nodes)
                    prnt('target.validatorNodeId',target.validatorNodeId)
                    required_matches = (len(creator_nodes) * 2/3) if len(creator_nodes) >= 2 else 1
                    vals = []
                    for val in validators:
                        if val.CreatorNode_obj.id in creator_nodes:
                            prnt('val',val.id,'is in creator_nodes')
                            vals.append(val)
                        if val.CreatorNode_obj.id == validator_nodes[0] and val.validatorType == 'scraper' and target.id in val.data:
                            prnt('val',val.id,'is in validator_nodes')
                            validator = val
                    if not vals and validator:
                        vals = list(Validator.objects.filter(id__in=validator.Validator_array))
                        found_ids = {v.id for v in vals}
                        if not all(v_id in found_ids for v_id in validator.Validator_array):
                            fetched_objs = request_items([v_id for v_id in validator.Validator_array if v_id not in [v.id for v in vals]], nodes=[validator.CreatorNode_obj], return_updated_objs=True, return_updated_ids=False, return_missing=False, check_consensus=True, downstream_worker=False, get_missing_blocks=False, override_completed=True, recent_request_time=20)
                            if fetched_objs:
                                for f in fetched_objs:
                                    if f.id in validator.Validator_array and f.id not in [v.id for v in vals]:
                                        vals.append(f)
                    prnt('vals:',vals)
                    prnt('validator',validator)
                    prnt('required_matches',required_matches)
                    prnt('len(vals)',len(vals))
                    if validator:
                        prnt('all(val.id in validator.Validator_array for val in vals)',all(val.id in validator.Validator_array for val in vals))
                        prnt('validatorid',validator.id)
                        if len(vals) >= required_matches:
                            obj_hash = sigData_to_hash(target, exclude_fields=['CreatorNode_obj', 'Validator_obj', 'signed'])
                            matched_vals = []
                            for val in vals:
                                prnt('val',val.id,'target.id',target.id,'obj_hash',obj_hash)
                                try:
                                    'val.data[target.id]',val.data[target.id]
                                except Exception as e:
                                    prnt('err 2',str(e))
                                if val.id in validator.Validator_array:
                                    if target.id in val.data and val.data[target.id] == obj_hash:
                                        prnt('good')
                                        matched_vals.append(val.id)
                            if len(matched_vals) >= required_matches:
                                prnt('is_good')
                                proceed = True
            else:
                prnt('validators not included')
                validators = Validator.objects.exclude(validatorType__in=['Block']).filter(created__gte=string_to_dt(target.created), data__contains={target.id: sigData_to_hash(target)}, is_valid=True).order_by('-created')
                prnt('xxxvalidators',validators)
                if validators and all(validator.func.lower() == 'super' and validator.CreatorNode_obj.User_obj.assess_super_status(dt=string_to_dt(validator.created)) for validator in validators):
                    validator = None
                    validator_nodes = [validators[0].CreatorNode_obj.id]
                    prnt('validator_nodes',validator_nodes)
                    for val in validators:
                        if val.CreatorNode_obj.id == validator_nodes[0]:
                            validator = val
                    if validator:
                        proceed = True
                elif validators:
                    # maybe should check that target was scraped at appropriate time
                    creator_nodes, validator_nodes = get_node_assignment(dt=round_time(dt=string_to_dt(get_timeData(target, sort=['lastUpdate','created']))), chainId=target.networkChain, func=target.func, opBlock_data=opBlock_data, nodeType='maintainer')
                    prnt('creator_nodes, validator_nodes',creator_nodes, validator_nodes)
                    prnt('target.validatorNodeId',target.validatorNodeId)
                    prnt('validators',validators)
                    for val in validators:
                        prnt('val',val.CreatorNode_obj.id)
                        if val.CreatorNode_obj.id == validator_nodes[0] and target.id in val.data:
                            validator = val
                            break
                    prnt('identified validator',validator)
                    required_matches = (len(creator_nodes) * 2/3) if len(creator_nodes) >= 2 else 1
                    
                    if validator:
                        vals = list(Validator.objects.filter(id__in=validator.Validator_array))
                        found_ids = {v.id for v in vals}
                        if not all(v_id in found_ids for v_id in validator.Validator_array):
                            fetched_objs = request_items([v_id for v_id in validator.Validator_array if v_id not in [v.id for v in vals]], nodes=[validator.CreatorNode_obj], return_updated_objs=True, return_updated_ids=False, return_missing=False, check_consensus=True, downstream_worker=False, get_missing_blocks=False, override_completed=True, recent_request_time=20)
                            if fetched_objs:
                                for f in fetched_objs:
                                    if f.id in validator.Validator_array and f.id not in [v.id for v in vals]:
                                        vals.append(f)
                        prnt('vals:',vals)
                        prnt('validator',validator.id,'required_matches',required_matches)
                        prnt('validator.Validator_array',validator.Validator_array)
                        prnt('all(val.id in validator.Validator_array for val in vals)',all(val.id in validator.Validator_array for val in vals))
                        prnt('len(vals)',len(vals))
                        if len(vals) >= required_matches:
                            obj_hash = sigData_to_hash(target, exclude_fields=['CreatorNode_obj', 'Validator_obj', 'signed'])
                            matched_vals = []
                            for val in vals:
                                prnt('val',val.id,'target.id',target.id,'obj_hash',obj_hash)
                                try:
                                    prnt('val.data[target.id]',val.data[target.id])
                                except Exception as e:
                                    prnt('err 2',str(e))
                                if val.CreatorNode_obj.id in creator_nodes:
                                    if target.id in val.data and val.data[target.id] == obj_hash:
                                        prnt('good')
                                        matched_vals.append(val.id)
                            if len(matched_vals) >= required_matches:
                                prnt('is_good')
                                proceed = True
        err += '1'
        prnt('validator in use:',validator,'proceed',proceed)
        if proceed and target and validator and validator.is_valid and validator.signed and target.signed:
            if has_field(target, 'created'):
                if not validator.dt_appropriate(target):
                    err += '1a'
                    prnt('validator created outside of window')
                    if obj and has_field(obj, 'notes'):
                        obj.notes[dt_to_string(now_utc())] = f'validator created outside of window:{err}.'
                        obj.save()
                    prnt('failed to validaed post1',err,target)
                    return False
            err += '2'
            if not verify_validator or verify_obj_to_data(validator, validator):
                err += 'a'
                if target.id in validator.data:
                    err += '3'
                    hash = validator.data[target.id]
                    if hash == sigData_to_hash(target):
                        err += '5'
                        if target.validatorNodeId in validator_nodes:
                            err += '6'
                            if obj and get_objType(obj) == 'Post':
                                err += '7'
                                if save_obj:
                                    err += '7a'
                                    obj, updated_fields = update_post(obj=target, p=obj, save_p=False)
                                    obj.validated = True
                                    obj.save()
                                    # super(Update, self).save()
                                if has_field(obj, 'Validator_obj') and obj.Validator_obj != validator and not obj.Block_obj:
                                    obj.Validator_obj = validator
                                if update_pointer:
                                    err += '7b'
                                    super(get_model(get_objType(target)), target).save()
                                    if has_field(target, 'networkChain'):
                                        err += '7c'
                                        network_chain, item, commit_chain = find_or_create_chain_from_object(target)
                                        network_chain.add_item_to_queue(target)
                            elif obj and get_objType(obj) in ['Update','Spren']:
                                err += '8'
                                if has_field(obj, 'Validator_obj') and obj.Validator_obj != validator and not obj.Block_obj:
                                    obj.Validator_obj = validator
                                if save_obj:
                                    obj.validated = True
                                    super(get_model(target._meta.object_name), obj).save()
                                    network_chain, item, commit_chain = find_or_create_chain_from_object(obj.Pointer_obj)
                                    if network_chain:
                                        network_chain.add_item_to_queue(obj)
                                    # else:
                                    #     # from utils.models import logEvent
                                    #     # from utils.locked import convert_to_dict
                                    #     logEvent('no blockchain', code='9763', func='update.validate()', extra={'self.id':obj.id,'dict':str(convert_to_dict(obj.Pointer_obj))[:500]})
                                target = obj
                            elif obj and obj._meta.object_name == 'Notification':
                                err += '9'
                                prnt('validated notification')
                                from accounts.models import UserNotification, User, Notification
                                if has_field(obj, 'Validator_obj') and obj.Validator_obj != validator and not obj.Block_obj:
                                    obj.Validator_obj = validator
                                if save_obj:
                                    obj.validated = True
                                    super(Notification, obj).save()
                                
                                try:
                                    err += '10'
                                    for target in obj.targetUsers:
                                        target_users = obj.targetUsers[target]
                                        prnt('target_users',target_users)
                                        if target == 'all':
                                            for u in User.objects.all():
                                                if not UserNotification.objects.filter(User_obj=u, Notification_obj=obj).exists():
                                                    n = UserNotification(User_obj=u, Notification_obj=obj)
                                                    n.save()
                                        elif target == 'by_id':
                                            for u in User.objects.filter(id__in=obj.targetUsers[target]):
                                                prnt(u)
                                                if not UserNotification.objects.filter(User_obj=u, Notification_obj=obj).exists():
                                                    n = UserNotification(User_obj=u, Notification_obj=obj)
                                                    n.save()
                                        elif target == 'all_in_country':
                                            pass
                                            # for u in User.objects.filter(Country_obj__id=target):
                                            #     n = UserNotification.objects.filter(User_obj=u, Notification_obj=self).first()
                                            #     if not n:
                                            #         n = UserNotification(User_obj=u, Notification_obj=self)
                                            #         n.save()
                                        elif target == 'all_in_provState':
                                            pass
                                        elif target == 'follow_bill':
                                            pass
                                        elif target == 'follow_person':
                                            pass
                                    if add_to_queue:
                                        network_chain, item, commit_chain = find_or_create_chain_from_object(obj.Region_obj)
                                        network_chain.add_item_to_queue(obj)
                                except Exception as e:
                                    prnt('fail40636',str(e))
                                    err += str(e)
                                target = obj
                                
                            else:
                                err += '11'
                                prnt('validator',validator)
                                if has_field(target, 'Validator_obj') and (not target.Validator_obj or target.Validator_obj != validator) and not target.Block_obj:
                                    err += 'a'
                                    target.Validator_obj = validator
                                if update_pointer:
                                    err += '12'
                                    super(get_model(target._meta.object_name), target).save()
                                    prnt('c2d',convert_to_dict(target))
                                    if has_field(target, 'networkChain'):
                                        network_chain, item, commit_chain = find_or_create_chain_from_object(target)
                                        network_chain.add_item_to_queue(target)

                            prnt('target',target)
                            if target and has_method(target, 'boot'):
                                if not Post.all_objects.filter(pointerId=target.id).exists():
                                    target.boot()
                            if target and has_method(target, 'sync_with_post'):
                                synced = target.sync_with_post()
                                if synced == False:
                                    prntDebug(f'post not validated - id:{obj.id if obj else "0"}, pointerId:{target.id}, err:{err}, synced:{synced}, opBlock_data:{opBlock_data}')
                                    return False
                            prntDebug(f'post validated - id:{obj.id if obj else "0"}, pointerId:{target.id}, err:{err}, save_self:{save_obj}, opBlock_data:{opBlock_data}')
                            return target
                        else:
                            prnt('valId incorrect',target)
                    else:
                        prnt('hash no match',target)
                        prnt('c2d:',convert_to_dict(target))
                        if obj and has_field(obj, 'notes'):
                            obj.notes[dt_to_string(now_utc())] = f'hash no match err:{err}. {target}'
                else:
                    prnt('point.id not in validator')
                    if obj and has_field(obj, 'notes'):
                        obj.notes[dt_to_string(now_utc())] = f'point.id not in validator err:{err}. {validator.id}'
            else:
                prnt('val not verified')
                if obj and has_field(obj, 'notes'):
                    obj.notes[dt_to_string(now_utc())] = f'val not verified err:{err}. {validator.id}'
        else:
            prnt('validator not valid')
            if obj and has_field(obj, 'notes'):
                obj.notes[dt_to_string(now_utc())] = f'no val or val not valid err:{err}.'
        prnt('failed to validaed post2',err,target)
        if obj:
            obj.save()

    if obj and has_field(obj, 'validated') and obj.validated or pointer and pointer.Validator_obj:
        prnt('already validated')
        return obj
    prnt('rturn False', err)
    return False

def get_broadcast_list(seed, dt=None, region_id=None, relevant_nodes={}, seed_nodes=[], important_nodes=None, excluded_nodes=None, included_nodes=[], peer_count=None, loop=False, all_nodes=False, include_relays=False, opBlock_data={}):
    from django.db import models
    from utils.models import is_id, get_dynamic_model, round_time, now_utc, dt_to_string,prnt
    from network.models import Node, universalChains, _OperationsChain_genesisId
    if not important_nodes:
        important_nodes = []
    if not excluded_nodes:
        excluded_nodes = []
    prnt('-get_broadcast_list',seed,'dt',dt,'region_id',region_id,'all_nodes',all_nodes,'loop',loop)
    seed_nodes = seed_nodes.copy()
    important_nodes = important_nodes.copy()
    extra_nodes = {}

    def get_deterministic_broadcast_order(func_name, dt, node_ids, seed_nodes, important_nodes, excluded_nodes=[]):
        prnt('get_deterministic_broadcast_order')
        prnt('func_name',func_name,'dt',dt,'node_ids',node_ids,'seed_nodes',seed_nodes,'important_nodes',important_nodes,'excluded_nodes',excluded_nodes)
        import random
        if isinstance(dt, datetime.datetime):
            dt_str = dt_to_string(dt)
        elif isinstance(dt, str):
            dt_str = dt
        else:
            raise ValueError("dt must be a datetime or ISO string")

        seed_input = f"{func_name}_{dt_str}"
        prnt('seed_input',seed_input)
        seed_hash = hashlib.sha256(seed_input.encode('utf-8')).hexdigest()
        seed_int = int(seed_hash, 16)
        rng = random.Random(seed_int)

        # important_nodes = [i for i in important_nodes]
        excluded = set(seed_nodes + important_nodes + excluded_nodes)
        remaining_nodes = [nid for nid in node_ids if nid not in excluded]

        rng.shuffle(important_nodes)
        rng.shuffle(remaining_nodes)
        prnt('seed_nodes',seed_nodes,'important_nodes',important_nodes,'remaining_nodes',remaining_nodes)
        return seed_nodes + important_nodes + remaining_nodes

    def get_broadcast_map(func_name, dt, nodes, seed_nodes, important_nodes, peer_count=2, excluded_nodes=[], included_nodes=[], extra_nodes={}, loop=False):
        prnt('get_broadcast_map',nodes,'important_nodes',important_nodes,'loop',loop,'extra_nodes',extra_nodes)
        if isinstance(nodes, list):
            nodes = {i:i for i in nodes}
        node_ids = list(nodes.keys()) + included_nodes
        ordered_ids = get_deterministic_broadcast_order(func_name, dt, node_ids, seed_nodes, important_nodes, excluded_nodes=excluded_nodes)
        broadcast_map = {}
        recipients_set = set()
        prnt('ordered_ids',ordered_ids)

        if loop:
            total = len(ordered_ids)
            for i, node_id in enumerate(ordered_ids):
                recipients = []
                count = 0
                j = 1
                # for j in range(1, peer_count+1): 
                while count < peer_count and j < total:
                    if loop:
                        recipient = ordered_ids[(i + j) % total]
                    else:
                        if i + j < total:
                            recipient = ordered_ids[i + j]
                        else:
                            break
                    if recipient in nodes and nodes[recipient] not in excluded_nodes:
                        # prnt('nodes[recipient]',nodes[recipient])
                        # if 'addr' in nodes[recipient]:
                        #     recipients.append(nodes[recipient]['addr'])
                        # else:
                        recipients.append(nodes[recipient])
                        count += 1
                    j += 1
                if node_id not in broadcast_map:
                    broadcast_map[node_id] = recipients
                else:
                    broadcast_map[node_id] += recipients

        else:
            # total = len(ordered_ids) + len(extra_nodes)
            if extra_nodes:
                extra_node_ids = list(extra_nodes.keys())
                ordered_extra_ids = get_deterministic_broadcast_order(func_name, dt, extra_node_ids, [], [], excluded_nodes=excluded_nodes)
                ordered_ids += [i for i in ordered_extra_ids if i not in ordered_ids]
                nodes = {**nodes, **extra_nodes}
            total = len(ordered_ids)
            for i, node_id in enumerate(ordered_ids):
                # prnt('i',i,'node_id',node_id)
                recipients = []
                count = 0
                j = i + 1
                while count < peer_count and j < total:
                    # prnt('j',j)
                    if j < total:
                        candidate = ordered_ids[j]
                        if candidate not in recipients_set and candidate not in excluded_nodes:
                            if candidate in nodes:
                                # prnt('nodes[candidate]x',nodes[candidate])
                                # if 'addr' in nodes[candidate]:
                                #     recipients.append(nodes[candidate]['addr'])
                                # else:
                                recipients.append(nodes[candidate])
                            else:
                                n = Node.objects.filter(id=candidate).first()
                                if n:
                                    addr = n.return_address()
                                else:
                                    addr = ''
                                recipients.append(addr)

                            recipients_set.add(candidate)
                            # prnt('recipients',recipients)
                            count += 1
                        j += 1
                if node_id not in broadcast_map:
                    broadcast_map[node_id] = recipients
                else:
                    broadcast_map[node_id] += recipients
                # prnt('broadcast_map111',broadcast_map)
            last_node = next(reversed(broadcast_map))
            # prnt('last_node',last_node)
            # prnt(type(seed_nodes),seed_nodes)
            for s in seed_nodes:
                # prnt('s',s)
                if s in nodes:
                    # prnt('x1')
                    # if 'addr' in nodes[s]:
                    #     addr = nodes[s]['addr']
                    # else:
                    addr = nodes[s]
                else:
                    # prnt('x2')
                    n = Node.objects.filter(id=s).first()
                    if n:
                        addr = n.return_address()
                    else:
                        addr = ''
                # prnt('addr',addr)
                # prnt("broadcast_map[last_node]1",broadcast_map[last_node])
                broadcast_map[last_node].append(addr)
                # prnt("broadcast_map[last_node]2",broadcast_map[last_node])

        # prnt('done broadcast_map:',broadcast_map)
        return broadcast_map

    if is_id(seed):
        obj = get_dynamic_model(seed, id=seed)
        if obj:
            seed = obj
    if isinstance(seed, models.Model):
        # include_relays = False
        if seed and seed._meta.object_name == 'Block' or seed and seed._meta.object_name == 'Transaction':

            if seed._meta.object_name == 'Block' and not seed.Transaction_obj or seed._meta.object_name == 'Block' and 'BlockReward' in seed.Transaction_obj.regarding and seed.Transaction_obj.regarding['BlockReward'] == seed.id:
                if seed._meta.object_name == 'Block' and seed.networkChain in universalChains:
                    include_relays = True
                if not relevant_nodes:
                    if not opBlock_data:
                        opBlock_data = get_relevant_nodes_from_block(dt=seed.DateTime, obj=seed, genesisId=seed.Blockchain_obj.genesisId, include_relays=include_relays)
                    relevant_nodes = opBlock_data['relevant_nodes']
                if not seed_nodes and not important_nodes:
                    seed_nodes, important_nodes = get_node_assignment(chainId=region_id, obj=seed, dt=dt)
                if all_nodes:
                    if region_id == _OperationsChain_genesisId:
                        missing_nodes = Node.objects.exclude(id__in=[i for i in relevant_nodes]).exclude(activated_dt=None)
                    else:
                        missing_nodes = Node.objects.exclude(id__in=[i for i in relevant_nodes]).filter(chain_array__contains=[seed.networkChain], expelled_dt=None).exclude(activated_dt=None)
                    extra_nodes = {i.id:i.return_address() for i in missing_nodes}
            else:
                if seed._meta.object_name == 'Block' and seed.Transaction_obj:
                    seed = seed.Transaction_obj
                dt = round_time(dt=seed.created, dir='down', amount='evenhour')
                if not relevant_nodes:
                    if not opBlock_data:
                        opBlock_data = get_relevant_nodes_from_block(dt=dt, obj=seed, include_relays=include_relays)
                    relevant_nodes = opBlock_data['relevant_nodes']
                if not seed_nodes and not important_nodes:
                    seed_nodes, important_nodes = get_node_assignment(chainId=region_id, obj=seed, dt=dt)
        elif seed._meta.object_name == 'Node':
            if not dt:
                dt = round_time(dt=seed.lastUpdate, dir='down', amount='10mins')
            if not relevant_nodes:
                if not opBlock_data:
                    opBlock_data = get_relevant_nodes_from_block(genesisId=region_id, obj=seed, dt=dt, include_relays=include_relays)
                relevant_nodes = opBlock_data['relevant_nodes']
            seed_nodes.append(seed.id)
        else:
            if seed._meta.object_name == 'DataPacket':
                prnt('ssed is datapacket', seed.Node_obj)
                if not dt:
                    dt = seed.created
                    dt = round_time(dt=dt, dir='down', amount='10mins')
                if seed.chainName == 'All':
                    include_relays = True
            elif seed._meta.object_name == 'Validator':
                dt = round_time(dt=seed.created, dir='down', amount='10mins')
            elif seed._meta.object_name == 'User' and not dt:
                dt = round_time(dt=seed.lastUpdate, dir='down', amount='10mins')
            elif not dt:
                dt = round_time(dt=now_utc(), dir='down', amount='10mins')
            if not relevant_nodes:
                if not opBlock_data:
                    opBlock_data = get_relevant_nodes_from_block(genesisId=region_id, obj=seed, dt=dt, include_relays=include_relays)
                relevant_nodes = opBlock_data['relevant_nodes']
        seed_text = seed.id
    elif isinstance(seed, str) and region_id and dt:
        if not opBlock_data:
            opBlock_data = get_relevant_nodes_from_block(genesisId=region_id, dt=dt, include_relays=include_relays)
            prnt('opBlock_data::',opBlock_data)
        if not seed_nodes and not important_nodes:
            seed_nodes, important_nodes = get_node_assignment(chainId=region_id, func=seed, dt=dt, opBlock_data=opBlock_data)
        if not relevant_nodes:
            relevant_nodes = opBlock_data['relevant_nodes']
        if all_nodes:
            from utils.models import get_pointer_type
            if get_pointer_type(region_id) == 'Blockchain':
                from network.models import Blockchain
                chain = Blockchain.objects.filter(id=region_id).first()
                region_id = chain.id
            if region_id == _OperationsChain_genesisId:
                missing_nodes = Node.objects.exclude(id__in=[i for i in relevant_nodes]).exclude(activated_dt=None)
            else:
                missing_nodes = Node.objects.filter(chain_array__contains=[region_id]).exclude(id__in=[i for i in relevant_nodes]).exclude(activated_dt=None)
            extra_nodes = {i.id:i.return_address() for i in missing_nodes}
        seed_text = seed
    else:
        prnt('seed',seed,'region_id',region_id,'dt',dt)
        raise ValueError("get_broadcast_list received wrong input")

    if not dt:
        dt = now_utc()
    if not peer_count:
        if not opBlock_data:
            opBlock_data = get_relevant_nodes_from_block(genesisId=region_id, dt=dt, include_relays=include_relays)
        peer_count = opBlock_data['opData']['number_of_peers']
    broadcast_map = {}
    for nid, recipients in get_broadcast_map(seed_text, dt, relevant_nodes, seed_nodes, important_nodes, peer_count=peer_count, excluded_nodes=excluded_nodes, included_nodes=included_nodes, extra_nodes=extra_nodes, loop=loop).items():
        prnt(f"{nid} → {recipients}")
        broadcast_map[nid] = recipients
    prnt('returned broadcast_map',broadcast_map)
    return broadcast_map

def get_relevant_nodes_from_block(dt=None, genesisId=None, chains=None, blockchain=None, obj=None, for_user=False, include_relays=False, exclude_list=None, opBlock=None, strings_only=True, sublist='', first_block_override=False, node_ids_only=False):
    from utils.models import now_utc, get_timeData, testing, round_time, prnt
    prnt('--get_relevant_nodes_from_block - strings_only:',strings_only,'genesisId',genesisId,'blockchain',blockchain,'chains',chains,'obj',obj,'dt',dt,'include_relays',include_relays,'exclude_list',exclude_list,'first_block_override',first_block_override)
    if not exclude_list:
        exclude_list = []
    if not dt and obj:
        # only use obj if dt may not be available, always include genesisId or network/chains else will get all active nodes
        dt = get_timeData(obj, sort='updated')
    elif not dt:
        dt = now_utc()
    record = None
    node_ids = []

    from network.models import Block, Node, NodeRecord, Blockchain, Sonet, _EarthChain_genesisId, universalChains, _OperationsChain_genesisId, mandatoryChains
    from utils.models import get_pointer_type, get_chain_type, is_id
    from django.db import models
    if not opBlock and not testing():
        opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=dt, validated=True).only('opData').order_by('-index', 'created').first()

    if blockchain and isinstance(blockchain, models.Model) and blockchain.genesisType in universalChains:
        include_relays = True
    elif blockchain and is_id(blockchain) and blockchain in universalChains:
        include_relays = True
    elif genesisId and is_id(genesisId) and genesisId in universalChains:
        include_relays = True
    def get_relay_list(record, exclude_list):
        if not include_relays and 'relay' in record.data:
            exclude_list += [n for n in record.data['relay'] if n not in exclude_list]
    if opBlock:
        if for_user and False:
            # not currently used - to be completed later

            node_ids = [n for n in opBlock.data[_EarthChain_genesisId]['server'] if n not in exclude_list]
            # prnt('node_ids',node_ids)
            # if node_ids_only:
            #     return node_ids
            # sonet = Sonet.objects.first().values('Domain').first()
            # if sonet and sonet['Domain']:
            #     relevant_nodes = {iden:{'addr':f'{iden}.{sonet['Domain']}','pos':opBlock.data['Active'][iden]['pos']} for iden in opBlock.data['Active'] if iden in node_ids}
            # # if 'node_data' in opBlock.notes:
            # #     relevant_nodes = {iden:{'pos':opBlock.data['positions'][iden],'addr':opBlock.notes['node_data'][iden]['addr']} for iden in opBlock.data['positions']}
            # else:
            #     relevant_nodes = {node.id:{'addr':node.return_address(),'pos':node.pos} for node in Node.objects.filter(id__in=node_ids)}
            # # if include_peers:
            # #     from blockchain.models import _user_peer_count
            # #     return relevant_nodes, _user_peer_count
            # # return relevant_nodes
            # return {'relevant_nodes':dict(relevant_nodes.items()),'opData':opBlock.opData}
        elif genesisId and NodeRecord.objects.filter(pointerId=genesisId, DateTime__lte=dt, is_valid=True).exists():
            record = NodeRecord.objects.filter(pointerId=genesisId, DateTime__lte=dt, is_valid=True).first()
            prnt('record',record)
            prnt('record.data',record.data)
            prnt('exclude_list',exclude_list)
            node_ids = [n for n in record.data['active'] if n not in exclude_list]

        elif genesisId or blockchain:
            prnt('op2')
            if not blockchain and get_pointer_type(genesisId) == 'Blockchain':
                blockchain = Blockchain.objects.filter(id=genesisId).only('genesisType','genesisId').first()
            elif is_id(blockchain) and get_pointer_type(blockchain) == 'Blockchain':
                blockchain = Blockchain.objects.filter(id=blockchain).only('genesisType','genesisId').first()
            elif is_id(blockchain):
                blockchain = Blockchain.objects.filter(genesisId=blockchain).only('genesisType','genesisId').first()
            elif is_id(genesisId) and get_pointer_type(genesisId) != 'Blockchain':
                blockchain = None
            if not sublist:
                sublist = 'active'
            from django.db import models
            if isinstance(blockchain, models.Model):
                genesisId = blockchain.genesisId
            prnt('genesisId',genesisId,'sublist',sublist)
            record = NodeRecord.objects.filter(pointerId=genesisId, DateTime__lte=dt, is_valid=True).first()
            prnt('record',record)
            if record:
                prnt('record.data',record.data)
                node_ids = [n for n in record.data[sublist] if n not in exclude_list]
        elif chains:
            if not sublist:
                sublist = 'active'
            chains_data = Blockchain.objects.filter(id__in=chains).values('genesisId')
            for record in NodeRecord.objects.filter(pointerId__in=[i['genesisId'] for i in chains_data], DateTime__lte=dt, is_valid=True):
                for node_iden in record.data[sublist]:
                    if node_iden not in node_ids and node_iden not in exclude_list:
                        node_ids.append(node_iden)
        elif sublist and sublist in ['relay']:
            record = NodeRecord.objects.filter(pointerId=_OperationsChain_genesisId, DateTime__lte=dt, is_valid=True).first()
            if record:
                node_ids = [n for n in record.data[sublist] if n not in exclude_list]
        elif sublist:
            record = NodeRecord.objects.filter(pointerId=_OperationsChain_genesisId, DateTime__lte=dt, is_valid=True).first()
            if record:
                node_ids = [n for n in record.data['abilities'][sublist] if n not in exclude_list]

        else:
            # prnt('else',dt)
            record = NodeRecord.objects.filter(pointerId=_OperationsChain_genesisId, DateTime__lte=dt, is_valid=True).first()
            if record:
                node_ids = [n for n in record.data['active'] if n not in exclude_list]

        if record:
            if node_ids_only:
                return node_ids
            sonet = Sonet.objects.values('Domain').first()
            if strings_only:
                relevant_nodes = {n['id']:{'address':n['address'],'onion':n['onion']} for n in Node.objects.filter(id__in=node_ids).values('address','onion','id')}
            else:
                relevant_nodes = {n.id: n for n in Node.objects.filter(id__in=node_ids).defer('chain_array','plugin_array','Block_obj','User_obj','abilities','region_data')}
            relevant_nodes = {i:relevant_nodes[i] for i in node_ids}
            prnt('nrec',record,'1 node_ids',node_ids, 'relevant_nodes',relevant_nodes)
            return {'relevant_nodes':dict(relevant_nodes.items()),'opData': opBlock.opData if opBlock else {}}
    if first_block_override:
        prnt('opBlock not found',obj, convert_to_dict(obj))
        from django.db import models
        from network.models import Node, get_default_opData
        from utils.models import get_chain_id
        if obj and isinstance(obj, models.Model) and obj._meta.object_name == 'Block' and obj.networkChain == _OperationsChain_genesisId:
            first_node = Node.objects.order_by('created').first()
            prnt('first_node',first_node)
            node_ids = [first_node.id]
            if node_ids_only:
                return node_ids
            sonet = Sonet.objects.values('Domain').first()
            if strings_only:
                relevant_nodes = {first_node.id:{'address':first_node.address,'onion':first_node.onion}}
            else:
                relevant_nodes = {first_node.id: first_node}
            prnt('relevant_nodes',relevant_nodes)
            return {'relevant_nodes':dict(relevant_nodes.items()),'opData':get_default_opData()}
    if node_ids_only:
        return []
    from network.models import get_default_opData
    return {'relevant_nodes':{}, 'opData':get_default_opData()}

def check_block_contents(block, retrieve_missing=True, update_items=False, log_missing=False, downstream_worker=True, return_missing=False, input_data=None, uncommitted_required=False):
    from utils.models import chunk_dict, get_timeData, has_field, has_method, get_dynamic_model, sigData_to_hash, exists_in_worker, get_data, now_utc, prnt, string_to_dt, is_id, declare_var, request_items, logMissing, logError, get_plugin
    prnt('-check_block_contents', block, block.index, now_utc(), retrieve_missing, downstream_worker)
    from network.models import Validator, max_commit_window
    input_data = declare_var(input_data, {})
    obj_idens = []
    requested_idens = []
    requested_validators = []
    if 'content_dt' in block.notes:
        content_dt = string_to_dt(block.notes['content_dt'])
    elif 'created_dt' in block.notes:
        content_dt = string_to_dt(block.notes['created_dt'])
    else:
        content_dt = string_to_dt(block.created)
    self_dt = string_to_dt(block.DateTime)
    try:
        from pathlib import Path
        import importlib.util
        proceed = True
        if is_id(block.Blockchain_obj.genesisId):
            genesis_obj = get_dynamic_model(block.Blockchain_obj.genesisId, id=block.Blockchain_obj.genesisId)
            if not has_field(genesis_obj, 'Block_obj'):
                prnt('stoppage 1 for gen obj',genesis_obj)
                proceed = False
            elif genesis_obj.Block_obj.Blockchain_obj == block.Blockchain_obj and not genesis_obj._meta.object_name in ['Sonet']:
                # Sonet is only genesis obj that starts a new tree
                prnt('stoppage 2 for gen obj',genesis_obj, genesis_obj.Block_obj)
                proceed = False
            elif not genesis_obj._meta.object_name in ['Sonet'] and (not genesis_obj.Block_obj or not genesis_obj.Block_obj.validated):
                prnt('stoppage 3 for gen obj',genesis_obj, genesis_obj.Block_obj)
                proceed = False
        if not proceed:
            if genesis_obj:
                from utils.models import find_or_create_chain_from_object
                network_chain, obj, commit_chain = find_or_create_chain_from_object(genesis_obj)
                if network_chain:
                    network_chain.add_item_to_queue(genesis_obj)
            if return_missing:
                return [], []
            return []
        plugin_name = get_plugin(genesis_obj, True)
        plugin_file = Path(f"{plugin_name}/utils.py")

        spec = importlib.util.spec_from_file_location("utils", plugin_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for_commitment = getattr(module, "for_commitment", None)
    except:
        for_commitment = None

    if input_data:
        prnt('input_data',input_data)
        # block_data = {key:value for key, value in block.data.items() if key in input_data}
        block_data = input_data
    else:
        block_data = {**block.data, **block.extraData}
    total_found = 0
    ineligible = []
    for chunk in chunk_dict(block_data, 300):
        storedModels, not_found, not_valid, delLogs = get_data(chunk, return_model=True, include_related=False, include_deletions=True)
        total_found += len(not_found)
        total_found += len(not_valid)
        total_found += len(storedModels)
        for x in storedModels:
            prnt('x',x)
            if x._meta.object_name == 'Validator':
                eligible = True
            else:
                try:
                    eligible = for_commitment(i, genesis_obj, block)
                except:
                    eligible = True
            if eligible and uncommitted_required and has_field(x, 'Block_obj') and x.Block_obj and x.id in block.data and x.Block_obj != block and x.id != block.Blockchain_obj.genesisId and check_commit_data(x, x.Block_obj.data[x.id]):
                eligible = False
            if not eligible:
                prnt('x ineligible (has Block_obj):', x.Block_obj)
                prnt('x.id',x.id)
                prnt('x.Block_obj.Blockchain_obj.genesisId',x.Block_obj.Blockchain_obj.genesisId)
                ineligible.append(x.id)
            elif eligible:
                if not has_field(x, 'Validator_obj') or x.Validator_obj and x.Validator_obj.is_valid and x.id in x.Validator_obj.data and x.Validator_obj.data[x.id] == sigData_to_hash(x) and x.Validator_obj.dt_appropriate(x):
                    # prnt('a')
                    if x.id in block_data:
                        i_dt = get_timeData(x)
                        if not has_method(x, 'block_conditions') or x.block_conditions():
                            prnt('ac')
                            if check_commit_data(x, block_data[x.id]): 
                                obj_idens.append(x.id)
                            else:
                                requested_idens.append(x.id)
                elif has_field(x, 'Validator_obj') and not x.Validator_obj:
                    try:
                        if validate_obj(obj=None, pointer=x, opBlock_data={}):
                            if x.id in block_data:
                                # prnt('az')
                                i_dt = get_timeData(x)
                                if not has_method(x, 'block_conditions') or x.block_conditions():
                                    if check_commit_data(x, block_data[x.id]):
                                        obj_idens.append(x.id)
                                    
                        else:
                            requested_idens.append(x.id)
                    except Exception as e:
                        prnt('***error*** validate_obj1', str(e))
                        requested_idens.append(x.id)
                else:
                    requested_validators.append(x.id)

        storedModels.clear()
        if not_valid:
            requested_idens = requested_idens + [i.id for i in not_valid]
        if not_found:
            requested_idens = requested_idens + not_found
        not_found.clear()
        not_valid.clear()
    prnt('total_found',total_found,'requested_idens',requested_idens,'obj_idens',len(obj_idens),'requested_validators',requested_validators)
    if requested_validators:
        vals = Validator.objects.filter(data__overlap=requested_validators, is_valid=True).order_by('-created')
        if vals:
            for i in requested_validators:
                creator_nodes, validator_nodes = get_node_assignment(dt=i.created, chainId=i.networkChain, func=i.func)

                for val in vals:
                    # prnt('val',val)
                    if val.CreatorNode_obj.id in validator_nodes and i in val.data:
                        # prnt('y')
                        obj = get_dynamic_model(i, id=i)
                        # prnt('obj',obj)
                        try:
                            if obj and validate_obj(obj=None, pointer=obj, validator=val, opBlock_data={}):
                                if obj.id in block.data and get_timeData(obj) < self_dt and get_timeData(obj) < self_dt and check_commit_data(obj, block.data[obj.id]):
                                # if obj.id in block.data and get_timeData(obj) >= self_dt - datetime.timedelta(days=max_commit_window) and get_timeData(obj) < self_dt and check_commit_data(obj, block.data[obj.id]):
                                    if not has_method(obj, 'block_conditions') or obj.block_conditions():
                                        obj_idens.append(obj.id)
                                        requested_validators.remove(obj.id)
                                elif obj.id in block.extraData and get_timeData(obj) < self_dt and get_timeData(obj) < self_dt and check_commit_data(obj, block.extraData[obj.id]):
                                    if not has_method(obj, 'block_conditions') or obj.block_conditions():
                                        obj_idens.append(obj.id)
                                        requested_validators.remove(obj.id)
                        except Exception as e:
                            prnt('***error*** validate_obj2', str(e))
                            requested_validators.append(obj.id)
    prnt('next stage check block contents')
    if retrieve_missing or not block.validated:
        from utils.models import get_operatorData
        chain_supported = False
        try:
            operatorData = get_operatorData()
            if 'syncingDB' in operatorData and operatorData['syncingDB'] in [True, 'bypass']:
                get_missing_blocks = False
            else:
                get_missing_blocks = True
            node_data = operatorData['myNodes'][operatorData['local_nodeId']]
            operatorData.clear()
            if not 'do_not_sync_block_content' in node_data['meta'] and 'chainData' in node_data['meta'] and 'supported' in node_data['meta']['chainData'] and node_data['meta']['chainData']['supported'] != '':
                if block.Blockchain_obj.genesisId in node_data['meta']['chainData']['supported'] or block.Blockchain_obj.genesisType in node_data['meta']['chainData']['supported']:
                    chain_supported = True
        except Exception as e:
            prnt('err 5607', str(e))
        if not chain_supported:
            prnt('retrieve_missing skip - !chain_supported')
            block.notes['unsupported_chain'] = True
            block.save(update_fields=['notes'])
        else:
            prnt('retrieve_missing p2',block)
            if 'unsupported_chain' in block.notes:
                prnt('retrieve_missing p3')
                del block.notes['unsupported_chain']
                block.save(update_fields=['notes'])

    if retrieve_missing:
        fetch_idens = [i for i in block_data if i not in obj_idens and is_id(i) and i not in ineligible]
        if fetch_idens:
            if chain_supported:
                request_nodes = [block.CreatorNode_obj.id]
                for iden, data in block.validations.items():
                    # prnt(iden, data)
                    request_nodes.append(data['CreatorNode_obj'])
                prnt('is valid path 11 request_nodes',request_nodes, block,'downstream_worker',downstream_worker)
                # logEvent(f'requesting:{fetch_idens}', func='check_block_contents')
                if downstream_worker:
                    import django_rq
                    queue = django_rq.get_queue('low')
                    if not exists_in_worker('request_items', queue=queue, requested_items=fetch_idens, nodes=request_nodes):
                        # attempts += 1
                        queue.enqueue(request_items, fetch_idens, nodes=request_nodes, get_missing_blocks=get_missing_blocks, job_timeout=600, result_ttl=7200)
                        if return_missing:
                            return [], []
                        return []
                else:
                    prnt('is valid path 444')
                    fetch_again = []
                    retreived_objs = request_items(fetch_idens, return_updated_objs=True, nodes=request_nodes, get_missing_blocks=get_missing_blocks)
                    try:
                        r_os = len(retreived_objs)
                    except:
                        r_os = str(retreived_objs)[:150]
                    prnt('retreived_objs 11p',r_os)
                    def check_conditions(x, block, obj_idens):
                        if x.id in block.data or x.id in block.extraData:
                            if not has_method(x, 'block_conditions') or x.block_conditions():
                                if x.id in block.data and check_commit_data(x, block.data[x.id]) or x.id in block.extraData and check_commit_data(x, block.extraData[x.id]):
                                    obj_idens.append(x.id)
                                    # if block.validated and has_field(x, 'Block_obj') and not x.Block_obj:
                                    #     if not has_field(x, 'commitChain') or x.commitChain == block.Blockchain_obj.genesisType:
                                    #         x.Block_obj = block
                                    #         x.save()
                        return obj_idens
                    for chunk in chunk_dict(fetch_idens, 300):
                        storedModels, not_found, not_valid, delLogs = get_data(chunk, return_model=True, include_related=False, include_deletions=True)
                        for x in storedModels:
                            if not has_field(x, 'Validator_obj') or x.Validator_obj and x.Validator_obj.is_valid and x.id in x.Validator_obj.data and x.Validator_obj.data[x.id] == sigData_to_hash(x):
                                obj_idens = check_conditions(x, block, obj_idens)
                            elif has_field(x, 'Validator_obj') and not x.Validator_obj:
                                try:
                                    if not validate_obj(obj=None, pointer=x, opBlock_data={}):
                                        fetch_again.append(x.id)
                                    else:
                                        obj_idens = check_conditions(x, block, obj_idens)
                                except Exception as e:
                                    prnt('***error*** validate_obj3', str(e))
                                    # fetch_again.append(x.id)
                        # retreived_objs.clear()
                    if fetch_again:
                        retreived_objs = request_items(fetch_again, return_updated_objs=True, nodes=request_nodes, get_missing_blocks=get_missing_blocks)
                        if retreived_objs:
                            prnt('retreived_objs 22p',len(retreived_objs))
                        for chunk in chunk_dict(fetch_again, 300):
                            storedModels, not_found, not_valid, delLogs = get_data(chunk, return_model=True, include_related=False, include_deletions=True)
                            for x in storedModels:
                                if not has_field(x, 'Validator_obj') or x.Validator_obj and x.Validator_obj.is_valid and x.id in x.Validator_obj.data and x.Validator_obj.data[x.id] == sigData_to_hash(x):
                                    obj_idens = check_conditions(x, block, obj_idens)
                                elif has_field(x, 'Validator_obj') and not x.Validator_obj:
                                    try:
                                        if not validate_obj(obj=None, pointer=x, opBlock_data={}):
                                            pass
                                        else:
                                            obj_idens = check_conditions(x, block, obj_idens)
                                    except Exception as e:
                                        prnt('***error*** validate_obj4', str(e))
                                        pass
        if chain_supported and 'unsupported_chain' in block.notes:
            prnt('retrieve_missing p4')
            del block.notes['unsupported_chain']
            block.save(update_fields=['notes'])
    prnt('self.data_len',len(block.data),'self.extradata_len',len(block.extraData),'obj_idens_len',len(obj_idens),'self.data',str(block.data)[:500],'obj_idens',str(obj_idens)[:500])
    # if len(self.data) != len(obj_idens):
    problem_idens = []
    for key in block_data:
        if key not in obj_idens:
            problem_idens.append(key)
    if problem_idens and log_missing:
        logMissing(problem_idens, reg=block.Blockchain_obj.genesisId, context={'block':block.id})
        logError(f'missing items from valid block {block.id}', code='5832645', func='check_block_contents', region=None, extra=problem_idens)

    update_block = False
    if 'found_idens' not in block.notes:
        block.notes['found_idens'] = []
        update_block = True
    if obj_idens:
        block.notes['found_idens'] = list(set(obj_idens + block.notes['found_idens']))
        update_block = True
    if 'unsupported_chain' not in block.notes:
        if problem_idens:
            if 'problem_idens' not in block.notes:
                block.notes['problem_idens'] = []
            problem_idens = list(set(problem_idens + block.notes['problem_idens']))
            block.notes['problem_idens'] = [p for p in problem_idens if p not in block.notes['found_idens']]
            update_block = True
        elif 'problem_idens' in block.notes:
            del block.notes['problem_idens']
            update_block = True
    if update_block:
        block.save(update_fields=['notes'])
    if update_items and block.validated:
        checked_idens = []
        from utils.models import seperate_by_type, dynamic_bulk_update, get_model, chunk_list
        for model_name, iden_list in seperate_by_type(obj_idens, include_only={'has_field':['Block_obj']}, exclude={'fields':[{'commitChain':f'!{block.Blockchain_obj.genesisType}'}]}).items():
            prnt('model_name',model_name,'iden_list',iden_list)
            checked_idens += iden_list
            if model_name == 'Validator':
                if block.Blockchain_obj.genesisType == 'Sonet':
                    dynamic_bulk_update(model_name, update_data={'Block_obj':block}, id__in=iden_list) # sonet chain includes opChain validators
                else:
                    dynamic_bulk_update(model_name, update_data={'Block_obj':block}, id__in=iden_list, networkChain=block.networkChain)
            else:
                dynamic_bulk_update(model_name, update_data={'Block_obj':block}, id__in=iden_list)
            if has_method(get_model(model_name), 'on_confirmation'):
                for chunk in chunk_list(iden_list, 500):
                    bulk_update = []
                    for i in get_dynamic_model(model_name, list=True, id__in=chunk):
                        i = i.on_confirmation(block)
                        if i:
                            bulk_update.append(i)
                    if bulk_update:
                        dynamic_bulk_update(model=get_model(model_name), update_data={}, items_field_update=[], items=bulk_update, compensate_save=True, return_items=False, retrieve_missing=False)
            elif has_field(get_model(model_name), 'validated'):
                bulk_update = []
                for chunk in chunk_list(iden_list, 500):
                    for i in get_dynamic_model(model_name, list=True, id__in=chunk):
                        if not i.validated:
                            i = validate_obj(obj=i, pointer=None, save_obj=False, update_pointer=True, verify_validator=True, add_to_queue=False, opBlock_data={})
                            if i and i.Validator_obj:
                                bulk_update.append(i.id)
                if bulk_update:
                    dynamic_bulk_update(model_name, update_data={'validated':True}, id__in=bulk_update)
            # if has_method(get_model(model_name), 'on_boot'):
            #     posts = Post.all_objects.filter(pointerId__in=iden_list).values('pointerId','validated')
            #     missing_posts = [iden for iden in iden_list if iden not in [p['pointerId'] for p in posts]]
        for model_name, iden_list in seperate_by_type([i for i in obj_idens if i not in checked_idens], include_only={'has_field':['Block_obj','commitChain']}).items():
            bulk_update = []
            objs = get_dynamic_model(model_name, list=True, id__in=iden_list)
            for obj in objs:
                if obj.commitChain in [block.Blockchain_obj.genesisType, block.Blockchain_obj.genesisId]:
                    obj.Block_obj = block
                    bulk_update.append(obj)
            if bulk_update:
                dynamic_bulk_update(model_name, items_field_update=['Block_obj'], items=bulk_update)
                


    if return_missing:
        return obj_idens, list(set(ineligible + problem_idens))
    return obj_idens


def verify_obj_to_data(obj, target_data, user=None, return_user=False, requireSuper=False, record_error=True):
    from utils.models import prnt, prntDebug
    # obj must be model of target data
    # target_data must be model or convert_to_dict(model)
    # should adjust so obj input is not needed
    f = '---verify_obj_to_data'
    # prntDebug(f) 12a5acdf8ag
    is_valid = False
    users = None
    x = 0
    try:
        from django.db.models import Model
        if not isinstance(target_data, Model):
            record_error = False
        from utils.models import get_user
        from network.models import Validator, Block
        # from utils.locked import sigData_to_hash
        from utils.models import has_method, has_field, get_pointer_type, string_to_dt, value_is_none, now_utc, sigData_to_hash, get_sigData
        from transactions.models import Wallet
        from django.db.models import Q
        failed = False
        upks = None
        block_dt = None
        block = None
        dt = None
        target_dt = None
        user_id = None
        node_id = None
        wallet_id = None
        pubKey = None
        sign_dict = None
        iden = None
        upk_ids = []
        x = '1'

        if isinstance(target_data, dict):
            x += '2'
            # prnt('target_data',target_data)
            iden = target_data['id']
            sign_dict = target_data['signed']
            sig_data = get_sigData(target_data, first_key=False)
            target_dt = sig_data['dt']

            upk_ids.append(sig_data['pk'])
            x += 'x'
            if sig_data['req']:
                for dt, req_data in sig_data['req'].items():
                    val = target_data['signed'][dt]
                    if req_data in val.get('pk',''):
                        upk_ids.append(val['pk'])
            x += 'a'
            if not failed and ('proposed_modification' not in target_data or value_is_none(target_data['proposed_modification'])) and 'Validator_obj' in target_data and not value_is_none(target_data['Validator_obj']):
                x += 'b'
                val = Validator.objects.filter(id=target_data['Validator_obj']).only('data').first()
                # if not val:
                #     failed = True
                #     x += 'd'
                if val:
                    if iden not in val.data:
                        failed = True
                        x += 'c'
                    if val.data[iden] != sigData_to_hash(target_data):
                        failed = True
                        x += 'd'
                    x += 'e'
            try:
                target_data = json.loads(target_data)
            except:
                pass
            if has_method(obj, 'get_hash_to_id') and iden != hash_obj_id(target_data):
                failed = True
                x += 'g'
                prnt('hash_obj_id(target_data)', hash_obj_id(target_data, return_data=True))
            target_data = json.loads(get_signing_data(target_data))
            # prnt('upk_ids',upk_ids)
        elif isinstance(target_data, Model):
            x += '3'
            iden = target_data.id
            sign_dict = target_data.signed
            sig_data = get_sigData(target_data.signed, first_key=False)
            target_dt = sig_data['dt']

            upk_ids.append(sig_data['pk'])

            if sig_data['req']:
                for dt, req_data in sig_data['req'].items():
                    val = target_data.signed[dt]
                    if req_data in val.get('pk',''):
                        upk_ids.append(val['pk'])

            # must check for req
            # get all pks in req
            # pass all upks and signed field to verify_data

            obj = target_data
            if has_method(obj, 'get_hash_to_id') and iden != hash_obj_id(target_data):
                failed = True
                x += 'a'
            if not failed and (not has_field(target_data, 'proposed_modification') or not target_data.proposed_modification) and has_field(target_data, 'Validator_obj') and target_data.Validator_obj:
                x += 'b'
                if not target_data.id in target_data.Validator_obj.data:
                    failed = True
                    x += 'c'
                if target_data.Validator_obj.data[target_data.id] != sigData_to_hash(target_data):
                    failed = True
                    x += 'd'
            prnt('upk_ids',upk_ids)

        if isinstance(target_data, dict):
            x += '5'
            if not failed or return_user:
                x += 'a'
                #     x += 'b'
                # else:
                x += 'c'
                if 'CreatorNode_obj' in target_data or 'id' in target_data and target_data['id'].startswith('nodSo'):
                    x += 'd'
                    from accounts.models import UserPubKey
                    upks = UserPubKey.objects.filter(id__in=upk_ids, created__lte=target_dt).exclude(keyType__in=['account','signing','security']).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=target_dt)).only('User_obj', 'created', 'publicKey')
                    
                    if 'Block_obj' in target_data and target_data['Block_obj']:
                        from network.models import Block
                        block = Block.objects.filter(id=target_data['Block_obj'], validated=True).values('DateTime').first()
                        if block:
                            prnt('target_data.Block_obj2',block)
                            block_dt = block['DateTime']
                    # if not block_dt and has_field(obj, 'Block_obj') and obj.Block_obj:
                    #     block_dt = obj.Block_obj.DateTime
                    if not upks:
                        x += 'f'
                else:

                    x += 'e'
                    if 'Super_User_obj' in target_data:
                        user_id = target_data['Super_User_obj']
                    elif 'SenderWallet_obj' in target_data and not value_is_none(target_data['SenderWallet_obj']):
                        wallet_id = target_data['SenderWallet_obj']
                        user_id = Wallet.objects.filter(id=wallet_id).values('User_obj_id').first()['User_obj']
                    
                    elif 'objType' in target_data and target_data['objType'] == 'User':
                        user_id = target_data['id']
                    elif 'User_obj' in target_data:
                        user_id = target_data['User_obj']
                    if upk_ids:
                    # elif pubKey or 'pkey' in target_data:
                        x += 'g'

                        from accounts.models import UserPubKey
                        # prnt('target_dt',target_dt,'upk_ids',upk_ids,'user_id',user_id)
                        if user_id:
                            x += 'h'
                            upks = UserPubKey.objects.filter(id__in=upk_ids, User_obj__id=user_id, created__lte=target_dt).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=target_dt)).only('User_obj', 'created', 'publicKey')
                        else:
                            x += 'i'
                            upks = UserPubKey.objects.filter(id__in=upk_ids, created__lte=target_dt).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=target_dt)).only('User_obj', 'created', 'publicKey')
                            
        elif isinstance(target_data, Model):
            x += '6'
            # prnt('0001')
            if not failed or return_user:
                x += 'a'
                if not failed:
                    x += 'b'
                if has_field(target_data, 'CreatorNode_obj'):
                    x += 'c'
                    from accounts.models import UserPubKey
                    # should check upks are committed to block, can use target_dt but would need to check blocks on multiple chains, one for each upk
                    upks = UserPubKey.objects.filter(id__in=upk_ids, created__lte=target_dt).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=target_dt)).exclude(keyType__in=['account','signing','security']).only('User_obj', 'created', 'publicKey')

                    if has_field(target_data, 'Block_obj') and target_data.Block_obj and target_data.Block_obj.validated:
                        prnt('target_data.Block_obj',target_data.Block_obj)
                        block_dt = target_data.Block_obj.DateTime
                        block = target_data.Block_obj
                    if not upks:
                        x += 'f'
                else:
                    x += 'd'
                    if has_field(target_data, 'Super_User_obj'):
                        user_id = target_data.Super_User_obj.id
                    elif has_field(target_data, 'SenderWallet_obj') and not value_is_none(target_data.SenderWallet_obj):
                        user_id = target_data.SenderWallet_obj.User_obj.id
                    elif has_field(target_data, 'objType') and target_data._meta.object_name == 'User':
                        user_id = target_data.id
                    elif has_field(target_data, 'User_obj'):
                        user_id = target_data.User_obj.id
                    if upk_ids:
                        x += 'e'
                        from accounts.models import UserPubKey
                        if user_id:
                            x += 'h'
                            upks = UserPubKey.objects.filter(id__in=upk_ids, User_obj__id=user_id, created__lte=target_dt).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=target_dt)).only('User_obj', 'created', 'publicKey')
                        else:
                            x += 'i'
                            upks = UserPubKey.objects.filter(id__in=upk_ids, created__lte=target_dt).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=target_dt)).only('User_obj', 'created', 'publicKey')
                        
                if not failed:
                    x += 'g'
        
        if not failed and not upks and pubKey:
            # not used
            x += '7'
            if user:
                x += 'a'
                user_id = user.id
            elif not user_id and wallet_id:
                x += 'b'
                prnt('wallet_id1',wallet_id)
                user = Wallet.objects.filter(id=wallet_id).only('User_obj').first().User_obj
                user_id = user.id
            if user_id:
                x += 'c'
                from accounts.models import UserPubKey
                from utils.models import is_id, hash_upk_id
                if is_id(pubKey):
                    iden = pubKey
                else:
                    iden = hash_upk_id(pubKey)
                upk = UserPubKey.objects.filter(id=iden, User_obj__id=user_id).only('User_obj', 'created', 'end_life_dt', 'publicKey').first()

        if False:
        # if not users and not failed and not upks or not users and return_user:
            x += '8'
            # prntDebug(f'not user1-- user_id:{user_id}, node_id:{node_id}, wallet_id:{wallet_id}')
            if not failed:
                x += 'a'
            if upks:
                x += 'b'
                user = upk.User_obj
            elif user_id:
                user = get_user(user_id=user_id)
                # prnt('user_id',user_id)
            elif node_id:
                x += 'd'
                from accounts.models import UserPubKey
                from utils.models import is_id, hash_upk_id
                if is_id(pubKey):
                    iden = pubKey
                else:
                    iden = hash_upk_id(pubKey)
                upk = UserPubKey.objects.filter(nodeId=node_id, id=iden, keyType='node', Block_obj__validated=True).only('User_obj', 'created', 'end_life_dt', 'publicKey').first()
                user = upk.User_obj
                if isinstance(target_data, dict) and 'Block_obj' in target_data and target_data['Block_obj']:
                    from blockchain.models import Block
                    block = Block.objects.filter(id=target_data['Block_obj'], validated=True).values('DateTime').first()
                    if block:
                        block_dt = block['DateTime']
                elif isinstance(target_data, Model) and has_field(target_data, 'Block_obj') and target_data.Block_obj:
                    block_dt = target_data.Block_obj.DateTime
                if not block_dt and has_field(obj, 'Block_obj') and obj.Block_obj:
                    block_dt = obj.Block_obj.DateTime
            elif wallet_id:
                x += 'e'
                prnt('wallet_id',wallet_id)
                user = Wallet.objects.filter(id=wallet_id).only('User_obj').first().User_obj
            elif pubKey:
                x += 'g'
                prnt('pubKey',str(pubKey)[:50])
                from accounts.models import UserPubKey
                from utils.models import is_id, hash_upk_id
                if is_id(pubKey):
                    iden = pubKey
                else:
                    iden = hash_upk_id(pubKey)
                prnt('iden',iden)
                upk = UserPubKey.objects.filter(id=iden).only('User_obj', 'created', 'end_life_dt', 'publicKey').first()
                prnt('upk',upk)
                user = upk.User_obj

            # elif iden and get_pointer_type(iden) == 'User':
            #     x += 'f'
            #     user = get_user(user_id=iden)
            else:
                x += 'h'
        
        def record_result(is_valid):
            if is_valid or record_error:
                if isinstance(obj, Model):
                    if not is_valid and record_error:
                        ...
                        # if sigData_to_hash(obj) == sigData_to_hash(target_data):
                            # if record_error and not is_valid and not obj.val_err:
                            #     from utils.models import get_model
                            #     obj.val_err = True
                            #     super(get_model(obj._meta.object_name), obj).save()

        if upks and not failed:
            x += '9'
            prntDebug(f, 'upk-',upks)
            is_valid = False
            if not requireSuper or requireSuper and all(upk for upk in upks if upk.super_level('guardian', dt=target_dt)):
                x += 'a'
                if obj and has_field(obj, 'is_modifiable') and obj.is_modifiable:
                    x += 'aa'
                    if isinstance(target_data, Model):
                        dt = target_data.lastUpdate
                    else:
                        dt = string_to_dt(target_data['lastUpdate'])
                elif block_dt:
                    x += 'b'
                    dt = block_dt
                    # if target_dt and target_dt >= dt:
                    #     x += 'bb'
                    #     failed = True
                    #     prnt('failed1')
                    #     prnt('target_dt',target_dt)
                    #     prnt('dt',dt)
                elif block and block.validated:
                    x += 'c'
                    dt = block.DateTime
                    # if target_dt and target_dt >= dt:
                    #     x += 'cb'
                    #     failed = True
                    #     prnt('failed2')
                    #     prnt('target_dt',target_dt)
                    #     prnt('dt',dt)
                else:
                    dt = target_dt
                if isinstance(target_data, Model):
                    x += 'd'
                    target_data = json.loads(get_signing_data(target_data))
                if not dt:
                    raise ValueError(f"dt not found x:{x}")
                x += 'g'
                # prnt('dt',dt,'upk.created',upk.created)
                if not failed and all(upk for upk in upks if upk.created <= dt):
                    x += 'h'
                    if return_user:
                        users = [upk.User_obj for upk in upks]
                    # if all(upk for upk in upks if not upk.end_life_dt or dt and dt < upk.end_life_dt):
                    #     x += 'i'
                    is_valid = verify_data(target_data, upks, sign_dict)
        elif user and not failed:
            x += '10'
            prntDebug(f, 'user-',user)
            if not failed and not requireSuper or not failed and requireSuper and user.assess_super_status(dt=target_dt):
                x += 'a'
                is_valid = user.verify_sig(target_data, sig, pubKey=pubKey)
            else:
                prnt('failed validate',failed,'requireSuper',requireSuper,'user.id',user.id,'x',x)
        prntDebug('verify_obj_to_data status:', x)
        # record_result(is_valid)
    except Exception as e:
        prnt(f'verify_obj_to_data error -{x}, iden:{iden}',str(e))
    if not is_valid:
        prntDebug(f, f'**FAILED IS_VALID** err:{x} hardFail:{failed}, iden:{iden}, data:{str(target_data)[:1000]}, now:{now_utc()}')
        prnt('get_signing_data(target_data)',get_signing_data(target_data))
    if return_user and users:
        return is_valid, users
    if return_user:
        return is_valid, x
    else:
        return is_valid

def generate_mnemonic():
    from mnemonic import Mnemonic
    return Mnemonic("english").generate(strength=256)


def sort_dict(data):
    # prnt('sort_ditc','str:',isinstance(data,str),'tuple:',isinstance(data, tuple), str(data)[:200])

    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return sort_dict(parsed)
        except json.JSONDecodeError:
            return data
    if isinstance(data, dict):
        return {key: sort_dict(value) for key, value in sorted(data.items(), key=lambda x: str(x[0]))}
    elif isinstance(data, (list, tuple)):
        return [sort_dict(item) for item in data]
    else:
        return data
    
_key_cache = None
def load_key():
    from .models import prnt
    # prnt('-load_key')
    global _key_cache
    if _key_cache is not None:
        return _key_cache
    import os
    system = platform.system()
    # prnt('load_key',system)
    if system == 'Windows':
        file_path = os.path.expanduser(f"~/Sonet/.data/special/keys/.soSecret.key")
        # file_path = "../.data/special/keys/.soSecret.key"
    elif system in ('Linux', 'Darwin'):
        file_path = os.path.expanduser(f"~/Sonet/.data/special/keys/.soSecret.key")
        # file_path = "../.data/special/keys/.soSecret.key"
    # prnt('file_path',file_path)
    try:
        with open(file_path, "rb") as f:
            _key_cache = f.read()
            return _key_cache
    except Exception as e:
        # from utils.models import prnt
        prnt('load_key error 352',str(e))
        from pathlib import Path
        prnt('folder contents1:',[p.name for p in Path("../.data/special").iterdir()])
        prnt('folder contents2:',[p.name for p in Path("../.data/special/keys").iterdir()])
        pass


import hashlib

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def merkle_root(leaves: list[bytes]) -> bytes:
    """
    leaves: list of validation byte blobs
    returns: merkle root (bytes)
    """
    if not leaves:
        raise ValueError("Cannot build Merkle tree with no leaves")

    # Hash leaves
    level = [sha256(leaf) for leaf in leaves]

    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])  # duplicate last

        next_level = []
        for i in range(0, len(level), 2):
            combined = level[i] + level[i + 1]
            next_level.append(sha256(combined))

        level = next_level

    return level[0]

def merkle_proof(leaves: list[bytes], index: int):
    """
    Returns a proof for leaves[index]
    proof = [(sibling_hash, is_left_sibling), ...]
    """
    if index < 0 or index >= len(leaves):
        raise IndexError("Invalid leaf index")

    hashes = [sha256(leaf) for leaf in leaves]
    proof = []
    idx = index

    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])

        sibling_index = idx ^ 1
        proof.append((
            hashes[sibling_index],
            sibling_index < idx
        ))

        idx //= 2
        next_level = []
        for i in range(0, len(hashes), 2):
            next_level.append(sha256(hashes[i] + hashes[i + 1]))

        hashes = next_level

    return proof

def verify_merkle_proof(
    leaf: bytes,
    proof: list[tuple[bytes, bool]],
    expected_root: bytes
    ) -> bool:
    """
    leaf: validation bytes
    proof: output from merkle_proof()
    expected_root: root stored in block
    """
    current_hash = sha256(leaf)

    for sibling_hash, sibling_is_left in proof:
        if sibling_is_left:
            current_hash = sha256(sibling_hash + current_hash)
        else:
            current_hash = sha256(current_hash + sibling_hash)

    return current_hash == expected_root
    



# DO NOT TOUCH BELOW UNDER ANY CIRCUMSTANCES




# assignment alogrithms

def position_sort(starting_position, pattern, active_set, number_of_matches, max_pos=None):
    # equivalent to find_matches in default.js
    '''Deterministic Position Traversal

        Used for creating a list of nodes from a user id that adjusts as nodes go online/offline without significant changes to the list.
        This function selects positions using a deterministic modular stepping algorithm designed to:
            •	Ensure reproducible ordering
            •	Distribute selections evenly across the full range
            •	Guarantee complete coverage before repetition


        How It Works
        1. Starting Point
            The initial position is derived from:

            starting_position + pattern

            This is wrapped into the valid range [1, max_number].

        2. Step Size Selection
            A step value is deterministically derived from pattern and adjusted so that:

            gcd(step, max_number) == 1

            Ensuring the step is coprime with max_number guarantees that every position in the range will be visited exactly once before repeating.

        3. Traversal Rule
            Each successive position is computed as:

            next_position = (current_position + step) mod max_number

            (wrapped to 1-based indexing)

        ⸻

        Why Coprime Step Matters
        When the step and max_number are coprime, modular arithmetic ensures a full permutation cycle.
        This prevents short cycles or repeated subsets and guarantees complete deterministic traversal.

        ⸻

        Properties
            •	Fully deterministic (same inputs → same output)
            •	No randomness required
            •	No state mutation during traversal
            •	Works identically across languages (e.g., JavaScript and Python)
            •	Safe for distributed systems requiring reproducible ordering
    '''

    from math import gcd
    from utils.models import is_id
    from network.models import Node
    if not max_pos:
        highest_node = Node.objects.exclude(Block_obj=None).order_by('-pos').values('pos').first()
        max_pos = highest_node['pos']
    if is_id(starting_position):
        node = Node.objects.filter(id=starting_position).values('pos').first()
        starting_position = node['pos']


    if max_pos <= 0:
        return []

    matches = []
    visited = set()

    #  Initial position (1-based safe wrap)
    start = ((starting_position + pattern - 1) % max_pos) + 1

    #  Deterministic step derived from pattern
    step = abs(pattern) % max_pos
    if step == 0:
        step = 1

    #  Force coprime step
    while gcd(step, max_pos) != 1:
        step = (step + 1) % max_pos
        if step == 0:
            step = 1

    current_pos = start

    for _ in range(max_pos):
        if len(matches) >= number_of_matches:
            break

        if current_pos in active_set and current_pos not in visited:
            matches.append(active_set[current_pos])
            visited.add(current_pos)

        current_pos = ((current_pos + step - 1) % max_pos) + 1

    return matches

def position_sort_old(starting_id, pattern, nodes_dict, number_of_matches, max_pos=None):
    from utils.models import prnt
    prnt('-position_sort')

    def find_matches(active_set, starting_position, pattern, max_pos, number_of_matches):
        prnt('find_matches',active_set,'starting_position',starting_position,'pattern',pattern,'max_pos',max_pos,'number_of_matches',number_of_matches)
        tries = 0
        saltA = 0
        saltB = 1
        matches = {}
        total_tries = 500
        if max_pos > total_tries:
            total_tries = max_pos
        current_pos = starting_position + pattern
        while len(matches) < number_of_matches:
            tries += 1
            current_pos = ((current_pos - 1) % max_pos) + 1
            if current_pos in active_set and current_pos not in matches:
                matches[current_pos] = active_set[current_pos]

            current_pos += (pattern + saltA)

            if current_pos > max_pos:
                saltA = (saltA + saltB) % max_pos
                saltB = (saltB + 7) % max_pos

            if len(matches) == len(active_set) or tries == total_tries:
                break
        if len(matches) < number_of_matches and number_of_matches <= len(active_set):
            # print('ROUND TWO',tries)
            current_pos = starting_position
            tries = 0
            while len(matches) < number_of_matches:
                tries += 1
                if current_pos in active_set and current_pos not in matches:
                    matches[current_pos] = active_set[current_pos]
                current_pos += 1
                if current_pos > max_pos:
                    current_pos = 1
                if tries == max_pos:
                    break
        # print('\nmatches_len:',len(matches),'/',number_of_matches,'\nlen(active_set):',len(active_set),'\ntries:',tries)
        return [matches[i] for i in matches]
    
    active_set = {value['pos']:iden for iden, value in nodes_dict.items()}
    # prnt('active_set',active_set)
    starting_pos = nodes_dict[starting_id]['pos']
    # prnt('starting_pos',starting_pos)
    if not max_pos:
        from network.models import Node
        highest_node = Node.objects.exclude(Block_obj=None).order_by('-pos').values('pos').first()
        # prnt('highest_node',highest_node)
        max_pos = highest_node['pos']
    # prnt('max_pos',max_pos)
    node_match_idens = find_matches(active_set, starting_pos, pattern, max_pos, number_of_matches)
    prnt('position_sort node_match_idens',node_match_idens)
    # prnt('result:',{iden:nodes_dict[iden]['addr'] for iden in node_match_idens})
    # return {iden:nodes_dict[iden]['addr'] for iden in node_match_idens}
    return node_match_idens

def get_node_assignment(obj=None, dt=None, func=None, chainId=None, return_receiverTransaction=False, full_validator_list=False, full_creator_list=False, strings_only=False, include_relays=False, opBlock_data=None, nodeType=''):
    import random
    from network.models import get_required_validator_count
    from utils.models import round_time, dt_to_string, prnt, string_to_dt, declare_var, get_chain_id, has_method
    opBlock_data = declare_var(opBlock_data, {})
    prnt('----get_node_assignment obj:', obj, 'dt',dt, 'func',func, 'strings:', strings_only,'chainId',chainId,'opBlock_data',opBlock_data,'return_receiverTransaction',return_receiverTransaction)

    def shuffle_nodes(text_input, dt, node_ids):
        # prnt('shuffle_nodes node_ids',node_ids)
        dt_str = dt_to_string(dt)
        seed_input = f"{text_input}_{dt_str}"
        # prnt('seed_input',seed_input)
        seed_hash = hashlib.sha256(seed_input.encode('utf-8')).hexdigest()
        seed_int = int(seed_hash, 16)
        rng = random.Random(seed_int)
        # node_ids.sort()
        # shuffled_nodes = node_ids.copy()
        shuffled_nodes = node_ids.copy()
        rng.shuffle(shuffled_nodes)
        # prnt('shuffled_nodes',shuffled_nodes)
        return shuffled_nodes

    is_transaction = False
    chain_list = None
    required_validators = 0
    required_scrapers = 0
    broadcast_list = {}
    validator_list = []
    scraper_list = []
    creator_nodes = []
    node_ids = None
    number_of_peers = None
    relevant_nodes = None
    valid_node_ids_received = False
    v = 0
    if opBlock_data:
        try:
            import copy
            node_dict = copy.deepcopy(opBlock_data)
            node_ids = [i for i in node_dict['relevant_nodes']]
            valid_node_ids_received = True
        except Exception as e:
            try:
                node_ids = [n for n in opBlock_data]
                valid_node_ids_received = True
            except Exception as e:
                prnt('node_assignment_error',str(e))

    if obj and obj._meta.object_name == 'Block' or obj and obj._meta.object_name == 'Transaction':

        if obj._meta.object_name == 'Block' and not obj.Transaction_obj or obj._meta.object_name == 'Block' and 'BlockReward' in obj.Transaction_obj.regarding and obj.Transaction_obj.regarding['BlockReward'] == obj.id:
            
            from network.models import _OperationsChain_genesisId
            if obj.networkChain == _OperationsChain_genesisId:
                dt = string_to_dt(obj.DateTime) - datetime.timedelta(minutes=20) # block is created 20 mins early
                shuffle_seed = f'opBlock_seed_{dt}'
            else:
                if not dt:
                    dt = string_to_dt(obj.DateTime)
                shuffle_seed = obj.id
            if obj.networkChain in ['Sonet',_OperationsChain_genesisId]:
                include_relays = True
            if not valid_node_ids_received:
                opBlock_data = get_relevant_nodes_from_block(dt=dt, obj=obj, genesisId=obj.Blockchain_obj.genesisId, strings_only=strings_only, include_relays=include_relays)
                node_ids = [i for i in opBlock_data['relevant_nodes']]
            # prnt('node_ids',node_ids)
            
            if not dt:
                dt = string_to_dt(obj.DateTime)
            shuffled_nodes = shuffle_nodes(shuffle_seed, dt, node_ids)
            if full_validator_list:
                required_validators = len(node_ids)
            else:
                required_validators = get_required_validator_count(obj=obj, node_ids=node_ids, opBlock_data=opBlock_data)
            # prnt('required_validators',required_validators)
            if full_creator_list:
                creator_nodes = shuffled_nodes
            else:
                creator_nodes = shuffled_nodes[:opBlock_data['opData']['block_creator_count']]
            # if len(shuffled_nodes) >= required_validators + available_creators:
            validator_nodes = list(reversed(shuffled_nodes[-required_validators:]))
            # else:
            #     validator_nodes = list(reversed(shuffled_nodes[-required_validators:]))
            prnt('assignment path 1a',obj,creator_nodes, validator_nodes)
            return creator_nodes, validator_nodes

        else:
            block = None
            if obj._meta.object_name == 'Block' and obj.Transaction_obj:
                block = obj
                obj = obj.Transaction_obj
            if obj._meta.object_name == 'Transaction' and 'BlockReward' in obj.regarding and obj.regarding['BlockReward']:
                
                if return_receiverTransaction:
                    shuffle_seed = obj.id # shuffle seed for ReceiverBlock_obj is tx.id for determining ReceieverBlock creator
                    if not dt and block:
                        dt = block.DateTime
                    elif not dt and obj.ReceiverBlock_obj:
                        dt = obj.ReceiverBlock_obj.DateTime

                    from network.models import Plugin
                    plugin = Plugin.objects.filter(app_name='transactions').exclude(Block_obj=None).values('id').first()
                    from accounts.models import User
                    user = User.objects.filter(id=obj.ReceiverWallet_obj.networkChain).values('nodeCreatorId','pattern').first()
                    opBlock_data = get_relevant_nodes_from_block(dt=dt, genesisId=plugin['id'], strings_only=strings_only, include_relays=False)

                    node_ids = position_sort(user['nodeCreatorId'], user['pattern'], opBlock_data['relevant_nodes'], opBlock_data['opData']['number_of_peers'])
                    valid_node_ids_received = True

                elif block: # block is RecevierBlock - same as inputting obj=tx and return_receiverTransaction=True
                    shuffle_seed = obj.id
                    chain = block.networkChain
                    if not dt:
                        dt = block.DateTime

                else:
                    shuffle_seed = obj.senderBlockId # tx can determine SenderBlock creators and validators
                    chain = get_chain_id(obj.senderChainGenId)

                if not dt:
                    dt = obj.created
                if not valid_node_ids_received:
                    # consider for consistency:
                    # required_validators, opBlock_data = block.get_required_validator_count(return_node_data=True)
                    opBlock_data = get_relevant_nodes_from_block(dt=dt, obj=obj, blockchain=chain, strings_only=strings_only, include_relays=include_relays)
                    node_ids = [i for i in opBlock_data['relevant_nodes']]

                shuffled_nodes = shuffle_nodes(shuffle_seed, dt, node_ids)
                if full_validator_list:
                    required_validators = len(node_ids)
                    # prnt('required_validators2',required_validators)
                else:
                    required_validators = get_required_validator_count(obj=obj, node_ids=node_ids, opBlock_data=opBlock_data)
                    # prnt('required_validators1',required_validators)

                creator_nodes = shuffled_nodes[:opBlock_data['opData']['block_creator_count']]
                validator_nodes = list(reversed(shuffled_nodes[-required_validators:]))
                prnt('assignment path 1b',obj,creator_nodes, validator_nodes)
                return creator_nodes, validator_nodes

            else: # user to user transaction - to be completed later
                
                user = obj.ReceiverWallet_obj.User_obj

                if return_receiverTransaction:
                        
                    if not dt:
                        dt = round_time(dt=obj.created, dir='down', amount='10mins')
                    # get genesisId from user region (country? only if enough available, else larger region)
                    opBlock_data = get_relevant_nodes_from_block(dt=dt, for_user=True, sublist='server')
                    # prnt('opBlock_data',opBlock_data)
                    required_validators = get_required_validator_count(obj=user, node_ids=[i for i in opBlock_data['relevant_nodes']])

                    user_assigned_nodes = position_sort(user.nodeCreatorId, user.pattern, opBlock_data['relevant_nodes'], opBlock_data['opData']['number_of_peers'])

                # dt = round_time(dt=obj.created, dir='down', amount='evenhour')
                # if sender_transaction: # reverse receiver/sender
                #     shuffle_seed = obj.SenderWallet_obj.id
                # else:
                #     shuffle_seed = obj.ReceiverWallet_obj.id
                # if not valid_node_ids_received:
                #     node_ids = get_relevant_nodes_from_block(dt=dt, obj=obj, strings_only=strings_only, node_ids_only=True, include_relays=include_relays)
                # shuffled_nodes = browser_shuffle(shuffle_seed, dt, node_ids)
                

                # available_creators, required_validators = get_required_validator_count(obj=obj, node_ids=node_ids, include_initializers=True)

                return [], []

            creator_nodes = shuffled_nodes[:opBlock_data['opData']['block_creator_count']]
            validator_nodes = list(reversed(shuffled_nodes[-required_validators:]))
            prnt('assignment path 2',obj,creator_nodes, validator_nodes)
            return creator_nodes, validator_nodes

    elif has_method(obj, 'get_assignment'):
        return obj.get_assignment()

    elif obj and obj._meta.object_name == 'DataPacket':
        chain_list = [obj.chainId]

        if not dt:
            dt = round_time(dt=obj.created, dir='down', amount='10mins')
        # if not valid_node_ids_received:
        #     node_ids, number_of_peers, relevant_nodes = get_relevant_nodes_from_block(dt=dt, blockchain=obj.chainId, strings_only=strings_only)
        if obj.Node_obj:
            if strings_only:
                creator_nodes.append(obj.Node_obj.id)
            else:
                creator_nodes.append(obj.Node_obj)
        # date_int = date_to_int(dt)
        # starting_position = hash_to_int(obj.id, len(node_ids))


        if not valid_node_ids_received:
            node_ids = get_relevant_nodes_from_block(dt=dt, blockchain=obj.networkChain, strings_only=strings_only, node_ids_only=True, include_relays=include_relays)
        shuffled_nodes = shuffle_nodes(obj.id, dt, node_ids)
        return shuffled_nodes, []

        # creator_nodes = shuffled_nodes[:available_creators]
        # validator_nodes = shuffled_nodes[-required_validators]
        # return creator_nodes, validator_nodes
        
    elif obj and obj._meta.object_name == 'Validator':
        # chain = Blockchain.objects.filter(id=obj.networkChain).first()
        # chain_list = [chain.genesisId]
        dt = round_time(dt=obj.created, dir='down', amount='10mins')
        if not valid_node_ids_received:
            node_ids = get_relevant_nodes_from_block(dt=dt, blockchain=obj.networkChain, strings_only=strings_only, node_ids_only=True)
        # date_int = date_to_int(dt)
        # starting_position = hash_to_int(obj.id, len(node_ids))

        shuffled_nodes = shuffle_nodes(obj.id, dt, node_ids)
        return shuffled_nodes, []
 
    elif obj and obj._meta.object_name == 'Node':
        chain_list = obj.chain_array
        if not dt:
            dt = round_time(dt=obj.lastUpdate, dir='down', amount='10mins')
        # if not valid_node_ids_received:
        #     node_ids, number_of_peers, relevant_nodes = get_relevant_nodes_from_block(dt=dt, strings_only=strings_only)
        # date_int = date_to_int(dt)
        # starting_position = hash_to_int(obj.id, len(node_ids))


        if not valid_node_ids_received:
            node_ids = get_relevant_nodes_from_block(dt=dt, strings_only=strings_only, node_ids_only=True, include_relays=include_relays)
        shuffled_nodes = shuffle_nodes(obj.id, dt, node_ids)
        return shuffled_nodes, []
    
    elif obj and obj._meta.object_name == 'User':
        # return a simple ordered list of nodes for user to connect to
        # user will connect to node in order of validator list.
        # build list according to chainId, servers not scripts
        # user transactions are validated by first x number of nodes on list at time of creation. transaction must have a region_obj if user is using region list, which currently is
        # transaction blocks are created for sender and receiver. sender block is created/validated by list of nodes assigned to sender of transaction, receiver will have his own list \
        # how to get list of nodes to validate receiver block? someone needs to have receiver region so nodes know where to send the validated transaction. \
        # other option is transactions are worldwide, no region assignment needed. use a seperate (world) list for transactions than normal list that connects user to server
        # correct validator nodes are needed because nodes are assigned to a user for a period of time rather than all nodes doing all transactions at all times
        # would be nice to be region specific so smaller regions are able to use lesser hardware and fewer nodes? could create issues for those regions if nodes not responding, transactions would fail
        if not dt:
            dt = round_time(dt=obj.lastUpdate, dir='down', amount='evenhour')
        # get genesisId from user region (country? only if enough available, else larger region)
        opBlock_data = get_relevant_nodes_from_block(dt=dt, for_user=True, sublist='server')
        required_validators = get_required_validator_count(obj=obj, node_ids=[i for i in opBlock_data['relevant_nodes']])

        user_assigned_nodes = position_sort(obj.nodeCreatorId, obj.pattern, opBlock_data['relevant_nodes'], opBlock_data['opData']['number_of_peers'])

        if len(user_assigned_nodes) >= opBlock_data['opData']['block_creator_count'] + required_validators:
            validator_nodes = user_assigned_nodes[opBlock_data['opData']['block_creator_count']:]
        else:
            validator_nodes = user_assigned_nodes

        return user_assigned_nodes, validator_nodes
        
    elif obj:
        dt = round_time(dt=obj.created, dir='down', amount='10mins')
        if not valid_node_ids_received:
            # likely returns full active node list
            node_ids = get_relevant_nodes_from_block(dt=dt, obj=obj, strings_only=strings_only, node_ids_only=True, include_relays=include_relays)
        shuffled_nodes = shuffle_nodes(obj.id, dt, node_ids)
        prnt('assignment path 4',shuffled_nodes)
        return shuffled_nodes, []
    
    elif func:
        # prnt('is func',func,'chainId',chainId)
        from network.models import Blockchain, intelligence_funcs
        from django.db import models
        if isinstance(chainId, models.Model):
            chainId = chainId.id
        else:
            from utils.models import get_model_prefix
            if not chainId.startswith(get_model_prefix('Blockchain')):
                chainId = Blockchain.objects.filter(genesisId=chainId).values('id').first()['id']
        if func in intelligence_funcs or nodeType == 'intelligence':
            node_ids = get_relevant_nodes_from_block(dt=dt, blockchain=chainId, strings_only=strings_only, node_ids_only=True, include_relays=False, sublist='intelligence')
            shuffled_nodes = shuffle_nodes(func, dt, node_ids)
            required_scrapers, required_validators = 1, 1
            # prnt('shuffled_nodes',shuffled_nodes,'required_validators',required_validators)
            creator_nodes = shuffled_nodes[:required_scrapers]
            if len(node_ids) <= required_scrapers:
                node_ids = get_relevant_nodes_from_block(dt=dt, blockchain=chainId, strings_only=strings_only, node_ids_only=True, include_relays=False, sublist='maintainer')
                shuffled_nodes = shuffle_nodes(func, dt, node_ids)

            validator_nodes = list(reversed(shuffled_nodes[-required_validators:]))
            return creator_nodes, validator_nodes
        else:
            if not nodeType and 'get_' in func:
                nodeType = 'maintainer'
            if not valid_node_ids_received:
                node_ids = get_relevant_nodes_from_block(dt=dt, blockchain=chainId, strings_only=strings_only, node_ids_only=True, include_relays=include_relays, sublist=nodeType)
            shuffled_nodes = shuffle_nodes(func, dt, node_ids)
            required_scrapers, required_validators = get_required_validator_count(dt=dt, func=func, node_ids=node_ids, include_initializers=True)
            # prnt('shuffled_nodes',shuffled_nodes,'required_validators',required_validators)
            creator_nodes = shuffled_nodes[:required_scrapers]
            validator_nodes = list(reversed(shuffled_nodes[-required_validators:]))
            prnt('assignment path 5',creator_nodes, validator_nodes)
            return creator_nodes, validator_nodes
    return [], []
            

# key generation/sign/verify

# helpers
def bytes_to_base64url(data):
    if isinstance(data, str):
        return data
    return base64.urlsafe_b64encode(data).decode().rstrip('=')

def base64url_to_bytes(s):
    if isinstance(s, bytes):
        return s
    s += '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def detect_security(key, key_type='sk'):
    from utils.models import prnt, is_id
    SK_SIZES = {32: 'secp256k1', 66: 'P521', 2560: 'ML_DSA_44', 4032: 'ML_DSA_65', 4896: 'ML_DSA_87'}
    PK_SIZES = {65: 'secp256k1', 133: 'P521', 1312: 'ML_DSA_44', 1952: 'ML_DSA_65', 2592: 'ML_DSA_87'}
    SIG_SIZES = {132: 'P521', 2420: 'ML_DSA_44', 3309: 'ML_DSA_65', 4627: 'ML_DSA_87'}
    if is_id(key):
        from accounts.models import UserPubKey
        upk = UserPubKey.objects.filter(id=key).values('algorithm').first()
        if upk:
            return upk['algorithm']
    data = base64url_to_bytes(key)
    byte_len = len(data)
    if key_type == 'pubkey' and byte_len == 65 and data[0] == 0x04:
        return 'secp256k1'
    if key_type == 'pubkey' and byte_len == 133 and data[0] == 0x04:
        return 'P521'
    sizes = SK_SIZES if key_type == 'privkey' else PK_SIZES if key_type == 'pubkey' else SIG_SIZES
    level = sizes.get(byte_len)
    if not level:
        raise ValueError(f"Unknown {key_type} size: {byte_len} bytes")
    return level

def get_ml_dsa(key_strength):
    if key_strength == 'ML_DSA_44':
        from dilithium_py.ml_dsa import ML_DSA_44
        return ML_DSA_44
    elif key_strength == 'ML_DSA_65':
        from dilithium_py.ml_dsa import ML_DSA_65
        return ML_DSA_65
    else:
        from dilithium_py.ml_dsa import ML_DSA_87
        return ML_DSA_87

# ml_dsa
def create_keys_ml_dsa(user_id, user_pass, key_strength='ML_DSA_44'):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.backends import default_backend
    # from utils.models import prnt
    # prnt('user_id',user_id,'user_pass',user_pass)
    salt = hashlib.sha256(f"{user_id}:{user_pass}".encode()).digest()
    if len(user_pass) > 120:
        n = 16384
    elif len(user_pass) > 40:
        n = 65536
    else:
        n = 262144
    kdf = Scrypt(salt=salt, length=32, n=n, r=8, p=1, backend=default_backend())
    seed = kdf.derive(user_pass.encode())
    pk, sk = get_ml_dsa(key_strength)._keygen_internal(seed)
    return bytes_to_base64url(sk), bytes_to_base64url(pk)

def simpleSign_ml_dsa(secret_key, data, key_strength='ML_DSA_44'):
    sk = base64url_to_bytes(secret_key)
    message = (data).encode('utf-8')
    signature = get_ml_dsa(key_strength).sign(sk, message)
    return bytes_to_base64url(signature)

def simpleVerify_ml_dsa(data, signature, public_key, key_strength='ML_DSA_44'):
    from utils.models import prnt
    sig_strength = detect_security(signature, key_type='sig')
    if key_strength != sig_strength:
        raise ValueError(f"Key/signature level mismatch: key={key_strength}, sig={sig_strength}")
    pk = base64url_to_bytes(public_key)
    sig = base64url_to_bytes(signature)
    message = (data).encode('utf-8')
    is_valid = get_ml_dsa(key_strength).verify(pk, message, sig)
    if is_valid:
        prnt(f"{key_strength} Signature is *VALID*")
    else:
        prnt(f"{key_strength} Signature is *INVALID*")
    return is_valid

# secp256k1
def create_keys_secp256k1(user_id, user_pass):
    import hashlib
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ec import SECP256K1
    from utils.models import prnt

    salt = hashlib.sha256(f"{user_id}:{user_pass}".encode()).digest()
    # prnt('salt',salt)
    password = user_pass.encode()
    if len(user_pass) > 120:
        n = 16384
    elif len(user_pass) > 40:
        n = 65536
    else:
        n = 262144
    kdf = Scrypt(salt=salt, length=32, n=n, r=8, p=1, backend=default_backend())

    seed = kdf.derive(password)
    # prnt("Derived seed:", seed.hex())

    priv_int = int.from_bytes(seed, 'big')
    curve = SECP256K1()
    order = int("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)
    priv_int = priv_int % order
    if priv_int == 0:
        priv_int = 1

    private_key = ec.derive_private_key(priv_int, curve, default_backend())
    priv_key_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
    # prnt("Private Key (hex):", priv_key_bytes.hex())

    public_key = private_key.public_key()
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    # prnt("Public Key (hex):", public_key_bytes.hex())
    # return priv_key_bytes.hex(), public_key_bytes.hex()
    return bytes_to_base64url(priv_key_bytes), bytes_to_base64url(public_key_bytes)
    


def simpleSign_secp256k1(private_key, data):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key_bytes = base64url_to_bytes(private_key)
    private_key = ec.derive_private_key(int.from_bytes(private_key_bytes, byteorder='big'), ec.SECP256K1())
    signature = private_key.sign((data).encode('utf-8'), ec.ECDSA(hashes.SHA256()))
    return bytes_to_base64url(signature)

def simpleVerify_secp256k1(data, signature, public_key):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidSignature
    from utils.models import prnt
    prnt('-simpleVerify_secp256k1',len(str(data)),str(data)[:100],type(data),str(signature)[:25], str(public_key)[:25])
    try:
        pub_bytes = base64url_to_bytes(public_key)
        sig_bytes = base64url_to_bytes(signature)
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pub_bytes)
        try:
            public_key.verify(sig_bytes, (data).encode('utf-8'), ec.ECDSA(hashes.SHA256()))
            prnt("SECP Signature is *VALID*")
            return True
        except InvalidSignature:
            prnt("SECP Signature !!INVALID!!")
    except Exception as e:
        prnt('VERIFY err3',str(e))
    return False



def create_keys_p521(user_id, user_pass):
    import hashlib
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ec import SECP521R1
    from utils.models import prnt
    prnt('-create_keys_p521',user_id, user_pass)
    salt = hashlib.sha256(f"{user_id}:{user_pass}".encode()).digest()
    password = user_pass.encode()
    if len(user_pass) > 120:
        n = 16384
    elif len(user_pass) > 40:
        n = 65536
    else:
        n = 262144
    kdf = Scrypt(salt=salt, length=32, n=n, r=8, p=1, backend=default_backend())

    seed = kdf.derive(password)
    # prnt("Derived seed:", seed.hex())

    FIELD_BYTES = 66
    ORDER_N = 0x01fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffa51868783bf2f966b7fcc0148f709a5d03bb5c9b8899c47aebb6fb71e91386409

    hkdf = HKDF(
        algorithm=hashes.SHA512(),
        length=FIELD_BYTES + 8,
        salt=b'',
        info=b'ecdsa-p521-key',
    )
    okm = hkdf.derive(seed)
    priv_int = int.from_bytes(okm, 'big') % ORDER_N
    if priv_int == 0:
        priv_int = 1

    curve = SECP521R1()
    private_key = ec.derive_private_key(priv_int, curve, default_backend())
    priv_key_bytes = private_key.private_numbers().private_value.to_bytes(FIELD_BYTES, 'big')
    # prnt("Private Key (hex):", priv_key_bytes.hex())

    public_key = private_key.public_key()
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    # prnt("Public Key (hex):", public_key_bytes.hex())
    return bytes_to_base64url(priv_key_bytes), bytes_to_base64url(public_key_bytes)

def _raw_to_der_p521(sig_raw: bytes) -> bytes:
    FIELD_BYTES_P521 = 66  # 521-bit curve, fixed-width r/s
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    assert len(sig_raw) == FIELD_BYTES_P521 * 2, f"Unexpected P521 sig length: {len(sig_raw)}"
    r = int.from_bytes(sig_raw[:FIELD_BYTES_P521], 'big')
    s = int.from_bytes(sig_raw[FIELD_BYTES_P521:], 'big')
    return encode_dss_signature(r, s)

def _der_to_raw_p521(sig_der: bytes) -> bytes:
    FIELD_BYTES_P521 = 66  # 521-bit curve, fixed-width r/s
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    r, s = decode_dss_signature(sig_der)
    return r.to_bytes(FIELD_BYTES_P521, 'big') + s.to_bytes(FIELD_BYTES_P521, 'big')

def simpleSign_P521(private_key, data):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from utils.models import prnt
    prnt('-simpleSign_P521', len(str(data)), str(data)[:100], type(data), str(private_key)[:25])

    private_key_bytes = base64url_to_bytes(private_key)
    private_key = ec.derive_private_key(int.from_bytes(private_key_bytes, byteorder='big'), ec.SECP521R1())
    der_sig = private_key.sign((data).encode('utf-8'), ec.ECDSA(hashes.SHA512()))
    raw_sig = _der_to_raw_p521(der_sig)
    return bytes_to_base64url(raw_sig)

def simpleVerify_P521(data, signature, public_key):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidSignature
    from utils.models import prnt
    prnt('-simpleVerify_P521', len(str(data)), str(data)[:100], type(data), str(signature)[:25], str(public_key)[:25])
    try:
        pub_bytes = base64url_to_bytes(public_key)
        prnt('1')
        sig_bytes = base64url_to_bytes(signature)
        prnt('12')
        der_sig = _raw_to_der_p521(sig_bytes)
        prnt('13')
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP521R1(), pub_bytes)
        prnt('14')
        try:
            public_key.verify(der_sig, (data).encode('utf-8'), ec.ECDSA(hashes.SHA512()))
            prnt("P521 Signature is *VALID*")
            return True
        except InvalidSignature:
            prnt("P521 Signature !!INVALID!!")
    except Exception as e:
        prnt('VERIFY err3', str(e))
    return False

# funcs
def create_keys(user_id, user_pass, key_type, key_strength='secp256k1'):
    # from utils.models import prnt
    # prnt('-create_keys',key_strength, user_id)
    user_pass = key_type + user_pass
    if key_strength == 'secp256k1':
        return create_keys_secp256k1(user_id, user_pass)
    elif key_strength == 'P521':
        return create_keys_p521(user_id, user_pass)
    else:
        return create_keys_ml_dsa(user_id, user_pass, key_strength)

def simpleSign(private_key, data, key_type=None):
    data = data + 'ycF3atcq61TMBvVmGwrQWZJ69fu'
    from utils.models import prnt
    # prnt('privkey:',private_key)
    prnt('signing....',key_type,len(str(data)))
    # prnt('key_type',key_type)
    if key_type == None:
        key_type = detect_security(private_key, key_type='privkey')
    # prnt('key_type',key_type)
    if key_type == 'secp256k1':
        return simpleSign_secp256k1(private_key, data)
    elif key_type == 'P521':
        return simpleSign_P521(private_key, data)
    else:
        return simpleSign_ml_dsa(private_key, data, key_type)

def simpleVerify(data, sig, pubKey, key_type='secp256k1'):
    if key_type == 'secp256k1':
        return simpleVerify_secp256k1(data, sig, pubKey)
    elif key_type == 'P521':
        return simpleVerify_P521(data, sig, pubKey)
    else:
        return simpleVerify_ml_dsa(data, sig, pubKey, key_type)

def verify_data(data, public_key, signature=None, key_type=None, skip_sort=False, upk_bypass=False):
    from utils.models import prnt, prntDebug, has_field, is_id, hash_upk_id, string_to_dt, resolve_target_keys
    prnt('-verify_data', str(public_key)[:50], str(signature)[:50], type(data))
    from django.db import models
    from django.db.models import QuerySet
    err = 0
    # data can be str, model or get_signing_data, not convert_to_dict
    # public_key could be:
    # single upk obj
    # single upk id
    # single pubkey string
    # list of upk objs
    # list of upk ids
    # list of pubkey strings
    # 'signed' dict field
    # nothing - requires 'signed' field within data
    # inputted signature works as single string with single pubKey/upk
    # or list of models when public_key == dict field

    # if passing public_key, be sure to include signature - targetData['signed'] is ok as sig - data likely does not contain 'sig'
    def print_dict_truncated(d, max_len=20):
        def trunc(x):
            s = str(x)
            return s if len(s) <= max_len else s[:max_len - 3] + "..."

        def build(d, indent=0):
            s = ''
            for key, value in d.items():
                prefix = '  ' * indent
                if isinstance(value, dict):
                    s += f"{prefix}{trunc(key)}:"
                    s += build(value, indent + 1)
                else:
                    s += f"{prefix}{trunc(key)}: {trunc(value)}"
            return s.strip()

        return build(d)
    try:

        if isinstance(data, str):
            prnt('0a')
            try:
                data = json.loads(data)
                # get_signing_data(data) often inputted. returns string. dict is required to remove sig
            except:
                try:
                    import ast
                    data = ast.literal_eval(data)
                except:
                    pass
        elif isinstance(data, models.Model):
            prnt('0b')
            # data = convert_to_dict(data)
            data = json.loads(get_signing_data(data))
        if isinstance(public_key, models.Model) and public_key._meta.object_name == 'UserPubKey':
            prnt('a1')
            target_keys = resolve_target_keys(data, signature)
            if target_keys is None or public_key.id in target_keys:
                public_key_data = {public_key.id:{'pubKey':public_key.publicKey}}
                if signature and isinstance(signature, str):
                    public_key_data[public_key.id]['signature'] = signature
            else:
                prnt('a1 - key not in target_keys')
                return False
        elif is_id(public_key):
            prnt('a2')
            from accounts.models import UserPubKey
            target_keys = resolve_target_keys(data, signature)
            if target_keys is not None and public_key not in target_keys:
                prnt('a2 - key not in target_keys')
                return False
            upk = UserPubKey.objects.filter(id=public_key).only('publicKey').first()
            if upk:
                prnt('has_upk')
                public_key_data = {public_key:{'pubKey':upk.publicKey}}
                if signature and isinstance(signature, str):
                    public_key_data[public_key]['signature'] = signature
        elif isinstance(public_key, str):
            prnt('a3')
            target_keys = resolve_target_keys(data, signature)
            upk_id = hash_upk_id(public_key)
            if target_keys is None or upk_id in target_keys:
                public_key_data = {upk_id:{'pubKey':public_key}}
                if signature and isinstance(signature, str):
                    public_key_data[upk_id]['signature'] = signature
            else:
                prnt('a3 - key not in target_keys')
                return False
        elif public_key and (isinstance(public_key, list) or isinstance(public_key, QuerySet)):
            prnt('a4')
            target_keys = resolve_target_keys(data, signature)

            if isinstance(public_key, list) and any(pk for pk in public_key if is_id(pk)):
                prnt('a4a')
                from accounts.models import UserPubKey
                upks = UserPubKey.objects.filter(id__in=public_key).only('id','publicKey')
                if not len(public_key) == upks.count():
                    prnt('upk cound fail 1')
                    return
                public_key_data = {upk.id:{'pubKey':upk.publicKey} for upk in upks if target_keys is None or upk.id in target_keys}
            elif isinstance(public_key, QuerySet) or isinstance(public_key, list) and any(pk for pk in public_key if isinstance(pk, models.Model)):
                prnt('a4b')
                public_key_data = {i.id:{'pubKey':i.publicKey} for i in public_key if target_keys is None or i.id in target_keys}
            else:
                prnt('a4c')
                public_key_data = {hash_upk_id(i):{'pubKey':i} for i in public_key if target_keys is None or hash_upk_id(i) in target_keys}
        elif not public_key or isinstance(public_key, dict):
            prnt('a5')
            if not public_key:
                public_key = data['signed']
            signed_field = public_key
            public_key_data = {}

            if not signed_field:
                prnt('empty signed field')
                return False

            last_dt = list(signed_field)[-1]

            def resolve_upk_chain(dt, entry_data, signed_field, upk_data):
                pk = entry_data['pk']
                if pk in upk_data:
                    return True  # already resolved via another path, avoid redundant work / cycles

                upk_data[pk] = {'dt': string_to_dt(dt)}
                if 'sig' in entry_data:
                    upk_data[pk]['sig'] = entry_data['sig']
                if 'publicKey' in entry_data:
                    upk_data[pk]['publicKey'] = entry_data['publicKey']

                if 'req' in entry_data:
                    for key, val in entry_data['req'].items():
                        if key not in signed_field:
                            prnt('req unresolved - missing key', key)
                            return False
                        ref_entry = signed_field[key]
                        ref_pk = ref_entry.get('pk')
                        if not ref_pk or ref_pk[:10] != val:
                            prnt('req unresolved - pk mismatch', key)
                            return False
                        if not resolve_upk_chain(key, ref_entry, signed_field, upk_data):
                            return False
                return True

            upk_data = {}
            if not resolve_upk_chain(last_dt, signed_field[last_dt], signed_field, upk_data):
                prnt('req chain fail')
                return False

            # should compare req data to signed_field to fetch full list of pk_ids

            if upk_bypass:
                for i in upk_data:
                    if 'publicKey' in upk_data[i]:
                        public_key_data[i] = {'pubKey':upk_data[i]['publicKey']}
                    if 'sig' in upk_data[i]:
                        public_key_data[i]['signature'] = upk_data[i]['sig']
            else:
                from accounts.models import UserPubKey
                upks = UserPubKey.objects.filter(id__in=[i for i in upk_data]).values('id','created','end_life_dt','publicKey')
                for upk in upks:
                    prnt('upk',upk)
                    if upk_data[upk['id']]['dt'] >= upk['created'] and (not upk['end_life_dt'] or upk_data[upk['id']]['dt'] <= upk['end_life_dt']):
                        public_key_data[upk['id']] = {'pubKey':upk['publicKey']}
                        if signature and (isinstance(signature, list) or isinstance(signature, QuerySet)):
                            for s in signature:
                                if has_field(s, 'Upk_obj') and s.Upk_obj == upk:
                                    public_key_data[upk['id']]['signature'] = s.sig
                        elif signature and isinstance(signature, str):
                            public_key_data[upk['id']]['signature'] = signature
                        elif 'sig' in upk_data[upk['id']]:
                            public_key_data[upk['id']]['signature'] = upk_data[upk['id']]['sig']

            prnt('public_key_data',print_dict_truncated(public_key_data))
            prnt('upk_data',upk_data)
            if len(public_key_data) != len(upk_data):
                prnt('upk count fail 2')
                return False
        else:
            prnt('a6')
        
        # prnt('b2')

        if isinstance(data, dict):
            prnt('p0')
            if skip_sort:
                sorted_data = data
            else:
                sorted_data = sort_for_sign(data)
            prnt('sorted_data',sorted_data)         
            if 'signed' in sorted_data:
                prnt('p1')
                if signature and isinstance(signature, dict):
                    sign_dict = signature
                elif 'signed' in data:
                    sign_dict = data['signed']
                adjusted_signed = {}

                for dt, sig_data in sign_dict.items():
                    prnt('dt',dt)
                    prnt('pk',str(sig_data['pk'])[:50])
                    prnt('sig_data',sig_data)
                    prnt('public_key_data',print_dict_truncated(public_key_data))

                    pk = sig_data['pk']
                    proceed = False
                    if pk in public_key_data:
                        prnt('aa')
                        proceed = True
                    elif signature and 'sig' in sig_data and sig_data['sig'] == signature:
                        proceed = True
                        prnt('ab')
                    elif 'publicKey' in sig_data and any(i for i in public_key_data if public_key_data[i] == sig_data['publicKey']):
                        proceed = True
                        prnt('ac')
                    prnt('proceed',proceed)
                    if not proceed:
                        return False
                    elif proceed:
                        def resolve_chain(dt, entry_data, sign_dict, snapshot):
                            if dt in snapshot:
                                return True  # already resolved via another path, avoid redundant work / cycles

                            snapshot[dt] = {'pk': entry_data['pk']}
                            if 'req' in entry_data:
                                snapshot[dt]['req'] = entry_data['req']
                                for key, val in entry_data['req'].items():
                                    if key not in sign_dict:
                                        prnt('req unresolved - missing key', key)
                                        return False
                                    ref_entry = sign_dict[key]
                                    ref_pk = ref_entry.get('pk')
                                    if not ref_pk or ref_pk[:10] != val:
                                        prnt('req unresolved - pk mismatch', key)
                                        return False
                                    if not resolve_chain(key, ref_entry, sign_dict, snapshot):
                                        return False
                            return True

                        snapshot = {}
                        if not resolve_chain(dt, sig_data, sign_dict, snapshot):
                            prnt('req chain resolution failed for', pk)
                            return False

                        snapshot = dict(sorted(snapshot.items(), key=lambda kv: kv[0]))  # earliest-first ordering

                        public_key_data[pk]['signed_snapshot'] = snapshot
                        # prnt('signed_snapshot', pk, snapshot)

                        if not public_key_data[pk].get('pubKey', None) and 'publicKey' in sig_data:
                            public_key_data[pk]['pubKey'] = sig_data['publicKey']

                        if not public_key_data[pk].get('signature', None):
                            if signature and (isinstance(signature, list) or isinstance(signature, QuerySet)):
                                for s in signature:
                                    if has_field(s, 'Upk_obj') and s.Upk_obj.id == pk:
                                        public_key_data[pk]['signature'] = s.sig
                            elif 'sig' in sig_data:
                                public_key_data[pk]['signature'] = sig_data['sig']
                            else:
                                from network.models import Signature
                                sig = Signature.objects.filter(Upk_obj__id=pk, pointerId=sorted_data['id'], DateTime=string_to_dt(dt)).only('sig').first()
                                if sig:
                                    public_key_data[pk]['signature'] = sig.sig
                        
            
            else:
                # data is simpleSign
                prnt('p6b',type(public_key_data))
                
            data = json.dumps(sorted_data, separators=(',', ':'))
        prnt('b3',type(data))

        if not isinstance(data, str):
            prnt('b3a')
            try:
                data = get_signing_data(data)
            except:
                pass
        # data is now the correctly-ordered JSON string, no suffix yet
        # base_payload = json.loads(data)
        prnt('public_key_data',print_dict_truncated(public_key_data))

        is_valid = False
        for upk_id, key_data in public_key_data.items():
            # prnt('VERIFY FOR:',upk_id)
            
            if not key_data.get('signature'):
                prnt('1 missing signature for', upk_id)
                return False
            s = 'ycF3atcq61TMBvVmGwrQWZJ69fu'
            try:
                if not isinstance(data, dict):
                    try:
                        data = json.loads(data)
                    except Exception as e:
                        import ast
                        data = ast.literal_eval(data)
                key_payload = dict(data)  # shallow copy - don't mutate base_payload
                if 'signed_snapshot' not in key_data:
                    prnt('2 missing snapshot for', upk_id)
                    return False
                key_payload['signed'] = key_data['signed_snapshot']
                prnt('signed_snapshot',print_dict_truncated(key_data['signed_snapshot']))
                key_data_str = json.dumps(key_payload, separators=(',', ':')) + s
            except Exception as e:
                prnt('signed_snapshot err5',str(e))
                key_data_str = str(data) + s
            prnt(f'-verifying...',upk_id, len(key_data_str), key_data_str)

            key_type = detect_security(key_data['pubKey'], key_type='pubkey')
            is_valid = simpleVerify(key_data_str, key_data['signature'], key_data['pubKey'], key_type=key_type)

            if not is_valid:
                return False

        return is_valid

    except Exception as e:
        prnt('VERIFY err4',str(e), 'code:',err)
    return False

# old - unused
def create_keys_ml_dsa_old(user_id, user_pass, security='ML_DSA_44'):
    import hashlib
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.backends import default_backend

    salt = hashlib.sha256(f"{user_id}:{user_pass}".encode()).digest()
    if len(user_pass) > 120:
        n = 65536
    else:
        n = 262144
    password = user_pass.encode()
    kdf = Scrypt(salt=salt, length=32, n=n, r=8, p=1, backend=default_backend())
    seed = kdf.derive(password)  # 32-byte seed (ξ)

    if security == 'ML_DSA_44':
        from dilithium_py.ml_dsa import ML_DSA_44  # NIST security level 2
        pk, sk = ML_DSA_44._keygen_internal(seed)
    elif security == 'ML_DSA_65':
        from dilithium_py.ml_dsa import ML_DSA_65  # NIST security level 3
        pk, sk = ML_DSA_65._keygen_internal(seed)
    else:
        from dilithium_py.ml_dsa import ML_DSA_87  # NIST security level 5
        pk, sk = ML_DSA_87._keygen_internal(seed)

    return sk.hex(), pk.hex()

def simpleSign_ml_dsa_old(secret_key_hex, data, security='ML_DSA_44'):
    sk = bytes.fromhex(secret_key_hex)
    message = (data).encode('utf-8')

    if security == 'ML_DSA_44':
        from dilithium_py.ml_dsa import ML_DSA_44
        signature = ML_DSA_44.sign(sk, message)
    elif security == 'ML_DSA_65':
        from dilithium_py.ml_dsa import ML_DSA_65
        signature = ML_DSA_65.sign(sk, message)
    else:
        from dilithium_py.ml_dsa import ML_DSA_87
        signature = ML_DSA_87.sign(sk, message)
    return signature.hex()

def simpleVerify_ml_dsa_old(data, signature_hex, public_key_hex, security='ML_DSA_44'):
    pk = bytes.fromhex(public_key_hex)
    sig = bytes.fromhex(signature_hex)
    message = (data).encode('utf-8')

    if security == 'ML_DSA_44':
        from dilithium_py.ml_dsa import ML_DSA_44
        return ML_DSA_44.verify(pk, message, sig)
    elif security == 'ML_DSA_65':
        from dilithium_py.ml_dsa import ML_DSA_65
        return ML_DSA_65.verify(pk, message, sig)
    else:
        from dilithium_py.ml_dsa import ML_DSA_87
        return ML_DSA_87.verify(pk, message, sig)

def detect_security_old(key_hex, key_type='privkey'):
    from utils.models import prnt
    SK_SIZES = {32: 'secp256k1', 2560: 'ML_DSA_44', 4032: 'ML_DSA_65', 4896: 'ML_DSA_87'}
    PK_SIZES = {65: 'secp256k1', 1312: 'ML_DSA_44', 1952: 'ML_DSA_65', 2592: 'ML_DSA_87'}
    byte_len = len(key_hex) // 2
    sizes = SK_SIZES if key_type == 'privkey' else PK_SIZES
    if key_type == 'pubkey' and byte_len == 65 and key_hex.startswith('04'):
        prnt('level','secp256k1','key_type',key_type)
        return 'secp256k1'
    level = sizes.get(byte_len)
    if not level:
        raise ValueError(f"Unknown {key_type} size: {byte_len} bytes")
    prnt('level',level,'key_type',key_type)
    return level
    

# critical utils

def dt_to_string(dt_input):
    if isinstance(dt_input, str):
        try:
            dt = datetime.datetime.fromisoformat(dt_input)
        except Exception as e:
            return dt_input
    elif isinstance(dt_input, datetime.datetime):
        dt = dt_input
    elif not dt_input:
        return ''
    else:
        raise TypeError("Input must be a datetime object or an ISO 8601 string")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    # Return JS-style ISO string (milliseconds precision, 'Z' suffix)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4] + "Z"

def sign_obj(item, operatorData=None, keys=None, do_save=True, req_sigs=None, key_type=None, signing_dt=None, return_error=False):
    try:
        # from blockchain.models import 
        from accounts.models import User
        from .models import get_operator_obj, logError, now_utc, has_field, has_method, testing, get_model, prnt, hash_upk_id, string_to_dt, get_sigData, is_locked, declare_var
        from django.db import models
        err = 'A'
        if is_locked(item):
            if return_error:
                return item, 'err0'
            return item
        if has_method(item, 'get_hash_to_id') and item.id != hash_obj_id(item) or isinstance(item, models.Model) and item.id == None:
            prnt('failSign4958', item)
            # logError('item.id != hash_obj_id', code='4958', func='sign_obj', extra={'item.id':item.id, 'correct_id':hash_obj_id(item), 'hash_obj_id_data':hash_obj_id(item, return_data=True), 'dict':str(convert_to_dict(item))[:500]})
            if return_error:
                return item, 'err1'
            return item
        
        # operatorData = get_operatorData(operatorData)
        if not keys:
            keys = get_operator_obj('keyPair', operatorData=operatorData)
        err += 'E'
        if keys:
            err += 'F'
            if has_field(item, 'func') and item.func and item.func.lower() == 'super':
                err += 'G'
                if do_save and testing() and User.objects.all().count() <= 2:
                    pass
                else:
                    user = User.objects.filter(id=get_operator_obj('userId', operatorData=operatorData)).first()
                    if not user.assess_super_status():
                        if return_error:
                            return item, 'err2'
                        return item
            err += 'H'
            prnt('signging with keys:',keys['pubKey'])
            prnt('keys',keys)
            signing_dt = dt_to_string(declare_var(signing_dt, now_utc()))

            def bump_dt_string(dt_str):
                from datetime import timedelta
                dt = string_to_dt(dt_str)
                dt = dt + timedelta(milliseconds=10)  # smallest representable increment at hundredths precision
                return dt_to_string(dt)

            # signing_dt = dt_to_string(now_utc())
            # if 'keyId' in keys:
            #     prnt('a1')
            #     pkey = keys['keyId']
            # else:
            #     prnt('a2')
            pkey = hash_upk_id(keys['pubKey'])
            try:
                if isinstance(item, dict):
                    prev_pk = get_sigData(item['signed'])['pk'] # should check all sign history, not just latest as is happening here
                else:
                    prev_pk = get_sigData(item.signed)['pk']
                if prev_pk != pkey:
                    from accounts.models import UserPubKey
                    prev_upk = UserPubKey.objects.filter(id=prev_pk).values('publicKey').first()
                    if prev_upk and len(prev_upk['publicKey']) > len(keys['pubKey']):
                        prnt('*previously signed by stronger key*', prev_upk)
                        return item
            except Exception as e:
                prnt('error checking previous signature', e)
            err += 'B'
            
            if isinstance(item, dict):
                current_sig_data = item.get('signed', {})
            else:
                current_sig_data = item.signed
            new_sig_data = {}
            new_pk = {'pk': pkey}
            if not req_sigs:
                err += 'E'
                if has_field(item, 'latestVer'):
                    item.modlVer = item.latestVer
                err += 'C'
                if has_field(item, 'lastUpdate'):
                    item.lastUpdate = string_to_dt(signing_dt)
                err += 'D'
            elif req_sigs == 'current':
                err += 'G'
                while signing_dt in current_sig_data:
                    signing_dt = bump_dt_string(signing_dt)
                new_pk['req'] = {}
                for dt, sig_data in current_sig_data.items():
                    new_sig_data[dt] = {'pk': sig_data['pk']}
                    if 'req' in sig_data:
                        new_sig_data[dt]['req'] = sig_data['req']
                    new_pk['req'][dt] = sig_data['pk'][:10]
            elif isinstance(req_sigs, list):
                err += 'H'
                while signing_dt in current_sig_data:
                    signing_dt = bump_dt_string(signing_dt)
                new_pk['req'] = {}
                for dt, sig_data in current_sig_data.items():
                    if sig_data['pk'] in req_sigs:
                        new_sig_data[dt] = {'pk': sig_data['pk']}
                        if 'req' in sig_data:
                            new_sig_data[dt]['req'] = sig_data['req']
                        new_pk['req'][dt] = sig_data['pk'][:10]
            elif req_sigs == 'restore':
                restore_sigs = current_sig_data

            err += 'I'
            new_sig_data[signing_dt] = new_pk
            if isinstance(item, dict):
                item['signed'] = new_sig_data
            else:
                item.signed = new_sig_data

            err += 'J'
            sig = simpleSign(keys['privKey'], get_signing_data(item), key_type=key_type)
            err += 'K'
            prnt('sig:',str(sig)[:100])
            if req_sigs == 'restore':
                for dt, sig_data in restore_sigs.items():
                    if dt != signing_dt:
                        if isinstance(item, dict):
                            item['signed'][dt] = sig_data
                        else:
                            item.signed[dt] = sig_data
            elif req_sigs == 'current': # added this to match javascript version which always needs all sigs added, may not be needed here
                for dt, sig_data in current_sig_data.items():
                    if dt != signing_dt:
                        if isinstance(item, dict):
                            if 'sig' in sig_data:
                                item['signed'][dt]['sig'] = sig_data['sig']
                            if 'publicKey' in sig_data:
                                item['signed'][dt]['publicKey'] = sig_data['publicKey']

            if isinstance(item, dict):
                item['signed'][signing_dt]['sig'] = sig
            else:
                prnt('signed:',item.signed)
                err += 'L'
                from network.models import Signature
                from django.contrib.contenttypes.models import ContentType
                sig_obj = Signature(pointerId=item.id, pointerKey=ContentType.objects.get_for_model(item), Upk_obj_id=pkey, sig=sig, DateTime=string_to_dt(signing_dt))
                sig_obj.save()
                if do_save:
                    item.save()
            err += 'M'
            # prntn('signed:',get_signing_data(item))
        elif do_save and testing() and User.objects.all().count() <= 2:
            err += 'N'
            prnt('bypass sign')
            super(get_model(item._meta.object_name), item).save()
    except Exception as e:
        w = str(e)
        prnt('fail sign 472549',now_utc(),w,'err',err,convert_to_dict(item))
        # logError(str(e), code='7532', func='sign_obj', extra={'dict':str(convert_to_dict(item))[:500]})
        if err[-1] == 'J':
            try:
                get_signing_data(item, print_data=True)
            except Exception as e:
                prnt('err x1234',now_utc(),w)
        if return_error:
            return item, w
    if return_error:
        return item, None
    return item

def get_commit_data(target, extra_data=None):
    from .models import get_dynamic_model, get_model, has_method, has_field, sigData_to_hash, dt_to_string, prnt, prntDebug
    from django.db import models
    from decimal import Decimal
    # prntDebug('-get_commit_data',target)
    if isinstance(target, str):
        obj_id = target
        obj = get_dynamic_model(target, id=target)
        is_model = True
    elif isinstance(target, dict):
        obj_id = target['id']
        obj_data = target
        model = get_model(obj_data['objType'])
        obj = model()
        is_model = False
    else:
        is_model = True
        obj = target
        obj_id = obj.id
    to_commit = {}
    if has_method(obj, 'commit_data'):
        # field_names = [f.name for f in obj._meta.get_fields()]
        for i in obj.commit_data():
            try:
                if i == 'hash':
                    to_commit[i] = sigData_to_hash(obj)
                else:
                    # prnt(i)
                    if has_field(obj, i, exclude_method=True):
                    # if i in field_names:
                        # prnt('p1')
                        if is_model:
                            attr = getattr(obj, i)
                        else:
                            attr = obj_data[i]
                            if i == 'signed':
                                attr = {}
                                # remove 'sig' and 'publicKey'
                                for k, v in attr.items():
                                    attr[k] = {'pk':v['pk']}
                        if isinstance(attr, datetime.datetime):
                            to_commit[i] = dt_to_string(attr)
                        elif isinstance(attr, Decimal):
                            to_commit[i] = str(attr)
                        elif i.endswith('_obj') and attr and isinstance(attr, models.Model):
                            to_commit[i] = attr.id
                        else:
                            to_commit[i] = attr
                        # prnt('p1 attr',attr)
                    elif has_method(obj, i):
                        # prnt('p2')
                        if extra_data != None:
                            resp = getattr(obj, i)(extra_data)
                        else:
                            resp = getattr(obj, i)()
                        if resp:
                            for key, value in resp.items():
                                to_commit[key] = value
                        # prnt('p2 resp',resp)
            except Exception as e:
                prnt('fail get_commit_data 5092', str(e), obj_id, i)
                to_commit[i] = str(e)
    if has_field(obj, 'proposed_modification') or has_field(obj, 'is_modifiable'):
        to_commit['modifiable'] = True
        if 'created' not in to_commit:
            if is_model:
                crtd = dt_to_string(obj.created)
            else:
                crtd = obj_data['created']
            to_commit['created'] = crtd
    if not to_commit:
        to_commit['hash'] = sigData_to_hash(obj)
    # prnt('result:',to_commit)
    return to_commit
    # return json.dumps(to_commit)

def check_commit_data(target, data, return_err=False, return_obj=False):
    from decimal import Decimal
    from utils.models import get_dynamic_model, value_is_none, has_method, sigData_to_hash, prnt, has_field, string_to_dt, get_or_create_model, logEvent
    prnt('-check_commit_data',type(target),target,data)
    # from blockchain.models import 
    err = 0
    try:
        data = json.loads(data)
    except:
        pass
    err = 1
    if isinstance(target, str):
        obj_id = target
        obj = get_dynamic_model(target, id=target)
        is_model = True
        xxxx = obj
    elif isinstance(target, dict):
        obj_id = target['id']
        obj_data = target
        obj = get_or_create_model(target['objType'], id=target['id'])
        # model = get_model(obj_data['objType'])
        # obj = model()
        is_model = False
        xxxx = obj_data
    else:
        is_model = True
        obj = target
        obj_id = obj.id
        xxxx = obj
    required = None
    success = False
    if is_model:
        if not has_method(obj, 'get_hash_to_id'):
            success = True
        elif hash_obj_id(obj) == obj.id:
            success = True
    else:
        if not has_method(obj, 'get_hash_to_id'):
            success = True
        elif hash_obj_id(obj_data, model=obj) == obj_id:
            success = True
    if not success:
        err = 12
        prnt(' check_commit fail1',obj_id)
        prnt(f'xxxx- {str(convert_to_dict(xxxx, withold_fields=False))[:1700]}')
        if return_err:
            logEvent(f'check_commit_error1:{obj_id}', log_type='Errors')
    elif 'modifiable' in data and data['modifiable']:
        if is_model:
            target_created = string_to_dt(obj.created)
        else:
            target_created = string_to_dt(obj_data['created'])
        prnt('target_created',target_created)
        prnt("string_to_dt(data['created'])",string_to_dt(data['created']))
        if string_to_dt(data['created']) == target_created:
            success = True
        else:
            err = 8
            success = False
            prnt(' check_commit fail8',obj_id)
            prnt(f'xxxx- {str(convert_to_dict(xxxx, withold_fields=False))[:700]}')
            if return_err:
                logEvent(f'check_commit_error2:{obj_id}', log_type='Errors')
    elif 'hash' in data:
        if is_model:
            sigHash = sigData_to_hash(obj)
        else:
            sigHash = sigData_to_hash(obj_data)
        if data['hash'] == sigHash:
            success = True
        else:
            err = 13
            success = False
            prnt(' check_commit fail2',obj_id)
            prnt(f'xxxx- {str(convert_to_dict(xxxx, withold_fields=False))[:1700]}')
            if return_err:
                logEvent(f'check_commit_error3:{obj_id}', log_type='Errors')

    elif 'genesis' in data and data['genesis'] == obj_id:
        success = True
    if success and has_method(obj, 'commit_data'):
        for i in obj.commit_data():
            if i != 'hash':
                if has_field(obj, i, exclude_method=True):
                    if is_model:
                        attr = getattr(obj, i)
                        if isinstance(attr, datetime.datetime):
                            attr = dt_to_string(attr)
                        elif isinstance(attr, Decimal):
                            attr = str(attr)
                        elif i.endswith('_obj') and attr:
                            attr = attr.id
                    else:
                        attr = obj_data[i]
                        if i == 'signed':
                            attr = {}
                            # remove 'sig' and 'publicKey'
                            for k, v in attr.items():
                                attr[k] = {'pk':v['pk']}
                    if i == 'signed':
                        new_sig_data = {}
                        for dt, sig_data in attr.items():
                            new_sig_data[dt] = {'pk': sig_data['pk']}
                            if 'req' in sig_data:
                                new_sig_data[dt]['req'] = sig_data['req']
                                        
                        attr = new_sig_data
                    if i not in data:
                        success = False
                        err = 5
                        prnt('check_commit fail5','f',obj_id,i,str(i),str(data))
                        prnt(f'xxxx- {str(convert_to_dict(xxxx, withold_fields=False))[:700]}')
                        if return_err:
                            logEvent(f'check_commit_error5: f,{obj_id}, {i},{str(data[i])},{str(attr)}', log_type='Errors')
                    elif value_is_none(data[i]) and value_is_none(attr):
                        err = 6
                        pass
                    elif str(data[i]) != str(attr):
                        success = False
                        err = 7
                        prnt('check_commit fail6','f',obj_id,i,str(data[i]),str(attr))
                        prnt(f'xxxx- {str(convert_to_dict(xxxx, withold_fields=False))[:700]}')
                        if return_err:
                            logEvent(f'check_commit_error6: f,{obj_id}, {i},{str(data[i]) if i in data else "x"},{str(attr)}', log_type='Errors')
                        # break
                elif has_method(obj, i):
                    # prnt('method')
                    resp = getattr(obj, i)(check_data=data)
                    prnt('resp',resp)
                    if not resp:
                        success = False
                        err = 8
                        prnt(f'check_commit fail7 f {obj_id},{i},{str(data[i]) if i in data else "x"}')
                        prnt(f'xxxx- {str(convert_to_dict(xxxx, withold_fields=False))[:700]}')
                        if return_err:
                            logEvent(f'check_commit_error7: f,{obj_id}, {i},{str(data[i]) if i in data else "x"}', log_type='Errors')

    # prntDebug('check_commit_data-result:',success)
    if return_obj:
        if is_model:
            return success, obj
        else:
            return success, None
    if return_err:
        return success, err
    return success

def convert_to_dict(obj, broadcast=False, withold_fields=True, exclude=None, full_pk=False, include_sig=True): 
    from utils.models import prntDebug, prnt
    # prntDebug('--convert_to_dict')
    if not obj:
        return None
    from django.db.models import Model
    from utils.models import get_dynamic_model, has_field, has_method, string_to_dt
    from network.models import Signature
    from accounts.models import UserPubKey
    if not isinstance(obj, Model):
        prnt('not model', obj)
        return obj
    do_not_share_fields = ['validated','enacted','notes','val_err','user_permissions','groups','password']
    if broadcast: # doesnt seem to be used
        new_dict = {'objType':obj._meta.object_name}
        if has_field(obj, 'latestVer'):
            new_dict['latestVer'] = obj.latestVer
        fields = obj._meta.fields
        for f in fields:
            if f.name not in do_not_share_fields:
                value = getattr(obj, f.name)
                if value:
                    if isinstance(value, datetime.datetime):
                        new_dict[f.name] = dt_to_string(value)
                    # elif isinstance(value, bytes):
                    #     new_dict[f.name] = value.decode('utf-8')
                    else:
                        new_dict[f.name] = value
        if has_field(obj, 'signed'):
            new_sig_data = {}
            for dt, sig_data in obj.signed.items():
                new_sig_data[dt] = {'pk': sig_data['pk']}
                if 'req' in sig_data:
                    new_sig_data[dt]['req'] = sig_data['req']
                if include_sig:
                    if full_pk or obj._meta.object_name in ['User','UserPubKey']:
                        upk = UserPubKey.objects.filter(id=sig_data['pk']).only('publicKey').first()
                        if upk:
                            new_sig_data[dt]['publicKey'] = upk.publicKey
                    sig = Signature.objects.filter(Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt), pointerId=obj.id).only('sig').first()
                    if sig:
                        new_sig_data[dt]['sig'] = sig.sig
            new_dict['signed'] = new_sig_data
    else:
        d1 = {'objType':obj._meta.object_name}
        if has_field(obj, 'latestVer'):
            d1['latestVer'] = obj.latestVer
        from decimal import Decimal
        from django.forms.models import model_to_dict
        d2 = {**d1, **model_to_dict(obj)}
        # prnt('d2',d2)
        if has_method(obj, 'get_version_fields'):
            fields = obj.get_version_fields()
        else:
            fields = d2
        data = {}
        for key, value in fields.items():
            # prnt('key',key, 'value',value)
            if key == 'imageField':
                from django.conf import settings
                from pathlib import Path
                try:
                    path = Path(settings.MEDIA_ROOT) / d2['file_path']
                    with path.open("rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    data[key] = b64
                except Exception as e:
                    prnt('convert_to_dict imageField error', e)

            else:
                if key in d2:
                    data[key] = d2[key]
                else:
                    data[key] = value
                if isinstance(data[key], bytes):
                    # prnt('size',len(data[key]))
                    if key in ['publicKey','sig']:
                        data[key] = bytes_to_base64url(data[key])
                    else:
                        from utils.models import to_base62
                        data[key] = to_base62(data[key])
        # prnt('next stage')
        if 'signed' in data:
            new_sig_data = {}
            for dt, sig_data in data['signed'].items():
                # prnt('dt',dt)
                # prnt('sig_data',sig_data)
                new_sig_data[dt] = {'pk': sig_data['pk']}
                if 'req' in sig_data:
                    new_sig_data[dt]['req'] = sig_data['req']
                # prnt('include_sig',include_sig)
                if include_sig:
                    if full_pk or data['objType'] in ['User','UserPubKey']:
                        # prnt('q1')
                        upk = UserPubKey.objects.filter(id=sig_data['pk']).only('publicKey').first()
                        # prnt('q2')
                        if upk:
                            # prnt('upk',upk.publicKey)
                            new_sig_data[dt]['publicKey'] = upk.publicKey
                    # prnt('q3')
                    sig = Signature.objects.filter(Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt), pointerId=data['id']).only('sig').first()
                    # prnt('q4',sig)
                    if sig:
                        new_sig_data[dt]['sig'] = sig.sig
                    # prnt('q5')
            # prnt('new_sig_data',new_sig_data)
            data['signed'] = new_sig_data
        # prnt('next stage 2')
        for key, value in data.items():
            if isinstance(value, datetime.datetime):
                data[key] = dt_to_string(value)
            elif isinstance(value, Decimal):
                data[key] = str(value)

        if withold_fields:
            for f in do_not_share_fields:
                if f in data:
                    del data[f]
        if exclude:
            for f in exclude:
                if f in data:
                    del data[f]
    # prntDebug('--convert_to_dict new_dict',str(data))
    return data

def get_signing_data(obj, extra_data=None, include_sig=False, full_pk=False, sort_data=True, exclude_fields=None, return_dict=False, print_data=False):
    # WARNING changes here could break ALL signing and verifying abilities
    
    if not obj:
        return obj
    from django.db import models
    from utils.models import get_model, has_method, prnt, prntDebug, string_to_dt
    prnt('--get_signing_data',str(obj)[:150],'exclude_fields',exclude_fields)
    data = {}
    model = None
    include_sign_fields = []
    skip_fields = skip_sign_fields.copy()
    if exclude_fields:
        skip_fields += exclude_fields
    if isinstance(obj, models.Model):
        if has_method(obj, 'no_sign_fields'):
            no_sign_fields = obj.no_sign_fields()
            skip_fields += no_sign_fields
        if has_method(obj, 'yes_sign_fields'):
            include_sign_fields = obj.yes_sign_fields()
        # prnt('include_sign_fields1', include_sign_fields)
        objDict = convert_to_dict(obj, include_sig=include_sig, full_pk=full_pk)
        for key, value in objDict.items():
            # if include_sig and key == 'signed':
            #     data[key] = objDict[key]
            if key not in skip_fields or key in include_sign_fields:
                data[key] = objDict[key]
        if sort_data:
            data = sort_for_sign(data, print_data=print_data)
        json_dump = json.dumps(data, separators=(',', ':'))
        if print_data:
            prnt('json_dump1', json_dump, '\n')
        if return_dict:
            return data
        return json_dump
    else:
        try: # obj may or not be json object
            objDict = json.loads(obj)
        except:
            objDict = obj
        fields = objDict
        if 'id' in objDict:
            # prnt("objDict['id']",objDict['id'])
            model = get_model(objDict['id'])
            # prnt('model',model)
            if has_method(model, 'get_version_fields'):
                fields = model().get_version_fields(version=objDict['modlVer'])
        if model and has_method(model(), 'no_sign_fields'):
            no_sign_fields = model().no_sign_fields(version=objDict['modlVer'])
            skip_fields += no_sign_fields
        if model and has_method(model(), 'yes_sign_fields'):
            include_sign_fields = model().yes_sign_fields(version=objDict['modlVer'])
        # prnt('include_sign_fields2', include_sign_fields)

        if include_sig:
            ...
        for key, value in fields.items():
            if key not in skip_fields or key in include_sign_fields:
                data[key] = objDict[key]

        if 'signed' in data:
            from network.models import Signature
            from accounts.models import UserPubKey
            new_sig_data = {}
            for dt, sig_data in data['signed'].items():
                new_sig_data[dt] = {'pk': sig_data['pk']}
                if 'req' in sig_data:
                    new_sig_data[dt]['req'] = sig_data['req']
                if include_sig:
                    if 'publicKey' in sig_data:
                        new_sig_data[dt]['publicKey'] = sig_data['publicKey']
                    elif data['objType'] in ['User','UserPubKey']:
                        upk = UserPubKey.objects.filter(id=sig_data['pk']).only('publicKey').first()
                        if upk:
                            new_sig_data[dt]['publicKey'] = upk.publicKey
                    if 'sig' in sig_data:
                        new_sig_data[dt]['sig'] = sig_data['sig']
                    else:
                        sig = Signature.objects.filter(Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt), pointerId=data['id']).only('sig').first()
                        if sig:
                            new_sig_data[dt]['sig'] = sig.sig
            data['signed'] = new_sig_data
    if sort_data:
        data = sort_for_sign(data, print_data=print_data)
    # for k in data:
    #     prnt('data2', k)
    json_dump = json.dumps(data, separators=(',', ':'))
    if print_data:
        prnt('json_dump2', json_dump, '\n')
    if return_dict:
        return data
    return json_dump

def sign_for_sending(sending_data, operatorData=None, keys=None):
    from utils.models import now_utc, get_operator_obj, prnt
    sending_data['dt'] = dt_to_string(now_utc())
    if not keys:
        keys = get_operator_obj('keyPair', operatorData=operatorData)
    sending_data['pubKey'] = keys['pubKey']
    if 'senderId' not in sending_data:
        sending_data['senderId'] = get_operator_obj('self_nodeId')
    hashed = hashlib.md5(str(sort_for_sign(sending_data)).encode('utf-8')).hexdigest()
    sig = simpleSign(keys['privKey'], hashed)
    sending_data['hashed'] = hashed
    sending_data['signed'] = sig
    return sending_data


# this var is very relevant to is_id()
# does not include prefix
# ID_LENGTH of 25 = upto 35 chars 
# ID_LENGTH of 10 = over 13 chars
ID_LENGTH = 14
def generate_id(data=None, length=ID_LENGTH):
    if data is not None:
        import hashlib
        if not isinstance(data, str):
            data = str(data)
        data = data.encode()
        digest = hashlib.sha256(data).digest()
        truncated = digest[:length]
    else:
        import uuid
        truncated =  uuid.uuid4().bytes[:length]
    from utils.models import to_base62
    s = to_base62(truncated)
    return s

def hash_obj_id(obj, verify=False, specific_data=None, return_data=False, model=None, version=None, length=ID_LENGTH, print_data=False):
    from utils.models import has_method, has_field, get_model_prefix, get_model, prnt, value_is_none, rgetattr
    # prnt('-hash_obj_id', obj)
    # prnt(convert_to_dict(obj))
    if not length:
        length = ID_LENGTH
    if specific_data:
        return get_model_prefix(obj) + 'So' + generate_id(specific_data, length=length)
    from django.db.models import Model
    data = {}
    err = 0
    try:
        if isinstance(obj, Model):
            err = 1
            if has_field(obj, 'iden_length'):
                # len = obj.iden_length
                length = obj.get_version_fields(version=version)['iden_length']
            if has_method(obj, 'get_hash_to_id'):
                err = 2
                d2 = convert_to_dict(obj)
                for i in obj.get_hash_to_id(version=version):
                    if '.' in i:
                        attr = rgetattr(obj, i)
                        data[i] = attr
                    elif i in d2:
                        data[i] = d2[i]
                    else:
                        if '_obj' in i:
                            attr = getattr(obj, i+'_id')
                        else:
                            attr = getattr(obj, i)
                        if isinstance(attr, datetime.datetime):
                            attr = dt_to_string(attr)
                        data[i] = attr
                err = 3
                if has_field(obj,'proposed_modification'):
                    mod = getattr(obj, 'proposed_modification')
                    if mod:
                        data['proposed_modification'] = mod
                if print_data:         
                    prnt('dat',err, str(data))
                
                err = 4
                data = sort_for_sign(data)
                if return_data:
                    return data
                if obj._meta.object_name == 'Region' and obj.Name == 'Earth':
                    from network.models import _EarthChain_genesisId
                    return _EarthChain_genesisId
                return get_model_prefix(obj) + 'So' + generate_id(data, length=length)
            elif verify:
                return None
            else:
                return get_model_prefix(obj) + 'So' + generate_id(length=length)
        elif isinstance(obj, str) and verify == False:
            err = 10
            if not model:
                model = get_model(obj)
            return get_model_prefix(model) + 'So' + generate_id(length=length)
        else:
            err = 100
            try:
                obj = json.loads(obj)
            except:
                pass
            if not model:
                if 'objType' in obj:
                    model = get_model(obj['objType'])()
                elif 'id' in obj:
                    model = get_model(obj['id'])()
            if model:
                if not version:
                    version = int(obj['modlVer'])
                err = 101
                if has_field(model, 'iden_length'):
                    # len = model.iden_length
                    length = model.get_version_fields(version=version)['iden_length']

                if has_method(model, 'get_hash_to_id'):
                    err = 102
                    for i in model.get_hash_to_id(version=version):
                        if i.endswith('_obj'):
                            c = i + '_id'
                            if c in obj:
                                i = c
                        if '.' in i:
                            a = i.find('.')
                            fk_type = i[:a].replace('_obj','')
                            from utils.models import get_dynamic_model, request_items
                            fk = get_dynamic_model(fk_type, id=obj[i[:a]])
                            if not fk:
                                returned_objs = request_items(requested_items=[obj[i[:a]]], return_updated_objs=True, return_updated_ids=False, return_missing=False, check_consensus=True, downstream_worker=False, get_missing_blocks=False, override_completed=True)
                                prnt('returned_objs',returned_objs)
                                for z in returned_objs:
                                    if z.id == obj[i[:a]]:
                                        fk = z
                            field = getattr(fk, i[a+1:])
                            data[i] = field
                        elif i in obj:
                            data[i] = obj[i]
                        else:
                            prnt('hash_obj_id error 389573',i)
                    if has_field(model,'proposed_modification'):
                        if 'proposed_modification' in obj and not value_is_none(obj['proposed_modification']):
                            mod = obj['proposed_modification']
                        else:
                            mod = None
                        if mod:
                            data['proposed_modification'] = mod
                    if print_data:
                        prnt('dat2',err, str(data))
                    data = sort_for_sign(data)
                    if return_data:
                        return data
                    if model._meta.object_name == 'Region' and obj['Name'] == 'Earth':
                        from network.models import _EarthChain_genesisId
                        return _EarthChain_genesisId
                    return get_model_prefix(model) + 'So' + generate_id(data, length=length)
                elif verify:
                    return None
                else:
                    return get_model_prefix(model) + 'So' + generate_id(length=length)
    except Exception as e:
        prnt(f'hash-id-fail49204-{err}',obj,str(e),'data:',data)
    # prnt('err',err)
    return None

def sort_for_sign(data, print_data=False, none_is_string=True):
    from utils.models import is_dt_string, prnt
    # prntDebug('-sort_for_sign','type:',type(data), str(data))

    def stringify_bool(val):
        if val is True or val is False:
            return str(val)
        if val is None and none_is_string:
            return "Val:N"
        return val

    def process_value(val):
        if isinstance(val, dict):
            return sort_for_sign(val, print_data)
        elif isinstance(val, list):
            if not val:
                return "Val:N"
            return [process_value(v) for v in val]
        elif isinstance(val, str) and is_dt_string(val):
            return dt_to_string(val)
        else:
            return stringify_bool(val)



    if isinstance(data, dict):
        data = {k: process_value(v) for k, v in data.items()}
        sorted_items = sorted(data.items(), key=lambda item: item[0].lower())
        sorted_dict = dict(sorted_items)
        id_val = {}
        # pkey_val = {}
        sign_val = {}
        if 'id' in sorted_dict:
            id_val = {'id': sorted_dict.pop('id')}
        # if 'pkey' in sorted_dict:
        #     pkey_val = {'pkey': sorted_dict.pop('pkey')}
        if 'signed' in sorted_dict:
            sign_val = {'signed': sorted_dict.pop('signed')}
        return {**id_val, **sorted_dict, **sign_val}

    elif isinstance(data, list):
        if not data:
            return "Val:N"
        return [process_value(v) for v in data]

    return stringify_bool(data)


_super_id = None

def super_id(iden=None, net=None):
    from utils.models import prntDev, prnt, prntDebug
    prnt('-super_id()',iden)
    global _super_id
    if _super_id is None:
        from network.models import Sonet
        sonet = Sonet.objects.first()
        prntDebug('sonet',sonet)
        if not sonet and net:
            sonet = net
        if sonet:
            if isinstance(sonet, dict):
                net_iden = sonet['id']
                net_created_dt = sonet['created']
            else:
                net_iden = sonet.id
                net_created_dt = sonet.created
            if net_iden == 'ohSohVQmm16CME0miSmsKW8':
                # _super_id = 'usrSo7vmfyZc7GoAq4ky8skiiif'
                _super_id = 'usrSo1KOSJaVhV6s4m84QcKg8x'
                prntDebug('_super_id1',_super_id)
            elif net_created_dt:
                prntDebug('sonet.created',net_created_dt)
                if net and isinstance(net_created_dt, str):
                    c_dt = net_created_dt
                else:
                    c_dt = dt_to_string(net_created_dt)
                _super_id = 'usrSo' + generate_id(f'SuperSo-{c_dt}',length=14)
                prntDebug('_super_id2',_super_id)
        elif iden:
            return True
        
    prnt('_super_id',_super_id)
    if iden:
        return True if _super_id == iden else False
    return _super_id


# default fields here, model specific fields within each model - may be issue in node manager
skip_sign_fields = [
        'validated','is_active','pkey_hash',
        'password','keyword_array','hash','fcm_capable','ai_capable',
        'coins','last_login','Block_obj','pos','password',
        'suspended_dt','expelled_dt','isVerified','validations','prevVersion',
        'groups','user_permissions','updated_on_node',
        'Validator_obj','new','date_created','Update_obj',
        'is_superuser','is_staff','display_hour','latestVer','enacted',
        'SenderBlock_obj','ReceiverBlock_obj','notes','activeNode',
        'is_modifiable','BillText_obj',
        'queued_dt','plugin_prefix','iden_length','value','added_to_node',
        # 'networkChain','commitChain','blockchainId',
        ]




def new_test_key():
    # pip install cryptography
    from utils.models import prnt
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


    # pip install ecdsa
    # from ecdsa import NIST521p
    # ORDER_N = NIST521p.order

    CURVE = ec.SECP521R1()
    # ORDER_N = 0x01FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFA51868783BF2F966B7FCC0148F709A5D03BB5C9B8899C47AEBB6FB71E91386409
    ORDER_N = 0x01fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffa51868783bf2f966b7fcc0148f709a5d03bb5c9b8899c47aebb6fb71e91386409
    SCALAR_BYTES = 66  # 521-bit curve -> 66-byte fixed-width fields

    def derive_private_scalar(seed_string: str, salt: bytes = b"", info: bytes = b"ecdsa-p521-key") -> int:
        hkdf = HKDF(
            algorithm=hashes.SHA512(),
            length=SCALAR_BYTES + 8,   # oversize to make mod-bias negligible
            salt=salt,
            info=info,
        )
        okm = hkdf.derive(seed_string.encode("utf-8"))
        scalar = int.from_bytes(okm, "big") % ORDER_N
        if scalar == 0:
            scalar = 1
        return scalar

    def keypair_from_string(seed_string: str):
        scalar = derive_private_scalar(seed_string)
        priv_key = ec.derive_private_key(scalar, CURVE)
        return priv_key

    def sign_message(priv_key, message: bytes) -> bytes:
        # cryptography hashes `message` with SHA-512 internally, then signs -> DER-encoded (r, s)
        return priv_key.sign(message, ec.ECDSA(hashes.SHA512()))

    def verify_message(pub_key, message: bytes, signature_der: bytes) -> bool:
        try:
            pub_key.verify(signature_der, message, ec.ECDSA(hashes.SHA512()))
            return True
        except Exception:
            return False




    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature, decode_dss_signature

    FIELD_BYTES = 66  # P-521

    def raw_to_der(sig_raw: bytes) -> bytes:
        assert len(sig_raw) == FIELD_BYTES * 2
        r = int.from_bytes(sig_raw[:FIELD_BYTES], "big")
        s = int.from_bytes(sig_raw[FIELD_BYTES:], "big")
        return encode_dss_signature(r, s)

    def der_to_raw(sig_der: bytes) -> bytes:
        r, s = decode_dss_signature(sig_der)
        return r.to_bytes(FIELD_BYTES, "big") + s.to_bytes(FIELD_BYTES, "big")

    def sign_message_raw(priv_key, message: bytes) -> bytes:
        der = priv_key.sign(message, ec.ECDSA(hashes.SHA512()))
        return der_to_raw(der)

    def verify_message_raw(pub_key, message: bytes, sig_raw: bytes) -> bool:
        try:
            pub_key.verify(raw_to_der(sig_raw), message, ec.ECDSA(hashes.SHA512()))
            return True
        except Exception:
            return False

    # if __name__ == "__main__":
    seed = "correct horse battery staple"
    message = b"hello cross-language ecdsa"

#     priv = keypair_from_string(seed)
#     pub = priv.public_key()

#     pub_hex = pub.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint).hex()
#     prnt("Public key (uncompressed hex):", pub_hex)

#     sig = sign_message(priv, message)
#     prnt("Signature (DER hex):", sig.hex())


#     prnt("Verified:", verify_message(pub, message, sig))

#     sig = sign_message_raw(priv, message)
#     prnt("Signature raw (DER hex):", sig.hex())
#     prnt("Verifiedraw:", verify_message_raw(pub, message, sig))

#     s = '006b73d8a3133bc67df90fde97b58eb2e4c2ecb9cd1a7c6f0511299882c856645ed29806a2f36853e481b29fedd52b1338308a2aadc6abd1a653002e9d5286b4530400d643876868e989eca39f8fd0d8221a1d528ddf8e0cea991185133cdc0bcc07a2375cfc346fff0dc1911f7203412c806e7b7ad9622e3574e7873f7d3bef60067365'
#     prnt("Verified2:", verify_message_raw(pub, message, s))
#     sig_raw = bytes.fromhex(s)
#     # verify_message_raw(pub, message, sig_raw)
#     prnt("Verified23:", verify_message_raw(pub, message, sig_raw))

# #     '040146276675f949117af17dc3fad32a1c3160d03a8544a3cbb8384c8bdd9b19a5a48f9db8c23aafba6f5d6343b3a74c90e5bf619a096e59e058184364d1e47b8be511007afd49cc2708b66f5249673527e286ed45eeb638eff5cee6948056b95d0eed99cf9adad2b55abc0ac0414739b7aff8bbd7efeb1aa7f707f8c797b14ad7bf8cbe92'
# #     ~:Public key (uncompressed hex):,040146276675f949117af17dc3fad32a1c3160d03a8544a3cbb8384c8bdd9b19a5a48f9db8c23aafba6f5d6343b3a74c90e5bf619a096e59e058184364d1e47b8be511007afd49cc2708b66f5249673527e286ed45eeb638eff5cee6948056b95d0eed99cf9adad2b55abc0ac0414739b7aff8bbd7efeb1aa7f707f8c797b14ad7bf8cbe92
# # ~:Signature (DER hex):,30818702411b3fda521482c5200e0d9b5f8b4a65b07b36f87cf846e7dcadc0e548321a02f15c4216dade8ac7583767e3c38b48b27f85db3ca0b44c41fcfc216c89ddfe34f93e024201a811603d60b5c842e3d976da90c2f26bb8914ab7ca43a5365aac06464a77833b5a9068fbb0b59fc22bc24bcb124f98b98a4aa8b7a648e3010f00172d53a80eaefc
# # ~:Verified:,True

#     import hashlib
#     msg_hash = hashlib.sha512(message).digest()
#     prnt("msg_hash hex:", msg_hash.hex())

#     sig = sign_message(priv, message)
#     from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
#     r, s = decode_dss_signature(sig)
#     prnt("r:", hex(r))
#     prnt("s:", hex(s))
#     prnt("sig DER hex:", sig.hex())

    passw = 'fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffa51868783bf2f966b7fcc0148f709a5d03bb5c9b8899c47aebb6fb71e91386409'
    data = 'sign_me'
    keys = create_keys('1234', passw, 'key_type', key_strength='P521')
    s = 'ycF3atcq61TMBvVmGwrQWZJ69fu'
    sig = simpleSign(keys[0], data, key_type='P521')
    prnt('sig',sig)
    is_valid = simpleVerify(data+s, sig, keys[1], key_type='P521')
    prnt('is_valid',is_valid)


    prnt()
    # keys = create_keys_p521('1234', 'key_type'+passw)
    sig = simpleSign_P521(keys[0], data+s)
    prnt('sig2',sig)
    is_valid = simpleVerify_P521(data+s, sig, keys[1])
    prnt('is_valid2',is_valid)

    sg = 'AXkUSlmUOWaCsRbeCS05tS0KAmQ1XMPUblr2SWyr6QRgLLQHmNdDZWp1NtYx39Dd5XtENOvOaLIael_4qreXlZUzAc5enkeGjWyNlxCz6Nei6xRZ7ViKQMq6pO6vTzPaqSRJG3CokqR_gowzcqq2Is3iHvXK-mINySENjpDNhUfUjvax'

    is_valid = simpleVerify(data+s, sg, keys[1], key_type='P521')
    prnt('is_valid3',is_valid)


