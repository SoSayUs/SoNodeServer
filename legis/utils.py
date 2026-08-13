from django.db import models
import datetime
from unidecode import unidecode
import re
from utils.models import prnt, get_operator_obj, now_utc, round_time

def for_commitment(obj, genesis_obj, block):
    ...
    return True
    

def for_validation(obj):
    ...
    return True

def get_region(Name, modelType='country'):
    from posts.models import Region
    return Region.supported_objects.filter(nameType__iexact=modelType, Name=Name).order_by('created').first()

def get_gov(country, gv_lvl='Federal', **kwargs):
    prnt('-get_gov',country,gv_lvl, kwargs)
    from legis.models import Government
    gov = None
    if country and isinstance(country, models.Model):
        if kwargs:
            kwargs['proposed_modification'] = None
            kwargs.setdefault('Country_obj', country)
            kwargs.setdefault('gov_level', gv_lvl)
            gov = Government.objects.filter(**kwargs).order_by('-GovernmentNumber','-SessionNumber','proposed_modification','-created').first()
        else:
            gov = Government.objects.filter(Country_obj=country, gov_level=gv_lvl, proposed_modification=None).order_by('-GovernmentNumber','-SessionNumber','proposed_modification','-created').first()
    if not gov and kwargs:
        from utils.models import create_dynamic_model
        gov = create_dynamic_model('Government', **kwargs)
    prnt('returned gov',gov,gov.id)
    return gov

def modify_gov(gov, items):
    prnt('-modify_gov',gov.id, items)
    for item in items:
        for field, value in item.items():
            if not isinstance(value, list):
                value = [value]
            for val in value:
                if field == 'Office_array':
                    if not gov.Office_array or val not in gov.Office_array:
                        if not gov.Validator_obj or not gov.Validator_obj.is_valid:
                            gov.add_office(val)
                        else:
                            gov = gov.propose_modification()
                            gov.add_office(val)
                elif field == 'Chamber_array':
                    if not gov.Chamber_array or val not in gov.Chamber_array:
                        if not gov.Validator_obj or not gov.Validator_obj.is_valid:
                            gov.add_chamber(val)
                        else:
                            gov = gov.propose_modification()
                            gov.add_chamber(val)
                elif field == 'menuItem_array':
                    if not gov.menuItem_array or val not in gov.menuItem_array:
                        if not gov.Validator_obj or not gov.Validator_obj.is_valid:
                            gov.add_menu_item(val)
                        else:
                            gov = gov.propose_modification()
                            gov.add_menu_item(val)
    return gov

def add_gov_menu_item(gov, item, log):
    prnt('-add_gov_menu_item',gov,item)
    if not gov.menuItem_array or item not in gov.menuItem_array:
        if not gov.signed:
            gov.add_menu_item(item)
        else:
            if not modded_gov:
                modded_gov = gov.propose_modification()
            modded_gov.add_menu_item(item)
            log.updateShare(modded_gov)
    else:
        log.updateShare(gov)
    return log


def remove_accents(input_str):
    import unicodedata
    normalized_str = unicodedata.normalize('NFD', input_str)
    filtered_str = ''.join(
        char for char in normalized_str 
        if unicodedata.category(char) != 'Mn'
    )
    return unicodedata.normalize('NFC', filtered_str)


def summarize_meetings(special=None, post=None, dt=None, max_mins=45):
    prnt('--summarize_meetings', post)
    func = 'summarize_meetings'
    region = None
    gov = None
    log = None
    start_time = now_utc()
    self_nodeId = get_operator_obj('self_nodeId')
    
    from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
    from utils.models import finishScript, create_share_object, prntn, declare_var
    from posts.models import Spren
    dt = now_utc()

    if post:
        meeting = post.Pointer_obj
        prnt('meeting',meeting)
        region = meeting.Region_obj
        gov = meeting.Government_obj
        
        if post.Update_obj:
            all_jobs = []
            topics = post.Update_obj.data['Terms']
            for topic in topics:
                for key, value in topic.items():
                    prntn('topic',key,'count:',value, now_utc())
                    if value > 1:
                        all_jobs.append(key)

            def run_job(key):
                prnt('run_job',key,now_utc())
                if not Spren.objects.filter(pointerId=meeting.id, type='Meeting_topic', re=key, Validator_obj__is_valid=True).exists():
                    spren = summarize_topic(meeting, key, self_nodeId)
                    if spren:
                        return spren

            results = []
            end_time = dt + datetime.timedelta(minutes=max_mins)

            with ThreadPoolExecutor(max_workers=1) as executor:
                futures = [executor.submit(run_job, job) for job in all_jobs]
                while futures:
                    timeout = (end_time - now_utc()).total_seconds()
                    if timeout <= 0:
                        prnt('breaking for time', now_utc() - dt)
                        break

                    done, futures = wait(futures, timeout=timeout, return_when=FIRST_COMPLETED)
                    for future in done:
                        try:
                            spren = future.result()
                            if spren:
                                if not log:
                                    log = create_share_object(func, region, special=special, dt=dt)
                                log.updateShare(spren)
                            prnt(f"Got result: {spren}")
                        except Exception as e:
                            prnt(f"Job failed: {e}")

                # Cancel anything that didn't start yet
                for f in futures:
                    f.cancel()

            if not log:
                log = create_share_object(func, region, special=special, dt=dt)
            spren = summarize_meeting(meeting, self_nodeId)
            log.updateShare(spren)
        if log:
            prnt('done summarize_meetings', now_utc() - start_time)
            return finishScript(log, gov, special)
    prnt('none run')
    return

def summarize_meeting(meeting, self_nodeId=None):
    import time
    from utils.models import run_prompt, get_token_count
    prnt('-summarize_meeting',meeting)
    if not self_nodeId:
        self_nodeId = get_operator_obj('self_nodeId')
    from posts.models import Spren
    spren = Spren.objects.filter(pointerId=meeting.id, type='Meeting', pointerType='Meeting').first()
    if not spren:
        spren = Spren(pointerId=meeting.id, type='Meeting', pointerType='Meeting', CreatorNode_obj_id=self_nodeId, Region_obj=meeting.Region_obj)
        spren.DateTime = meeting.DateTime
        spren.data = {}
    elif spren and spren.data:
        if spren.CreatorNode_obj.id == self_nodeId and not spren.Validator_obj:
            if spren.created >= round_time(now_utc(), amount='hour') - datetime.timedelta(hours=1):
                return None
            return spren
        elif spren.Validator_obj and spren.Validator_obj.is_valid:
            return None
        
    text = ''
    for s in Spren.objects.filter(pointerId=meeting.id, type='Meeting_topic'):
        if 'items' in s.data:
            for topic, summary in s.data['items'].items():
                text += f'Topic:{topic}, Summary:{summary}\n'
    if not text:
        from legis.models import Statement
        for s in Statement.objects.filter(Meeting_obj=meeting):
            text += f'Speaker:{s.PersonName}, Statement:{s.Content}\n'
    # text = remove_tags(html)
    token_count = get_token_count(text)
    prnt('tokens:',token_count)
    prompt = f'Briefly summarize the following text in bullet form with "\n" linebreaks, do not say anything other than the summary: {text}'
    prnt()
    r = run_prompt(prompt)
    spren.data['summary'] = r.replace("\n-", "\n\n-")
    spren.save()
    return spren

def summarize_topic(obj, topic, self_nodeId=None):
    import time
    from utils.models import run_prompt, get_token_count
    prnt('-summarize_topic',topic)
    if not self_nodeId:
        self_nodeId = get_operator_obj('self_nodeId')
    
    if obj._meta.object_name == 'Meeting':
        search = [str(topic)]
        from posts.models import Post
        from django.db.models import Q
        posts = Post.all_objects.filter(Statement_obj__Meeting_obj=obj).filter(Q(Statement_obj__SubjectOfBusiness__icontains=topic)|Q(Statement_obj__Terms_array__overlap=search)|Q(Statement_obj__keyword_array__overlap=search)).order_by('Statement_obj__order','DateTime')
        post_count = posts.count()
        prnt('posts.count()',posts.count())
    from posts.models import Spren
    spren = Spren.objects.filter(pointerId=obj.id, re=topic, type='Meeting_topic').first()
    if not spren:
        spren = Spren(pointerId=obj.id, re=topic, type='Meeting_topic', CreatorNode_obj_id=self_nodeId, Region_obj=obj.Region_obj)
        spren.DateTime = obj.DateTime
    elif spren and spren.data:
        if spren.CreatorNode_obj.id == self_nodeId and not spren.Validator_obj:
            if spren.created >= round_time(now_utc(), amount='hour') - datetime.timedelta(hours=2):
                return None
            return spren
        elif spren.Validator_obj and spren.Validator_obj.is_valid:
            return None
        
    prnt('-------------')
    start_time = datetime.datetime.now()
    
    def get_prompt(data, topic, num):
        if num == 1:
            return f"the following is a snippet from a congressional debate: {data} \n|END| choose the most informative and contextual post regarding the topic '{topic}', then return the post_id of that post. Do not say anything besides the post_id."
        elif num == 2:
            return f"Read the following text: {data} \n|END| Very briefly present the most important points from the preceeding text to an audience in bullet form, do not go over 2 bullets, do not say anything besides the bullet points, do not say 'Here are the two bullet points'"
        elif num == 3:
            return f"Summarize the following in paragraph form: {data}"
    
    n = 0
    m = 0
    total_tokens = 0
    idenList = []

    def run(posts, n, post_count, rounded, promptPosition):
        # max_tokens = 3500
        max_tokens = 7000
        prnt('n',n, 'post_count',post_count,'rounded',rounded)
        num_tokens, text = makeText(posts[n:n+rounded])
        if len(text) < 200 and promptPosition == 1:
            return None, n+1, post_count
        if num_tokens < 1000:
            try:
                while num_tokens < 1000 and rounded <= (post_count/3):
                    rounded += 2
                    num_tokens, text = makeText(posts[n:n+rounded])
                    if num_tokens > max_tokens:
                        while num_tokens > max_tokens and rounded > 1:
                            rounded -= 1
                            num_tokens, text = makeText(posts[n:n+rounded])
                            if num_tokens < 1000:
                                num_tokens = 1000
            except:
                pass
            if rounded > 1:
                prompt = get_prompt(text, topic, promptPosition)
                result = run_prompt(prompt)
            else:
                if isinstance(posts[n+rounded], int) or isinstance(posts[n+rounded], str):
                    result = "xpp%sqqx" %(posts[n+rounded])
                else:
                    result = "xpp%sqqx" %(posts[n+rounded].Statement_obj.id)
        elif num_tokens < max_tokens:
            if rounded > 1:
                prompt = get_prompt(text, topic, promptPosition)
                result = run_prompt(prompt)
            else:
                if isinstance(posts[n+rounded], int) or isinstance(posts[n+rounded], str):
                    result = "xpp%sqqx" %(posts[n+rounded])
                else:
                    result = "xpp%sqqx" %(posts[n+rounded].Statement_obj.id)
        else:
            while num_tokens >= max_tokens and rounded > 1:
                if rounded > 3:
                    rounded -= 2
                else:
                    rounded -= 1
                prnt('roundedn, n', rounded, n)
                prnt(len(posts))

                num_tokens, text = makeText(posts[n:n+rounded])
            if num_tokens > max_tokens:
                prnt()
                prnt('num_tokens >',max_tokens)
                q = 0
                while num_tokens > max_tokens + 500:
                    q += 10
                    text = text[:-q]
                    num_tokens = get_token_count(text, "cl100k_base")
                    prnt('q', q)
                    prnt('num_toeksn', num_tokens)
            if promptPosition == 2:
                prompt = get_prompt(text, topic, promptPosition)
                num_tokens = get_token_count(prompt, "cl100k_base")
                prnt('prompt tokens', num_tokens)
                result = run_prompt(prompt)
            else:
                prnt('len(posts)',len(posts))
                prnt(f'{posts}[{n}+{rounded}]')
                if isinstance(posts[n+rounded], int) or isinstance(posts[n+rounded], str):
                    result = "xpp%sqqx" %(posts[n+rounded])
                else:
                    result = "xpp%sqqx" %(posts[n+rounded].Statement_obj.id)
        n += rounded
        if promptPosition == 1:
            x = result.find('xpp')+3
            q = result.find('qqx')
            try:
                selectedPost = result[x:q]
            except Exception as e:
                prnt('err 765123 x:',x,'q:',q,'err:',str(e))
                selectedPost = 99999999999
            prnt(result)
            prnt(n, '/', rounded)
            prnt('------result', str(selectedPost))
            return selectedPost, n, post_count
        else:
            return result, n, post_count
    
    if post_count > 7:
        rounded = 7
        if post_count < 35:
            rounded = round(post_count/7)
        prnt('post count', post_count)
        while n < post_count:
            m += 1
            prnt('cycle:', m)
            
            try:
                selectedPost, n, post_count = run(posts, n, post_count, rounded, 1)
                if selectedPost:
                    idenList.append(selectedPost)
            except Exception as e:
                prnt('err 5321',str(e))
                n += 1
    else:
        for i in posts:
            idenList.append(i.Statement_obj.id)

    prnt('total tokens', total_tokens)
    prnt('-----next1', datetime.datetime.now() - start_time)
    total = len(idenList)
    prnt(total)
    if total > 7:
        rounded = round(total / 7)
        def run2(idenList, total):
            prnt('---run2')
            returnList = []
            n = 0
            while n < total:
                prnt('n:', n, 'total:', total)
                try:
                    selectedPost, n, total = run(idenList, n, total, rounded, 1)
                    if selectedPost:
                        returnList.append(selectedPost)
                except Exception as e:
                    prnt('err 07452',str(e))
                    n += 1
            return returnList
        
        returnList = run2(idenList, total)
        if len(returnList) > 7:
            while len(returnList) > 7:
                nextList1 = []
                for x in returnList:
                    nextList1.append(x)
                returnList = run2(nextList1, len(returnList))
        idenList = returnList

    prnt('-----next2', datetime.datetime.now() - start_time)

    summary = ""
    idenList = sorted(idenList)
    prnt('idenList',idenList)
    if spren.data and 'items' in spren.data:
        items = spren.data['items']
    else:
        items = {}
    for i in idenList:
        prnt('i1',i)
        try:
            result, n, post_count = run([i], 0, 1, 7, 2)
            if 'Sure' in result or 'Here' in result:
                if "Sure" in result:
                    k = result.find('Sure')
                elif "Here" in result:
                    k = result.find('Here')
                try:
                    l = result[k:].find('\n')
                    sure = result[:k+l+1]
                    prnt(sure)
                    result = result.replace(sure,'').replace('\n\n', '\n')
                except:
                    pass
            result = result.replace("- Overview of the text's content\n- Key takeaways: Importance and main themes", "")
            summary = summary + '\n' + result.strip() + '\n---'
            items[i] = result.strip()
        except Exception as e:
            prnt('yikes', str(e))
            time.sleep(2)

    if items:
        if not spren.data:
            spren.data = {}
        spren.data['items'] = items
        spren.save()
    prnt('----summary----')
    prnt(summary)
    prnt('-----')
    prnt('done summarizer', datetime.datetime.now() - start_time)
    prnt(spren)
    return spren

def makeText(data):
    prnt('-makeText',len(data))
    def remove_tags(text):
        try:
            TAG_RE = re.compile(r'<[^>]+>')
            text = TAG_RE.sub('', text).replace('"', "'").replace('\n', '').strip()
            text = ''.join(text.splitlines())
            text = unidecode(text)
            return text
        except Exception as e:
            prnt('err 9802',str(e))
            return ''
    def textualize(statement, text):
        if statement.PersonName:
            person_name = statement.PersonName
        else:
            person_name = ''
            if statement.Person_obj:
                name = statement.Person_obj.get_name()
                if name and not any(char.isdigit() for char in name):
                    person_name = name
                
        text = text + '[post_id:xpp%sqqx]%s:\n%s\n\n' %(statement.id, person_name, statement.Content)
        return text
    text = ""

    from legis.models import Statement
    from utils.models import get_token_count, is_id
    for i in data:
        if is_id(i):
            s = Statement.objects.filter(id=i).first()
            if s and len(s.Content) > 100:
                text = textualize(s, text)
        elif isinstance(i, models.Model) and i._meta.object_name == 'Post':
            if i.Statement_obj and len(i.Statement_obj.Content) > 100:
                text = textualize(i.Statement_obj, text)
        elif isinstance(i, models.Model) and i._meta.object_name == 'Statement':
            if len(i.Content) > 100:
                text = textualize(i, text)
    text = remove_tags(text)
    num_tokens = get_token_count(text)
    prnt('-----num_tokens',num_tokens)
    return num_tokens, text


def summarize_bills(special=None, region_id=None, dt=None, max_mins=45, task=1):
    prnt('--summarize_bills', region_id)
    func = 'summarize_bills'
    region = None
    gov = None
    dp = None
    start_time = now_utc()
    self_nodeId = get_operator_obj('self_nodeId')

    from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
    from utils.models import finishScript, create_share_object, prntn, declare_var
    from posts.models import Post, Spren
    from .models import BillText, Bill, Government
    dt = declare_var(dt, start_time)

    if region_id:
        spren_pointers = Spren.objects.filter(Region_obj__id=region_id, type='Billtext').values('pointerId').order_by('-created')[:1000]
        prnt('spren_pointers',len(spren_pointers))
        btexts = BillText.objects.filter(Region_obj__id=region_id, Validator_obj__is_valid=True, created__gt=start_time-datetime.timedelta(days=7)).exclude(id__in=[s['pointerId'] for s in spren_pointers]).values('id').distinct('pointerId').order_by('pointerId','created')[:5]
        prnt('btexts',btexts.count())

        def run_job(btext_id):
            prnt('-run_job',now_utc())
            btext = BillText.objects.filter(id=btext_id).first()
            return summarize_bill(btext, self_nodeId=self_nodeId)
        
        all_jobs = [b['id'] for b in btexts]
        end_time = dt + datetime.timedelta(minutes=max_mins)

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(run_job, job) for job in all_jobs]
            while futures:
                timeout = (end_time - now_utc()).total_seconds()
                prnt('timeout',timeout)
                if timeout <= 0:
                    prnt('breaking for time', now_utc() - dt)
                    break

                done, futures = wait(futures, timeout=timeout, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        spren = future.result()
                        prnt('returned spren:',spren)
                        if spren:
                            if not dp:
                                bill = Bill.objects.filter(id=spren.re).first()
                                if bill:
                                    if not region:
                                        region = bill.Region_obj
                                    if not gov:
                                        gov = bill.Government_obj
                                    if not gov and region:
                                        gov = Government.objects.filter(Region_obj=region, Validator_obj__is_valid=True).first()
                                    prnt('gov',gov,'region',region)
                                bill = None
                                if gov and region:
                                    dp = create_share_object(func, region, special=special, dt=dt, task=task)

                            if dp:
                                dp.updateShare(spren)

                        prnt(f"Got result: {spren}",dp,now_utc())
                    except Exception as e:
                        prnt(f"Job failed: {e}")

            # Cancel anything that didn't start yet
            for f in futures:
                f.cancel()
                
        if dp:
            timeout = (end_time - now_utc()).total_seconds()
            prnt('timeout',timeout)
            if timeout > 0 and BillText.objects.filter(Region_obj__id=region_id, Validator_obj__is_valid=True, created__gt=start_time-datetime.timedelta(days=7)).exclude(id__in=[s['pointerId'] for s in spren_pointers] + [b['id'] for b in btexts]).values('id').distinct('pointerId').exists():
                prnt('next round',task+1)
                from utils.models import create_job
                create_job(summarize_bills, job_timeout=3000, worker='low', clear_chrome_job=False, region_id=region_id, dt=dt, max_mins=max_mins, task=task+1)

            prnt('done summarize_bills', now_utc() - start_time)
            return finishScript(dp, gov, special)
    prnt('none run')
    return

def summarize_bill(billText, self_nodeId=None):
    start = now_utc()
    prnt('-summarize_bill',start)
    from posts.models import Spren
    if not self_nodeId:
        self_nodeId = get_operator_obj('self_nodeId')
    spren = Spren.objects.filter(pointerId=billText.id, re=billText.pointerId, type='Billtext').first()
    if not spren:
        spren = Spren(pointerId=billText.id, re=billText.pointerId, type='Billtext', pointerType='Bill', CreatorNode_obj_id=self_nodeId, Region_obj=billText.Region_obj)
        spren.DateTime = billText.created
    elif spren and spren.data:
        if spren.CreatorNode_obj.id == self_nodeId and not spren.Validator_obj:
            return spren
        elif spren.Validator_obj and spren.Validator_obj.is_valid:
            return None
    
    from utils.models import remove_tags, run_prompt, get_token_count
    if not spren.data:
        spren.data = {}
    if 'bullets' not in spren.data:
        spren.data['bullets'] = {}
    prev = 0
    section_title = 'init'
    section_code = '0'
    html = billText.data['TextHtml']
    for i in billText.data['TextNav']:
        for a, b in i.items():
            prnt('now:',now_utc(),'start:',start)
            prnt(a)
            prnt(b['html'])
            x = html[prev:].find(b['html'])
            prnt('x',x)
            if 'bullets' in spren.data and section_title in spren.data['bullets']:
                pass
            else:
                section = remove_tags(html[prev:prev+x])
                if section:
                    prompt = f'Very briefly summarize the following text in point form, do not say anything other than representing the main points detailed in this text, do not go over 4 points unless the text is very long: {section}'
                    r = run_prompt(prompt)
                    spren.data['bullets'][section_title] = {'code':section_code,'data':r}
                    spren.save()
                section_title = a
                section_code = b['code']
                x += len(b['html'])
                prev += x
                prnt()
            
    prnt('final:',prev)
    if prev != 0:
        
        section = remove_tags(html[prev:])
        if section:
            prompt = f'Very briefly summarize the following text in point form, do not say anything other than representing the main points detailed in this text, do not go over 4 points unless the text is very long: {section}'
            r = run_prompt(prompt)
            spren.data['bullets'][section_title] = {'code':section_code,'data':r}
            spren.save()
        prnt()

    prnt('-----finally:')
    for i, v in spren.data['bullets'].items():
        prnt(i)
        prnt(v)
        prnt('')

    text = remove_tags(html)
    token_count = get_token_count(text)
    prnt('tokens:',token_count)
    if token_count > 7000:
        text = ''
        for key, value in spren.data['bullets'].items():
            text += f"{value['data']}\n"
    prompt = f'Briefly summarize the purpose of the following bill, do not say anything other than the summary: {text}'
    prnt()
    r = run_prompt(prompt)
    spren.data['status'] = r
    spren.save()
    return spren

def verify_bill_spren(spren):
    from utils.models import remove_tags, run_prompt, get_token_count
    from .models import BillText
    from network.models import Validator
    from utils.locked import get_node_assignment
    billText = BillText.objects.filter(id=spren.pointerId).first()
    
    is_valid = True
    scrapers, validators = get_node_assignment(chainId=spren.Region_obj.id, func='summarize_bills', dt=spren.created, nodeType='intelligence')
    if spren.CreatorNode_obj.id not in scrapers:
        is_valid = False
    validator = Validator.objects.filter(jobId=spren.id, func='verify_bill_spren').order_by('created').first()
    if validator and validator.CreatorNode_obj.id not in validators:
        validator = None
    if not validator:
        validator = Validator(jobId=spren.id, CreatorNode_obj_id=get_operator_obj('self_nodeId'), func='verify_bill_spren', created=round_time(now_utc(), amount='hour'))

        if 'bullets' in spren.data:
            for bullet in spren.data['bullets'].values():
                if not is_valid:
                    break
                data = bullet['data']
                code = bullet['code']
                prnt()
                prnt('code',code)
                prnt('tokens:',get_token_count(data))
                prnt('data',data)

                html = billText.data['TextHtml']
                prev = 0
                
                for i in billText.data['TextNav']:
                    if not is_valid:
                        break
                    for a, b in i.items():
                        x = html[prev:].find(b['html'])
                        if b['code'] == code:
                            section = remove_tags(html[prev:prev+x])
                            if section:

                                prompt = f'Answer yes/no only, does this summary seem a reasonable summary of the following text. Summary: {data}. Text: {section}'
                                r = run_prompt(prompt, tkns_plus=900)
                                prnt('RESPONSE:',r)
                                if 'yes' in r.lower():
                                    ...
                                else:
                                    is_valid = False
                                    break
                                    
                        x += len(b['html'])
                        prev += x
        validator.is_valid = is_valid
        validator.save()



def get_scraperScripts(gov=None, region=None, gov_level=''):
    prnt('-get_scraperScripts',gov,region)
    model_type = None
    if gov:
        region = gov.Region_obj
        region_name = region.Name
        gov_level = gov.gov_level
        model_type = region.nameType.lower()
    elif region:
        if isinstance(region, models.Model):
            region_name = region.Name
            model_type = region.nameType.lower()
        elif isinstance(region, dict):
            region_name = region['Name']
            model_type = region['nameType'].lower()
    prnt('region',region)
    if region and model_type and model_type == 'country':
        country_name = region_name.lower()
        importScript = f'legis.generators.{country_name}.{gov_level.lower()}'
    elif region and model_type and model_type == 'provState':
        provState_name = region_name.lower()
        if isinstance(region, dict):
            from posts.models import Region
            par_region = Region.objects.filter(id=region['ParentRegion_obj'], Validator_obj__is_valid=True).first()
            country_name = par_region.Name.lower()
        else:
            country_name = region.ParentRegion_obj.Name.lower()
        importScript = f'legis.generators.{country_name}.{provState_name}.{gov_level.lower()}'
    elif region and model_type and model_type == 'city':
        name = region_name.lower()
        if isinstance(region, dict):
            from posts.models import Region
            provState = Region.objects.filter(id=region['ParentRegion_obj'], Validator_obj__is_valid=True).first()
            provState_name = provState.Name.lower()
            country_name = provState.ParentRegion_obj.Name.lower()
        else:
            provState_name = region.ParentRegion_obj.Name.lower()
            country_name = region.ParentRegion_obj.ParentRegion_obj.Name.lower()
        importScript = f'legis.generators.{country_name}.{provState_name}.{name}'
    # else:
    #     logError('err', code='5423', func='get_scraperScripts', extra={'gov':gov,'region':region})
    
    import importlib
    scraperScripts = importlib.import_module(importScript) 
    return scraperScripts

def get_scrape_duty(gov=None, receivedDt=None, region=None, gov_level=None, debate_obj=None, func=None):
    # requires either gov or region AND gov_level 
    prnt('--get scrape duty',gov,receivedDt,region,gov_level)
    from utils.locked import get_node_assignment
    import pytz

    if gov:
        region = gov.Region_obj
        region_id = region.id
        to_zone = pytz.timezone(region.timezone)
        scraperScripts = get_scraperScripts(gov)
    elif region and gov_level:
        if isinstance(region, models.Model):
            region_id = region.id
            tz = region.timezone
        elif isinstance(region, dict):
            region_id = region['id']
            tz = region['timezone']
        to_zone = pytz.timezone(tz)
        scraperScripts = get_scraperScripts(region=region, gov_level=gov_level)
    else:
        prnt('missing req input')
        # logEvent('missing gov or region and gov_level', code='86432', func='get_scrape_duty', log_type='Errors')
        return [], {}

    local_dt = receivedDt.astimezone(to_zone)
    today = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    dayOfWeek = today.weekday()
    prnt('receivedDt converted to region',local_dt)
    runTimes = scraperScripts.runTimes
    function_set = scraperScripts.functions
    approved_models = scraperScripts.approved_models
    function_list = []
    
    for function_dt, functions in dict(sorted(function_set.items(), key=lambda x: datetime.datetime.strptime(x[0], "%Y-%m-%d"), reverse=True)).items():
        if datetime.datetime.strptime(function_dt, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc) <= receivedDt:
            for function in functions:
                prnt('function:',function)
                runtime_window = [local_dt.hour]
                prnt('runtime_window',runtime_window)
                # prntDebug("function['hour']",function['hour'])
                if 'x' in function['hour'] or any(i in function['hour'] for i in runtime_window):
                    if 'x' in function['dayOfWeek'] or dayOfWeek in function['dayOfWeek']:
                        if 'x' in function['date'] or today in function['date']:
                            for f in function['cmds']:
                                if not func or func == f:
                                    function_list.append({'region_id':region_id,'function_name':f, 'function':getattr(scraperScripts, f), 'timeout':runTimes[f]})
            break

    # prnt('function_list',function_list)
    master_list = []
    for f in function_list:
        scrapers, validators = get_node_assignment(chainId=region_id, func=f['function_name'], dt=receivedDt, nodeType='maintainer')
        # get_scraping_order(chainId=region_id, func_name=f['function_name'], dt=receivedDt)
        f['scraping_order'] = scrapers
        f['validators'] = validators
        master_list.append(f)
    prnt('master_list',master_list)
    return master_list, approved_models                 
            

def run_assigned_duties(receivedDt=None, result=None):
    # runs every hour
    prnt('\n---run_script_duty',receivedDt)
    from network.models import EventLog, Tidy, intelligence_funcs
    from posts.models import Post
    from utils.locked import get_node_assignment, hash_obj_id
    from utils.models import get_self_node, dt_to_string, create_job, round_time
    import random
    import django_rq

    self_node = get_self_node()

    if not receivedDt:
        receivedDt = round_time(dt=now_utc(), dir='down', amount='hour')
    if receivedDt.minute < 10 and receivedDt.hour in [9, 11, 20]:
        # also check for User objs without valid UPK and vice versa, maybe less often
        queue = django_rq.get_queue('low')
        queue.enqueue(Tidy()._add_all_jobs, dt=receivedDt, job_timeout=60, result_ttl=7200)
                    
    # return
    if receivedDt.minute < 10:
        # if a user is assigned new nodes those nodes need to catch up the users activity such as wallet blocks not in node database, likely certain nodes will be chosen to scan the user list and alert each node of any changes
        import hashlib
        def shuffle_list(seed_input, lst):
            seed_hash = hashlib.sha256(seed_input.encode('utf-8')).hexdigest()
            seed_int = int(seed_hash, 16)
            rng = random.Random(seed_int)
            rng.shuffle(lst)
            return lst

        # if 'maintainer' in self_node.node_type:
        govPosts = list(Post.objects.filter(pointerType='Government', Region_obj__is_supported=True, Region_obj__id__in=self_node.region_array, validated=True).exclude(Update_obj__data__has_key='EndDate').distinct('Region_obj__id').order_by('Region_obj__id','-DateTime'))
        
        seed_input = f"govPosts_{dt_to_string(receivedDt)}"
        prnt('seed_input',seed_input)
        govPosts = shuffle_list(seed_input, govPosts)
        
        prnt('govPosts',govPosts)
        for post in govPosts:
            gov = post.get_pointer()
            scraper_list, approved_models = get_scrape_duty(gov, receivedDt)

            seed_input = f"{post.pointerId}_{dt_to_string(receivedDt)}"
            scraper_list = shuffle_list(seed_input, scraper_list)
            for i in scraper_list:
                if self_node.id in i['scraping_order']:
                    if result:
                        result['scrape assignment'].append(f'{gov.Region_obj.Name} {i["function_name"]}')

                    create_job(i['function'], job_timeout=i['timeout'], worker='low', clear_chrome_job=True, dt=receivedDt)
                
                job_id = hash_obj_id('DataPacket', specific_data=f"{dt_to_string(round_time(dt=receivedDt, dir='down', amount='hour'))}{i['function_name']}{gov.Region_obj.id}")
                if self_node.id in i['scraping_order'] + [i['validators'][0]]:
                    for node_id in i['scraping_order']:
                        if node_id != self_node.id:
                            log = EventLog(
                                jobId=job_id, 
                                created=round_time(dt=receivedDt, dir='down', amount='hour'),
                                Node_obj_id=node_id,
                                func=f'assigned_job:{i["function_name"]}',
                                type='job_tracker',
                                Region_obj=gov.Region_obj
                                )
                            log.save()

        job_assigned = False
        max_mins = 35

        from posts.models import Post, Spren, Region
        seed_input = f"intelligence_{dt_to_string(receivedDt)}"
        prnt('seed_input',seed_input)
        regions = shuffle_list(seed_input, list(Region.objects.filter(is_supported=True).values('id','networkChain')))
        supported_regions = {i['id']:i['networkChain'] for i in regions}

        for job in intelligence_funcs:
            prnt('job',job)
            if job_assigned:
                break
            else:
                if job == 'summarize_meetings':
                    from legis.utils import summarize_meetings
                    meetings = Post.objects.filter(pointerType='Meeting', validated=True, created__gt=receivedDt - datetime.timedelta(days=10), networkChain__in=self_node.chain_array).exclude(Update_obj=None).order_by('-created')
                    for meeting_post in meetings:
                        if not Spren.objects.filter(pointerId=meeting_post.pointerId, pointerType='Meeting', Validator_obj__is_valid=True).exists():
                            scrapers, validators = get_node_assignment(chainId=meeting_post.Region_obj.id, func=job, dt=receivedDt, nodeType='intelligence')
                            if self_node.id in scrapers:
                                if result:
                                    result['scrape assignment'].append(f'{meeting_post.Region_obj.Name} {job}')
                                create_job(summarize_meetings, job_timeout=3600, worker='low', clear_chrome_job=False, post=meeting_post, dt=receivedDt, max_mins=max_mins)
                            job_assigned = True
                            job_id = hash_obj_id('DataPacket', specific_data=f"{dt_to_string(round_time(dt=receivedDt, dir='down', amount='hour'))}{job}{meeting_post.Region_obj.id}")
                            if self_node.id in scrapers + [validators[0]]:
                                for node_id in scrapers:
                                    if node_id != self_node.id:
                                        log = EventLog(
                                            jobId=job_id, 
                                            created=round_time(dt=receivedDt, dir='down', amount='hour'),
                                            Node_obj_id=node_id,
                                            func=f'assigned_job:{job}',
                                            type='job_tracker',
                                            Region_obj=meeting_post.Region_obj
                                            )
                                        log.save()
                if job == 'summarize_bills':
                    from legis.utils import summarize_bills
                    from legis.models import BillText

                    for region_id, chain_id in supported_regions.items():
                        if chain_id in self_node.chain_array:
                            if region_id.startswith('regSo') and not job_assigned:
                                spren = Spren.objects.filter(Region_obj__id=region_id, type='Billtext').exclude(Validator_obj=None).values('pointerId').order_by('-created')[:1000]
                                if BillText.objects.filter(Region_obj__id=region_id, Validator_obj__is_valid=True, created__gt=receivedDt-datetime.timedelta(days=7)).exclude(id__in=[s['pointerId'] for s in spren]).distinct('pointerId').order_by('pointerId','-created').exists():
                                    scrapers, validators = get_node_assignment(chainId=region_id, func=job, dt=receivedDt, nodeType='intelligence')
                                    if self_node.id in scrapers:
                                        if result:
                                            result['scrape assignment'].append(f'{region_id} {job}')
                                        create_job(summarize_bills, job_timeout=3000, worker='low', clear_chrome_job=False, region_id=region_id, dt=receivedDt, max_mins=max_mins)
                                        # job_assigned = True
                                    job_id = hash_obj_id('DataPacket', specific_data=f"{dt_to_string(round_time(dt=receivedDt, dir='down', amount='hour'))}{job}{region_id}")
                                    if self_node.id in scrapers + [validators[0]]:
                                        for node_id in scrapers:
                                            if node_id != self_node.id:
                                                log = EventLog(
                                                    jobId=job_id, 
                                                    created=round_time(dt=receivedDt, dir='down', amount='hour'),
                                                    Node_obj_id=node_id,
                                                    func=f'assigned_job:{job}',
                                                    type='job_tracker',
                                                    Region_obj_id=region_id
                                                    )
                                                log.save()
        if result:
            return result


