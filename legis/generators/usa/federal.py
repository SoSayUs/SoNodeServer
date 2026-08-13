
from django.db.models import Q, Avg

import django_rq
from django.contrib.contenttypes.models import ContentType

from accounts.models import UserData
from legis.models import Government,Agenda,Action,Bill,Meeting,Statement,Motion,RepVote,Election,Party,Person,District
from legis.utils import get_gov, get_region, modify_gov, add_gov_menu_item, remove_accents
from posts.models import Post, Update, ImageFile, Region
from posts.views import get_ordinal
from network.models import Node
from utils.models import (
    prnt, prntn, prntDebug, get_model_and_update, get_model_prefix, 
    save_and_return, declare_var, finishScript, create_share_object, 
    dt_to_string, save_mutable_fields, open_browser, close_browser, 
    now_utc, timezonify, testing, create_job, request_browser_data,
    logEvent, logError, return_test_result, script_test_error, save_image
    )

import datetime
from dateutil.parser import parse
import requests
import json
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import xmltodict
import pytz
import time
import re
import calendar
import wikipedia

from selenium.webdriver.common.by import By 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC

state_list = {
    'AK': 'Alaska',
    'AL': 'Alabama',
    'AR': 'Arkansas',
    'AZ': 'Arizona',
    'CA': 'California',
    'CO': 'Colorado',
    'CT': 'Connecticut',
    'DC': 'District of Columbia',
    'DE': 'Delaware',
    'FL': 'Florida',
    'GA': 'Georgia',
    'HI': 'Hawaii',
    'IA': 'Iowa',
    'ID': 'Idaho',
    'IL': 'Illinois',
    'IN': 'Indiana',
    'KS': 'Kansas',
    'KY': 'Kentucky',
    'LA': 'Louisiana',
    'MA': 'Massachusetts',
    'MD': 'Maryland',
    'ME': 'Maine',
    'MI': 'Michigan',
    'MN': 'Minnesota',
    'MO': 'Missouri',
    'MS': 'Mississippi',
    'MT': 'Montana',
    'NC': 'North Carolina',
    'ND': 'North Dakota',
    'NE': 'Nebraska',
    'NH': 'New Hampshire',
    'NJ': 'New Jersey',
    'NM': 'New Mexico',
    'NV': 'Nevada',
    'NY': 'New York',
    'OH': 'Ohio',
    'OK': 'Oklahoma',
    'OR': 'Oregon',
    'PA': 'Pennsylvania',
    'RI': 'Rhode Island',
    'SC': 'South Carolina',
    'SD': 'South Dakota',
    'TN': 'Tennessee',
    'TX': 'Texas',
    'UT': 'Utah',
    'VA': 'Virginia',
    'VT': 'Vermont',
    'WA': 'Washington',
    'WI': 'Wisconsin',
    'WV': 'West Virginia',
    'WY': 'Wyoming'
}

runTimes = {
    'initialize_region' : 2000,
    'get_bills_us' : 450, 'add_bill': 120, 
    'get_house_rollcalls_us' : 600, 'add_house_rollcall': 300, 
    'get_senate_rollcalls_us' : 600, 'add_senate_rollcall': 150, 
    'get_house_debates_us' : 1200, 'get_senate_debates_us' : 1200, 'add_official_debate_transcript': 420,
    'get_persons_us' : 600, 'get_senate_persons_us' : 300,
    'get_senate_committees' : 200, 
    'get_house_committees' : 1000, 'get_upcoming_senate_committees' : 200,
    'get_general_election_candidates' : 300, 'get_general_elections_results' : 200,
    }



functions = { # in gov_region timezone
    "2025-03-13" : [
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [2, 8, 10, 12, 14, 16, 18, 22], 'cmds' : ['get_bills_us'] },
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [1, 5, 17, 21], 'cmds' : ['get_house_rollcalls_us']},
    {'date' : ['x'], 'dayOfWeek' : [1,2,3,4,5,6], 'hour' : [3, 7, 16, 23], 'cmds' : ['get_senate_rollcalls_us']},
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [12,13,14], 'cmds' : ['get_house_debates_us','get_senate_debates_us']},
    ],
    "2026-01-24" : [
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [2, 8, 10, 12, 14, 16, 18, 22], 'cmds' : ['get_bills_us'] },
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [1, 5, 11, 17, 21], 'cmds' : ['get_house_debates_us', 'get_house_rollcalls_us']},
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [3, 7, 19, 23], 'cmds' : ['get_senate_debates_us', 'get_senate_rollcalls_us']},
    {'date' : ['x'], 'dayOfWeek' : [1], 'hour' : [14], 'cmds' : ['get_persons_us']},
    ],
}



approved_models = {
        # 'get_house_agendas' : ['Government', 'Agenda', 'AgendaTime', 'AgendaItem', 'Meeting'],
            'initialize_region' : ['Government', 'Person', 'Party', 'District', 'Region', 'ImageFile'],
            'get_persons_us' : ['Government', 'Person', 'Party', 'District', 'Region', 'ImageFile'],
            # 'get_senate_persons_us' : ['Government', 'Person', 'Party', 'Region', 'ImageFile'],
            'get_bills_us' : ['Bill', 'BillText', 'Committee', 'Meeting', 'Action', 'Government', 'Notification'],
            'get_house_debates_us' : ['Meeting', 'Statement', 'Agenda', 'Bill', 'BillText', 'Action', 'Government', 'Committee', 'Notification'],
            'get_senate_debates_us' : ['Meeting', 'Statement', 'Agenda', 'Bill', 'BillText', 'Action', 'Government', 'Committee', 'Notification'],
            'get_house_rollcalls_us' : ['Government', 'Motion', 'RepVote', 'Bill', 'BillText', 'Committee', 'Meeting', 'Action', 'Notification'],
            'get_senate_rollcalls_us' : ['Motion', 'RepVote', 'Bill', 'BillText', 'Government', 'Committee', 'Meeting', 'Action', 'Notification'],
            'get_general_election_candidates' : ['Election', 'Person', 'Party', 'Notification'],
            'get_general_elections_results' : ['Election', 'Person', 'Party', 'Notification'],
            'get_user_region' : ['District', 'Region', 'Party', 'Person'],
            }

def find_party(party_short=None, party_name=None):
    # prnt('find_party',party_short,party_name)
    party_list = {
        'Republican':{'short':'R','alt':None},
        'Democratic':{'short':'D','alt':'Democrat'},
        'Libertarian':{'short':'L','alt':None},
        'Independent':{'short':'I','alt':None},
        'Green':{'short':'G','alt':None},
    }
    if party_name:
        party_name_modded = party_name.replace('The','').replace('Party','').replace('the','').replace('party','').strip()
        for key, value in party_list.items():
            if key.lower() == party_name_modded.lower() or value['alt'] and value['alt'].lower() == party_name_modded.lower():
                return key, value['short'], value['alt']
    if party_short:
        for key, value in party_list.items():
            if value['short'] == party_short:
                return key, value['short'], value['alt']
    if party_short and not party_name:
        party_name = party_short
    return party_name, party_short, None

gov_logo_links = {"House": "img/regions/usa/house.svg.png", "Senate": "img/regions/usa/senate.svg.png"}

get_wiki = not testing()
get_wiki = False


def initialize_region(special=None, dt=None, iden=None):
    dt = declare_var(dt, now_utc())
    country = get_region('USA')
    log = create_share_object('initialize_region', country, special=special, dt=dt, iden=iden)
    get_persons_us(special=special, iden=log.id, func='initialize_region')
    # get_senate_persons_us(special=special, iden=log.id, func='initialize_region')


def api_fetch(url, country=None):
    prnt('-api_fetch',url)
    from utils.models import get_operatorData
    if not country:
        country = get_region('USA')
    data = None
    operatorData = get_operatorData()
    try:
        full_nodeData = operatorData['myNodes'][operatorData['local_nodeId']]
        if 'abilities' in full_nodeData['meta'] and country.id in full_nodeData['meta']['abilities']:
            api_key = full_nodeData['meta']['abilities'][country.id]['api_key']
            if '?' in url:
                x = '&api_key='
            else:
                x = '?api_key='
            url = url + x + api_key
            r = requests.get(url)
            data = r.content
            return data
    except Exception as e:
        prnt('err api_fetch',str(e))
    if not data:
        nodes = Node.objects.filter(active=True, region_array__contains=country.id).filter(abilities__api_keys__contains=country.id)
        for node in nodes:
            # proxy_request
            ...
    return None


def get_persons_us(special=None, dt=None, iden=None, func='get_persons_us', as_rq=True):
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    gov = None
    country = get_region('USA')
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)

    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')

    starting_url = 'https://www.house.gov/representatives'
    new_members = []
    found_persons = {'house':[], 'senate':[]}
    try:
        driver = open_browser(starting_url)

        # soup = get_browser_data(p='get_house_persons_1', driver=driver)

        prnt('loaded')
        element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="by-state"]/div/div/div[2]'))
        WebDriverWait(driver, 10).until(element_present)
        time.sleep(1)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        close_browser(driver)
    
    
        div = soup.find('div', {'id':'house-in-session'}).text
        a = div.find(' Congress, ')
        b = div[a+len(' Congress, '):].find(' Session')
        cong = div[:a]
        sess = div[a+len(' Congress, '):a+len(' Congress, ')+b]
        cong = cong.replace('st','').replace('nd','').replace('rd','').replace('th','')
        sess = sess.replace('st','').replace('nd','').replace('rd','').replace('th','')
        cong = int(cong)
        sess = int(sess)
        prnt(cong, sess)

        gov = get_gov(country, Country_obj=country, gov_level='Federal', gov_type='Congress', GovernmentNumber=cong, SessionNumber=sess, Region_obj=country)
        prnt('gov',gov)
        if not gov.StartDate:
            from utils.models import round_time
            gov.StartDate = timezonify('est', round_time(dt=now_utc(), dir='down', amount='day'))
            gov.migrate_data()
            gov.LogoLinks = gov_logo_links
        gov = modify_gov(gov, [{'Office_array':'Congressional Representative'},{'Chamber_array':'House'},{'menuItem_array':['Bills','Debates','RollCalls','Officials']}])
        gov = modify_gov(gov, [{'Office_array':'Senator'},{'Chamber_array':'Senate'}])
        log.updateShare(gov)
        
        content = soup.find('div', {'class':'view-content'})
        tables = content.find_all('table', {'class':'table'})
        for table in tables:
            state_name = table.find('caption').text.strip()
            for key, value in state_list.items():
                if value == state_name:
                    AbbrName = key
                    break
            state = Region.objects.filter(Name=state_name, AbbrName=AbbrName, nameType='State', ParentRegion_obj=country, Validator_obj__is_valid=True).first()
            if not state:
                state = Region(func=func, Name=state_name, AbbrName=AbbrName, nameType='State', ParentRegion_obj=country)
                state.save()
            if not state.Validator_obj or not state.Validator_obj.is_valid:
                log.updateShare(state)

            tbody = table.find('tbody')
            trs = tbody.find_all('tr')
            for tr in trs:
                tds = tr.find_all('td')
                district_name = tds[0].text.replace('st','').replace('nd','').replace('rd','').replace('th','').strip()
                # try:
                #     isint = int(district_name)
                #     district_name = district_name
                # except:
                #     # prnt('not int')
                #     ...

                district = District.objects.filter(Name=district_name, Country_obj=country, Region_obj=country, ProvState_obj=state, gov_level='Federal', nameType='Congressional District', Validator_obj__is_valid=True).first()
                if district:
                    if not district.Office_array or 'Congressional Representative' not in district.Office_array:
                        modded_district = district.propose_modification()
                        modded_district.add_office('Congressional Representative')
                    district, districtU, district_is_new, log = save_and_return(district, None, log)
                else:
                    district = District(func=func, Name=district_name, Country_obj=country, Region_obj=country, ProvState_obj=state, gov_level='Federal', nameType='Congressional District')
                    try:
                        dNum = get_ordinal(int(district_name))
                    except:
                        dNum = district_name
                    if get_wiki:
                        try:
                            time.sleep(1)
                            search_name = dNum + ' congressional district of ' + state_name
                            prnt('search_name',search_name)
                            title = wikipedia.search(search_name)[0].replace(' ', '_')
                            district.Wiki = 'https://en.wikipedia.org/wiki/' + title
                            prnt('district.Wiki',district.Wiki)
                            # district.update_data()
                        except Exception as e:
                            prnt('get_wiki err 1',str(e))
                    district.add_office('Congressional Representative')
                if not district.Validator_obj or not district.Validator_obj.is_valid:
                    log.updateShare(district)

                representative = tds[1]
                x = representative.text.find(', ')
                z = representative.text[x+2:].find('(link is external)')
                first_name = representative.text[x+2:x+2+z].strip()
                last_name = representative.text[:x].strip()
                prnt('first_name, last_name',first_name, last_name)
                a = representative.find('a')
                website = a['href']
                party_short = tds[2].text.strip()
                party_name, party_short, alt_name = find_party(party_short=party_short)

                party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=country, Region_obj=country, gov_level='Federal')
                if party_is_new:
                    if get_wiki:
                        try:
                            # time.sleep(1)
                            # search_name = party_name + ' american federal political party'
                            # prnt(search_name)
                            # link = wikipedia.search(search_name)[0].replace(' ', '_')
                            # party.Wiki = 'https://en.wikipedia.org/wiki/' + link
                            prnt('party.Wiki',party.Wiki)
                        except Exception as e:
                            prnt('party err 1:',str(e))
                            pass
                    party, partyU, party_is_new, log = save_and_return(party, partyU, log)

                officeRoom = tds[3].text.strip()
                phone = tds[4].text.strip()
                try:
                    assignments = tds[5].text.strip()
                except:
                    assignments = None

                personUpdate = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__Websites__contains=[website]).first()
                if personUpdate:
                    person, personU, person_is_new = get_model_and_update('Person', id=personUpdate.pointerId, Country_obj=country, Region_obj=country)
                    if person_is_new:
                        m = {'first':first_name, 'last':last_name, 'website':website, 'party':party, 'state':state, 'district':district, 'officeRoom':officeRoom, 'phone':phone, 'assignments':assignments}
                        new_members.append(m)
                    personU.data['Chamber'] = 'House'
                    personU.data['District_id'] = district.id
                    personU.data['ProvState_id'] = state.id
                    personU.data['FirstName'] = first_name
                    personU.data['LastName'] = last_name
                    personU.data['FullName'] = first_name + ' ' + last_name
                    personU.data['Position'] = 'Congressional Representative'
                    personU.data['gov_level'] = 'Federal'
                    personU.data['Telephones'] = [phone]
                    personU.data['Party_id'] = party.id
                    person.update_role(personU, data={'role':'Congressional Representative','current':True, 'gov_level':'Federal', 'officeName':officeRoom})

                    if assignments:
                        for assignment in assignments.split('|'):
                            data = {'role':assignment, 'current':True, 'gov_level':'Federal', 'Chamber':'House', 'Government_id':gov.id}
                            person.update_role(personU, data=data)
                    person, personU, person_is_new, log = save_and_return(person, personU, log)
                    found_persons['house'].append(person.id)
                    if not person.GovIden:
                        prnt('no govIden')
                        m = {'first':first_name, 'last':last_name, 'website':website, 'party':party, 'state':state, 'district':district, 'officeRoom':officeRoom, 'phone':phone, 'assignments':assignments, 'role':'Congressional Representative', 'chamber':'House'}
                        new_members.append(m)
                    elif 'PhotoLink' in personU.data and not ImageFile.objects.filter(pointerId=person.id, Validator_obj__is_valid=True).exists():
                        url = personU.data['PhotoLink']
                        try:
                            img_r = requests.get(url)
                            if img_r:
                                img_obj = save_image(url, f'legis/usa/', pointerId=person.id, r=img_r, region=country)
                                log.updateShare(img_obj)
                        except Exception as e:
                            prnt('img err 575',str(e))
                            
                else:
                    m = {'first':first_name, 'last':last_name, 'website':website, 'party':party, 'state':state, 'district':district, 'officeRoom':officeRoom, 'phone':phone, 'assignments':assignments, 'role':'Congressional Representative', 'chamber':'House'}
                    new_members.append(m)

        url = 'https://www.senate.gov/general/contact_information/senators_cfm.xml'
        r = requests.get(url)
        root = ET.fromstring(r.content)
        last_update = root.find('last_updated')
        prnt('last_update.text',last_update.text)
        # driver = None
        for member in root.findall('member'):
            member_full = member.find('member_full').text
            last_name = member.find('last_name').text
            first_name = member.find('first_name').text
            party_short = member.find('party').text
            state_short = member.find('state').text
            address = member.find('address').text
            phone = member.find('phone').text
            email = member.find('email').text
            website = member.find('website').text
            member_class = member.find('class').text
            bioguide_id = member.find('bioguide_id').text

            state = Region.objects.filter(AbbrName=state_short, Name=state_list[state_short], nameType='State', ParentRegion_obj=country, Validator_obj__is_valid=True).first()
            
            if not state:
                state = Region(func=func, AbbrName=state_short, Name=state_list[state_short], nameType='State', ParentRegion_obj=country)
                state.save()
            if not state.Validator_obj or not state.Validator_obj.is_valid:
                log.updateShare(state)
            party_name, party_short, alt_name = find_party(party_short=party_short)

            party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=country, Region_obj=country, gov_level='Federal')
            if party_is_new:
                if get_wiki:
                    try:   
                        search_name = party_name + ' american federal political party'
                        link = wikipedia.search(search_name)[0].replace(' ', '_')
                        party.Wiki = 'https://en.wikipedia.org/wiki/' + link
                    except:
                        pass
                party, partyU, party_is_new, log = save_and_return(party, partyU, log)

            person, personU, person_is_new = get_model_and_update('Person', GovIden=bioguide_id, Country_obj=country, Region_obj=country)
            personU.data['Chamber'] = 'Senate'
            personU.data['ProvState_id'] = state.id
            personU.data['FirstName'] = first_name
            personU.data['LastName'] = last_name
            personU.data['FullName'] = first_name + ' ' + last_name
            personU.data['Position'] = 'Senator'
            personU.data['gov_level'] = 'Federal'
            personU.data['Telephones'] = [phone]
            personU.data['Email'] = email
            personU.data['Party_id'] = party.id
            personU.data['Class'] = member_class
            personU.data['member_detail'] = remove_accents(member_full)
            person.update_role(personU, data={'role':'Senator','current':True, 'gov_level':'Federal'})
        
            person, personU, person_is_new, log = save_and_return(person, personU, log)

            if person_is_new or not person.GovProfilePage or not person.GovIden or not 'PhotoLink' in personU.data:
                s = {'person_obj':person, 'personU':personU, 'person_is_new':person_is_new, 'first':first_name, 'last':last_name, 'website':website, 'party':party, 'state':state, 'bioguide_id':bioguide_id, 'role':'Senator', 'chamber':'Senate'}
                new_members.append(s)
            elif 'PhotoLink' in personU.data and not ImageFile.objects.filter(pointerId=person.id, Validator_obj__is_valid=True).exists():
                url = personU.data['PhotoLink']
                try:
                    img_r = requests.get(url)
                    if img_r:
                        img_obj = save_image(url, f'legis/usa/', pointerId=person.id, r=img_r, region=country)
                        log.updateShare(img_obj)
                except Exception as e:
                    prnt('img err 578',str(e))
                    
            prnt(f"--Member Full: {member_full}")
            prnt(f"Last Name: {last_name}")
            prnt(f"First Name: {first_name}")
            prnt(f"Party: {party}")
            prnt(f"State: {state}")
            prnt(f"Bioguide ID: {bioguide_id}")
            found_persons['senate'].append(person.id)

            
        prnt('new_members',len(new_members),new_members)
        if new_members:
            # new_members = sorted(new_members, key=lambda item: item['last'].lower())

            url = f'https://api.congress.gov/v3/member/congress/{gov.GovernmentNumber}?format=json&limit=200&currentMember=true'
            
            def parse_data(url, found_persons, new_members, log):
                data = api_fetch(url)
                data = json.loads(data)
                for d in data:
                    if d == 'members':
                        for member_data in data[d]:
                            print()
                            print(member_data)
                            name = member_data['name']
                            found = False
                            for m in new_members:
                                if 'district' in m and str(member_data['district']) in m['district'].Name or member_data['district'] == 0:
                                    prnt("str(member_data['district'])",str(member_data['district']))
                                    if member_data['state'].lower() == m['state'].Name.lower():
                                        prnt("member_data['state'].lower()",member_data['state'].lower())
                                        if remove_accents(m['last']) in remove_accents(name):
                                            prnt("remove_accents(m['last'])",remove_accents(m['last']))
                                            found = True
                                            break
                                elif 'bioguide_id' in m and m['bioguide_id'] == member_data['bioguideId']:
                                    prnt("member_data['bioguideId']",member_data['bioguideId'])
                                    found = True
                                    break
                            prnt('found',found)
                            if found:
                                new_members.remove(m)
                                prnt(m)

                                code = member_data['bioguideId']
                                # img_url = f'https://www.congress.gov/img/member/{code}_200.jpg'
                                img_url = None

                                x = name.find(', ')
                                first_name = name[x+2:].strip()
                                last_name = name[:x].strip()
                                link = f"{first_name.split(' ')[0]}-{last_name.split(' ')[0]}/{code}"

                                if m.get('person') and m.get('personU'):
                                    person = m.get('person')
                                    personU = m.get('personU')
                                else:
                                    person, personU, person_is_new = get_model_and_update('Person', GovIden=code, Country_obj=country, Region_obj=country)
                                person.GovProfilePage = 'https://www.congress.gov' + link
                                personU.data['Websites'] = [m['website']]
                                personU.data['Chamber'] = m['chamber']
                                if m.get('district'):
                                    personU.data['District_id'] = m['district'].id
                                personU.data['ProvState_id'] = m['state'].id
                                personU.data['FirstName'] = first_name
                                personU.data['LastName'] = last_name
                                personU.data['FullName'] = name
                                personU.data['Position'] = m['role']
                                personU.data['gov_level'] = 'Federal'
                                if m.get('phone'):
                                    personU.data['Telephones'] = [m['phone']]
                                personU.data['Party_id'] = m['party'].id
                                if 'depiction' in member_data:
                                    img_url = member_data['depiction']['imageUrl']
                                    personU.data['PhotoLink'] = img_url

                                role_data = {'role':m['role'],'current':True, 'gov_level':'Federal', 'officeName':m['officeRoom'] if m.get('officeRoom') else None}
                                start_date = None
                                for item in member_data['terms']['item']:
                                    dt = datetime.datetime(year=int(item['startYear']), month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                                    year = timezonify('est', dt)
                                    if not start_date or year < start_date:
                                        start_date = year
                                if start_date:
                                    role_data['StartDate'] = dt_to_string(start_date)
                                person.update_role(personU, data=role_data)

                                if 'assignments' in m and m['assignments']:
                                    for assignment in m['assignments'].split('|'):
                                        role_data = {'role':assignment,'current':True,'gov_level':'Federal', 'Chamber':m['chamber'],'Government_id':gov.id}
                                        person.update_role(personU, data=role_data)

                                person, personU, person_is_new, log = save_and_return(person, personU, log)

                                try:
                                    prnt('img_url',img_url)
                                    if img_url:
                                        time.sleep(1)
                                        img_r = requests.get(img_url)
                                    if img_r:
                                        img_obj = save_image(img_url, f'legis/usa/', pointerId=person.id, r=img_r, region=country)
                                        log.updateShare(img_obj)
                                except Exception as e:
                                    prnt('img err 579',str(e))
                                if m['chamber'] == 'House':
                                    found_persons['house'].append(person.id)
                                elif m['chamber'] == 'Senate':
                                    found_persons['senate'].append(person.id)
    
                    elif d == 'pagination' and 'next' in data[d]:
                        prnt('data[d]',data[d])
                        prnt('found_persons:',len(found_persons['house'] + found_persons['senate']))
                        prnt('new_members len:',len(new_members))
                        if new_members:
                            time.sleep(1)
                            found_persons, new_members, log = parse_data(data[d]['next'], found_persons, new_members, log)
                    else:
                        prnt('else')
                        print(d, data[d])
                return found_persons, new_members, log

            found_persons, new_members, log = parse_data(url, found_persons, new_members, log)



        #     prnt('len(new_members)',len(new_members))
        #     prnt('^ new members')
        #     url = f'https://www.congress.gov/search?pageSize=250&q=%7B%22source%22%3A%22members%22%2C%22congress%22%3A%22{gov.GovernmentNumber}%22%2C%22chamber%22%3A%22House%22%7D'
        #     prnt('url',url)
        #     url2 = f'https://www.congress.gov/search?pageSize=250&q=%7B%22source%22%3A%22members%22%2C%22congress%22%3A%22{gov.GovernmentNumber}%22%2C%22chamber%22%3A%22House%22%7D&page=2'
        #     prnt('url2',url2)
        #     try:
        #         # driver.get(url)
        #         # prnt('loaded')
        #         # element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="main"]'))
        #         # WebDriverWait(driver, 10).until(element_present)
        #         # prnt('ready1')

        #         # soup1 = BeautifulSoup(driver.page_source, 'html.parser')
        #         soup1 = get_browser_data(p='get_house_persons_2', driver=driver, url=url)

        #         # driver.get(url2)
        #         # prnt('loaded2')
        #         # element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="main"]'))
        #         # WebDriverWait(driver, 10).until(element_present)
        #         # prnt('ready12')
        #         # soup2 = BeautifulSoup(driver.page_source, 'html.parser')
        #         soup2 = get_browser_data(p='get_house_persons_3', driver=driver, url=url2)

        #     except Exception as e:
        #         prnt('house persons err 2',str(e))

        #     close_browser(driver)

            # def get_data(soup, log):
            #     main = soup.find('div', {'id':'main'})
            #     lis = main.find_all('li', {'class':'expanded'})
            #     for li in lis:
            #         if li.text and 'Present' in li.text:
            #             try:
            #                 if not new_members:
            #                     prnt('new_members done')
            #                     break
            #             except:
            #                 pass
            #             searchText = remove_accents(li.text).replace(' ','')
            #             found = False
            #             for m in new_members:
            #                 required = [f"{m['last']}", f"{m['first']}", m['state'].Name, m['district'].Name.replace('District ',''), m['party'].Name, 'Present']
            #                 for i in required:
            #                     if i.replace(' ','') not in searchText:
            #                         found = False
            #                         break
            #                     else:
            #                         found = True
            #                 if found:
            #                     prnt('FOUND',m)
            #                     new_members.remove(m)
            #                     heading = li.find('span', {'class':'result-heading'})
            #                     try:
            #                         img_url = 'https://www.congress.gov' + li.find('img')['src']
            #                         prnt('firstImg:',img_url)
            #                     except Exception as e:
            #                         prnt('find image fail',str(e))
            #                         img_url = None
            #                     listing_name = remove_accents(heading.find('a').text)
            #                     x = listing_name.find(', ')
            #                     z = listing_name[x+2:].find(' - ')
            #                     first_name = listing_name[x+2:x+2+z].strip()
            #                     last_name = listing_name[:x].strip()

            #                     link = heading.find('a')['href']
                                
            #                     prnt('link',link)
            #                     q = link.find('?')
            #                     w = link[:q].rfind('/')
            #                     code = link[w+1:q]
            #                     link = link[:q]
            #                     person, personU, person_is_new = get_model_and_update('Person', GovIden=code, Country_obj=country, Region_obj=country)
            #                     if not img_url:
            #                         img_url = 'https://www.congress.gov/img/member/%s_200.jpg' %(code.lower())

            #                     try:
            #                         if img_url:
            #                             img_r = requests.get(img_url)
            #                         if img_r:
            #                             img_obj = save_image(img_url, f'legis/usa/', pointerId=person.id, r=img_r, region=country)
            #                             log.updateShare(img_obj)
            #                     except Exception as e:
            #                         prnt('img err 576',str(e))
                                    
            #                     profile = li.find('div', {'class':'member-profile'})
            #                     spans = profile.find_all('span', {'class':'result-item'})
            #                     start_date = None
            #                     for span in spans:
            #                         if 'Served' in span.text:
            #                             z = span.text.find('House: ')+len('House: ')
            #                             x = span.text[z:].find('-')
            #                             dt = datetime.datetime(year=int(span.text[z:z+x].strip()), month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            #                             start_date = timezonify('est', dt)
            #                             break
            #                     if person_is_new and get_wiki:
            #                         try:
            #                             time.sleep(1)
            #                             search_name = m['state'].Name + ' congressional representative ' + first_name + ' ' + last_name
            #                             prnt(search_name)
            #                             title = wikipedia.search(search_name)[0].replace(' ', '_')
            #                             u = 'https://en.wikipedia.org/wiki/' + title
            #                             person.Wiki = u
            #                         except Exception as e:
            #                             prnt(str(e))
            #                     person.GovProfilePage = 'https://www.congress.gov' + link
            #                     personU.data['Websites'] = [m['website']]
            #                     personU.data['Chamber'] = 'House'
            #                     personU.data['District_id'] = m['district'].id
            #                     personU.data['ProvState_id'] = m['state'].id
            #                     personU.data['FirstName'] = first_name
            #                     personU.data['LastName'] = last_name
            #                     personU.data['FullName'] = first_name + ' ' + last_name
            #                     personU.data['Position'] = 'Congressional Representative'
            #                     personU.data['gov_level'] = 'Federal'
            #                     personU.data['Telephones'] = [m['phone']]
            #                     personU.data['Party_id'] = m['party'].id
            #                     personU.data['PhotoLink'] = img_url
            #                     data = {'role':'Congressional Representative','current':True, 'gov_level':'Federal', 'officeName':m['officeRoom']}
            #                     if start_date:
            #                         data['StartDate'] = dt_to_string(start_date)
            #                     person.update_role(personU, data=data)

            #                     if 'assignments' in m and m['assignments']:
            #                         for assignment in m['assignments'].split('|'):

            #                             data = {'role':assignment,'current':True,'gov_level':'Federal', 'Chamber':'House','Government_id':gov.id}
            #                             person.update_role(personU, data=data)
            #                     person, personU, person_is_new, log = save_and_return(person, personU, log)
            #                     congressmen.append(person.id)
            #                     break
            #     return log

        #     log = get_data(soup1, log)
        #     log = get_data(soup2, log)
        # else:
        #     close_browser(driver)

        prnt('not found members:',new_members)
        # if new_members:
        #     logEvent('not found members', func='get_house_persons', code='37463', region=country, extra={'missing':new_members})
        prnt('found_persons len',len(found_persons))

        prnt('remove previous congressmen')
        repUpdates = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, extra__roles__contains=[{'role':'Congressional Representative','current':True, 'gov_level':'Federal'}]).exclude(pointerId__in=found_persons['house'])
        for u in repUpdates:
            prnt('removing:::',u.pointerId)
            update = u.create_next_version()
            if 'Position' in update.data and update.data['Position'] == 'Congressional Representative':
                del update.data['Position']
            update.Pointer_obj.update_role(update, role='Congressional Representative', current=False)
            update, u_is_new = update.save_if_new(func=func)
            if u_is_new:
                log.updateShare(update)
        
        prnt('remove previous senators')
        repUpdates = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, extra__roles__contains=[{'role':'Senator', 'current':True, 'gov_level':'Federal'}]).exclude(pointerId__in=found_persons['senate'])
        for u in repUpdates:
            prnt('removing:::',u.pointerId)
            update = u.create_next_version()
            if 'Position' in update.data and update.data['Position'] == 'Senator':
                del update.data['Position']
            update.Pointer_obj.update_role(update, role='Senator', current=False)
            update, u_is_new = update.save_if_new(func=func)
            if u_is_new:
                log.updateShare(update)
        prnt('done')
    
    except Exception as e:
        prnt('house persons fail ',str(e))

    # close_browser(driver)
    return finishScript(log, gov, special)


def get_senate_persons_us(special=None, dt=None, iden=None, func='get_senate_persons_us', as_rq=True):
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    country = get_region('USA')
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = get_gov(country)
    gov = modify_gov(gov, [{'Office_array':'Senator'},{'Chamber_array':'Senate'},{'menuItem_array':'Officials'}])
    log.updateShare(gov)
    if not gov and country:
        return finishScript(log, gov, special)
    
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')
    
    url = 'https://www.senate.gov/general/contact_information/senators_cfm.xml'
    r = requests.get(url)
    root = ET.fromstring(r.content)
    last_update = root.find('last_updated')
    prnt('last_update.text',last_update.text)
    driver = None
    driver_service = None
    senators = []
    new_senators = []
    for member in root.findall('member'):
        member_full = member.find('member_full').text
        last_name = member.find('last_name').text
        first_name = member.find('first_name').text
        party_short = member.find('party').text
        state_short = member.find('state').text
        address = member.find('address').text
        phone = member.find('phone').text
        email = member.find('email').text
        website = member.find('website').text
        member_class = member.find('class').text
        bioguide_id = member.find('bioguide_id').text

        state = Region.objects.filter(AbbrName=state_short, Name=state_list[state_short], nameType='State', ParentRegion_obj=country, Validator_obj__is_valid=True).first()
        
        if not state:
            state = Region(func=func, AbbrName=state_short, Name=state_list[state_short], nameType='State', ParentRegion_obj=country)
            state.save()
        if not state.Validator_obj or not state.Validator_obj.is_valid:
            log.updateShare(state)
        party_name, party_short, alt_name = find_party(party_short=party_short)

        party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=country, Region_obj=country, gov_level='Federal')
        if party_is_new:
            if get_wiki:
                try:   
                    search_name = party_name + ' american federal political party'
                    link = wikipedia.search(search_name)[0].replace(' ', '_')
                    party.Wiki = 'https://en.wikipedia.org/wiki/' + link
                except:
                    pass
            party, partyU, party_is_new, log = save_and_return(party, partyU, log)

        person, personU, person_is_new = get_model_and_update('Person', GovIden=bioguide_id, Country_obj=country, Region_obj=country)
        personU.data['Chamber'] = 'Senate'
        personU.data['ProvState_id'] = state.id
        personU.data['FirstName'] = first_name
        personU.data['LastName'] = last_name
        personU.data['FullName'] = first_name + ' ' + last_name
        personU.data['Position'] = 'Senator'
        personU.data['gov_level'] = 'Federal'
        personU.data['Telephones'] = [phone]
        personU.data['Email'] = email
        personU.data['Party_id'] = party.id
        personU.data['Class'] = member_class
        personU.data['member_detail'] = remove_accents(member_full)
        person.update_role(personU, data={'role':'Senator','current':True, 'gov_level':'Federal'})
    
        person, personU, person_is_new, log = save_and_return(person, personU, log)

        if person_is_new or not person.GovProfilePage or not person.GovIden or not 'PhotoLink' in personU.data:
            s = {'person_obj':person, 'personU':personU, 'person_is_new':person_is_new, 'first':first_name, 'last':last_name, 'website':website, 'party':party, 'state':state, 'bioguide_id':bioguide_id}
            new_senators.append(s)
        elif 'PhotoLink' in personU.data and not ImageFile.objects.filter(pointerId=person.id, Validator_obj__is_valid=True).exists():
            url = personU.data['PhotoLink']
            try:
                img_r = requests.get(url)
                if img_r:
                    img_obj = save_image(url, f'legis/usa/', pointerId=person.id, r=img_r, region=country)
                    log.updateShare(img_obj)
            except Exception as e:
                prnt('img err 578',str(e))
                
        prnt(f"--Member Full: {member_full}")
        prnt(f"Last Name: {last_name}")
        prnt(f"First Name: {first_name}")
        prnt(f"Party: {party}")
        prnt(f"State: {state}")
        # prnt(f"Address: {address}")
        # prnt(f"Phone: {phone}")
        # prnt(f"Email: {email}")
        # prnt(f"Website: {website}")
        # prnt(f"Class: {member_class}")
        prnt(f"Bioguide ID: {bioguide_id}")
        senators.append(person.id)
                
    if new_senators:
        new_senators = sorted(new_senators, key=lambda item: item['last'].lower())
        url = f'https://www.congress.gov/search?pageSize=250&q=%7B%22source%22%3A%22members%22%2C%22congress%22%3A%22{gov.GovernmentNumber}%22%2C%22chamber%22%3A%22Senate%22%7D'
        try:
            driver = open_browser(url)
            prnt('loaded')
            element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="main"]'))
            WebDriverWait(driver, 10).until(element_present)
            soup1 = BeautifulSoup(driver.page_source, 'html.parser')
        except Exception as e:
            prnt('sen persons url err', str(e))
            soup1 = {}

        close_browser(driver)

        def get_data(soup, log):
            prnt('get data')
            main = soup.find('div', {'id':'main'})
            lis = main.find_all('li', {'class':'expanded'})
            for li in lis:
                if li.text and 'Present' in li.text:
                    if not new_senators:
                        prnt('new_senators done')
                        break
                    searchText = remove_accents(li.text).replace(' ','')
                    found = False
                    for m in new_senators:
                        required = [f"{remove_accents(m['last'])}", f"{remove_accents(m['first'])}", m['state'].Name, m['party'].Name, 'Senator', 'Present']
                        for i in required:
                            if i.replace(' ','') not in searchText:
                                found = False
                                break
                            else:
                                found = True
                        if found:
                            prnt('FOUND',m)
                            new_senators.remove(m)
                            heading = li.find('span', {'class':'result-heading'})
                            try:
                                img_url = 'https://www.congress.gov' + li.find('img')['src']
                            except:
                                img_url = None
                            listing_name = remove_accents(heading.find('a').text)
                            x = listing_name.find(', ')
                            z = listing_name[x+2:].find(' - ')
                            first = listing_name[x+2:x+2+z].strip()
                            last = listing_name[:x].strip()
                            link = heading.find('a')['href']
                            
                            prnt('link',link)
                            q = link.find('?')
                            w = link[:q].rfind('/')
                            code = link[w+1:q]
                            link = link[:q]
                            prnt('code',code)
                            person = m['person_obj']
                            personU = m['personU']
                            person_is_new = m['person_is_new']

                            if not img_url:
                                img_url = 'https://www.congress.gov/img/member/%s_200.jpg' %(code.lower())
                            prnt('img_url',img_url)
                            try:
                                if img_url:
                                    img_r = requests.get(img_url)
                                if img_r:
                                    img_obj = save_image(img_url, f'legis/usa/', pointerId=person.id, r=img_r, region=country)
                                    log.updateShare(img_obj)
                            except Exception as e:
                                prnt('img err 579',str(e))

                            profile = li.find('div', {'class':'member-profile'})
                            spans = profile.find_all('span', {'class':'result-item'})
                            start_date = None
                            for span in spans:
                                if 'Served' in span.text:
                                    z = span.text.find('Senate: ')+len('Senate: ')
                                    x = span.text[z:].find('-')
                                    start_date = timezonify('est', datetime.datetime(year=int(span.text[z:z+x].strip()), month=1, day=1, hour=0, minute=0, second=0, microsecond=0))
                                    break
                            if person_is_new and get_wiki:
                                try:
                                    time.sleep(1)
                                    search_name = m['state'].Name + ' Senator ' + m['first'] + ' ' + m['last']
                                    prnt('search_name',search_name)
                                    title = wikipedia.search(search_name)[0].replace(' ', '_')
                                    u = 'https://en.wikipedia.org/wiki/' + title
                                    person.Wiki = u
                                except Exception as e:
                                    prnt('sen get wiki err', str(e))

                            person.GovProfilePage = 'https://www.congress.gov' + link
                            personU.data['Websites'] = [m['website']]
                            personU.data['Chamber'] = 'Senate'
                            personU.data['ProvState_id'] = m['state'].id
                            personU.data['FirstName'] = m['first']
                            personU.data['LastName'] = m['last']
                            personU.data['FullName'] = m['first'] + ' ' + m['last']
                            personU.data['Position'] = 'Senator'
                            personU.data['gov_level'] = 'Federal'
                            personU.data['Party_id'] = m['party'].id
                            personU.data['PhotoLink'] = img_url
                            data = {'role':'Senator','current':True,'gov_level':'Federal'}
                            if start_date:
                                data['StartDate'] = dt_to_string(start_date)
                            person.update_role(personU, data=data)
                            person, personU, person_is_new, log = save_and_return(person, personU, log)
                            senators.append(person.id)
                            break
            return log

        log = get_data(soup1, log)
        prnt('done new senators')
        # if new_senators:
        #     logEvent('not found senators', func='get_senate_persons_us', code='3847', region=country, extra={'missing':new_senators})

    prnt('remove previous senators')
    repUpdates = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, extra__roles__contains=[{'role':'Senator', 'current':True, 'gov_level':'Federal'}]).exclude(pointerId__in=senators)
    for u in repUpdates:
        prnt('removing:::',u.pointerId)
        update = u.create_next_version()
        if 'Position' in update.data and update.data['Position'] == 'Senator':
            del update.data['Position']
        update.Pointer_obj.update_role(update, role='Senator', current=False)
        update, u_is_new = update.save_if_new(func=func)
        if u_is_new:
            log.updateShare(update)
    return finishScript(log, gov, special)

# not used
def get_senator_details(driver, personId):
            
    url = f'https://bioguide.congress.gov/search/bio/{personId}'
    driver.get(url)
    element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div/div/div[2]/div/div[1]'))
    WebDriverWait(driver, 10).until(element_present)

    photoSrc = driver.find_element(By.XPATH, '//*[@id="root"]/div/div/div[2]/div/div[1]/div[1]/div[3]/div/img').get_attribute('src')
    photoLink = 'https://bioguide.congress.gov' + photoSrc

    serving = driver.find_element(By.XPATH, '//*[@id="profile-overview--desktop"]/div/div[2]/div[2]/span[2]').text.replace('(','').replace(')','').strip()
    # "(2007 – Present)"
    a = serving.find('–')
    startYearTxt = serving[:a].strip()
    startingYear = datetime.strptime(startYearTxt, '%Y')

    bio = driver.find_element(By.XPATH, '//*[@id="Biography"]/div').text
    # x = 'https://bioguide.congress.gov/photo/3b76ebb14cbdc3c0e07d89e5d84e1075.jpg'
    # close_browser(driver)
    return photoLink, startingYear, bio


def get_bills_us(special=None, dt=None, iden=None, target_dt=None, target_links=None, job_dt=None, task=None, as_rq=True):
    func = 'get_bills_us'
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    task = declare_var(task, 1)
    prnt('task:',task)
    prnt('dt',dt)
    prnt('target_links',target_links)
    country = get_region('USA')
    if not job_dt:
        job_dt = dt
    log = create_share_object(func, country, special=special, dt=dt, iden=iden, job_dt=job_dt, task=task)
    if not log:
        return
    gov = get_gov(country)
    if not gov and country:
        return finishScript(log, gov, special)
    if special != 'testing':
        logEvent(f'scrapeAssignment target_links:{len(target_links) if target_links else 0}', region=country, func=func, log_type='Tasks')

    log = add_gov_menu_item(gov, 'Bills', log)

    driver = None
    driver_service = None
    if target_links:
        if not target_dt:
            target_dt = dt
        updates = Update.objects.filter(pointerKey=ContentType.objects.get_for_model(Bill), Region_obj=country, data__data_link__in=target_links, created__gte=target_dt).filter(Q(validated=True)|Q(created__gt=now_utc()-datetime.timedelta(minutes=60))).distinct('pointerId').order_by('pointerId','-created')
        for u in updates:
            if u.data['data_link'] in target_links:
                if u.validated or u.created > now_utc() - datetime.timedelta(minutes=60) and not special:
                    target_links.remove(u.data['data_link'])

        for link in target_links:
            if link:
                log, driver, driver_service = add_bill(url=link, log=log, update_dt=target_dt, driver=driver, driver_service=driver_service, country=country, ref_func=func)
                if link != target_links[-1]:
                    time.sleep(2)
            
    else:
        prnt('task2:',task)
        xml = 'https://www.govinfo.gov/rss/billstatus-batch.xml'
        r = requests.get(xml)
        root = ET.fromstring(r.content)
        channel = root.find('channel')
        item_list = list(reversed(channel.findall('item')))

        i = 0

        def check_item_updates(item, i, log, driver=None, driver_service=None, task=1):
            pubDate = item.find('pubDate')
            pub_dt = datetime.datetime.strptime(pubDate.text, "%a, %d %b %Y %H:%M:%S %z")
            desc = item.find('description')
            soup = BeautifulSoup(desc.text, 'html.parser')
            ass = soup.find_all('a')
            links = []
            for a in ass:
                if a['href']:
                    links.append(a['href'])
            prnt('links1:',links)
            updates = Update.objects.filter(pointerKey=ContentType.objects.get_for_model(Bill), Region_obj=country, data__data_link__in=links, created__gte=pub_dt).filter(Q(validated=True)|Q(created__gt=now_utc()-datetime.timedelta(minutes=60))).distinct('pointerId').order_by('pointerId','-created')
            for u in updates:
                prnt('u1',u)
                if u.data['data_link'] in links:
                    if u.validated or u.created > now_utc() - datetime.timedelta(minutes=60) and not special:
                        links.remove(u.data['data_link'])

            prnt('links2:',links)
            if testing():
                x = 1
            else:
                x = 1 # adjust here for shorter runtime, but less lookback
            if not links and i < x:
                i += 1
                check_item_updates(item_list[i], i, log, driver, driver_service, task=task)
            else:
                max_bills_run = 8
                while i >= 0:
                    item = item_list[i]
                    i -= 1
                    pubDate = item.find('pubDate')
                    pub_dt = datetime.datetime.strptime(pubDate.text, "%a, %d %b %Y %H:%M:%S %z")
                    while len(links) > 0:
                        target_links = links[:max_bills_run]
                        task += 1
                        if as_rq:
                            queue = django_rq.get_queue('low')
                            queue.enqueue(get_bills_us, special=special, target_links=target_links, dt=now_utc(), job_dt=job_dt, task=task, target_dt=pub_dt, job_timeout=runTimes[func], result_ttl=7200)
                        else:
                            prnt('pause')
                            get_bills_us(special=special, target_links=target_links, dt=now_utc(), job_dt=job_dt, task=task, target_dt=pub_dt, as_rq=False)
                        if len(links) > max_bills_run:
                            links = links[max_bills_run:]
                        else:
                            links = []
            return log, driver, driver_service
                    
        log, driver, driver_service = check_item_updates(item_list[i], i, log, task=task)   

    if driver:
        close_browser(driver)

    return finishScript(log, gov, special)

billTypes = {'hr':{'chamber':'House','billType':'Bill','prefix':'H.R.','legisLink':'https://www.congress.gov/bill/xxx-congress/house-bill/'},
        'hres':{'chamber':'House','billType':'Resolution','prefix':'H.Res.','legisLink':'https://www.congress.gov/bill/xxx-congress/house-resolution/'},
        'hconres':{'chamber':'House','billType':'Concurrent Resolution','prefix':'H.Con.Res.','legisLink':'https://www.congress.gov/bill/xxx-congress/house-concurrent-resolution/'},
        'hamdt':{'chamber':'House','billType':'Amendment','prefix':'H.Amdt','legisLink':'https://www.congress.gov/amendment/xxx-congress/house-amendment/'},
        'sconres':{'chamber':'Senate','billType':'Concurrent Resolution','prefix':'S.Con.Res.','legisLink':'https://www.congress.gov/bill/xxx-congress/senate-concurrent-resolution/'},
        'samdt':{'chamber':'Senate','billType':'Amendment','prefix':'S.Amdt','legisLink':'https://www.congress.gov/amendment/xxx-congress/senate-amendment/'},
        'hjres':{'chamber':'House','billType':'Joint Resolution','prefix':'H.J.Res.','legisLink':'https://www.congress.gov/bill/xxx-congress/house-joint-resolution/'},
        'sjres':{'chamber':'Senate','billType':'Joint Resolution','prefix':'S.J.Res.','legisLink':'https://www.congress.gov/bill/xxx-congress/senate-joint-resolution/'},
        'sres':{'chamber':'Senate','billType':'Resolution','prefix':'S.Res.','legisLink':'https://www.congress.gov/bill/xxx-congress/senate-resolution/'},
        's':{'chamber':'Senate','billType':'Bill','prefix':'S.','legisLink':'https://www.congress.gov/bill/xxx-congress/senate-bill/'}
        }

def add_bill(url=None, log=None, update_dt=None, driver=None, driver_service=None, special=None, country=None, ref_func=None):
    func = 'add_bill'
    prnt(f'--{func} USA', now_utc())
    dt = now_utc()
    log = declare_var(log, [])
    if not country:
        country = Region.supported_objects.filter(nameType='Country', Name='USA').first()
    if not log:
        log = create_share_object(func, country, special=special, dt=now_utc(), iden=None)
    err = 'start'
    try:
        if not url:
            return log, driver, driver_service
        prnt('href:',url)
        r = requests.get(url)
        root = ET.fromstring(r.content)
        billXML = root.find('bill')
        try:
            billNum = billXML.find('number').text
        except:
            billNum = billXML.find('billNumber').text
        try:
            type = billXML.find('type').text
        except:
            type = billXML.find('billType').text
        prnt('billNum',billNum)
        try:
            updateDate = billXML.find('updateDate').text
        except:
            updateDate = None
        try:
            updateDateIncludingText = billXML.find('updateDateIncludingText').text
        except:
            updateDateIncludingText = None
        try:
            originChamberCode = billXML.find('originChamberCode').text
        except:
            originChamberCode = None
        originChamber = billXML.find('originChamber').text
        introducedDate = billXML.find('introducedDate').text
        congress = billXML.find('congress').text
        prnt('congress',congress)
        billType = billTypes[type.lower().replace('.','')]['billType']
        billPrefix = billTypes[type.lower().replace('.','')]['prefix']
        billCode = billPrefix + billNum
        legisLink = billTypes[type.lower().replace('.','')]['legisLink'] + billNum
        prnt('legisLink',legisLink)
        from posts.views import get_ordinal
        legisLink = legisLink.replace('xxx', get_ordinal(congress))
        prnt('legisLink2',legisLink)

        err = 0
        try:
            prnt(f'billNum: {billNum}')
            prnt(f'updateDate: {updateDate}')
            # prnt(f'updateDateIncludingText: {updateDateIncludingText}')
            # prnt(f'originChamber: {originChamber}')
            # prnt(f'type: {type}')
            # prnt(f'introducedDate: {introducedDate}')
            prnt(f'congress: {congress}')
            prnt(f'billCode: {billCode}')
        except Exception as e:
            prnt('err123',str(e))

        gov = Government.objects.filter(Country_obj=country, gov_level='Federal', GovernmentNumber=int(congress), Validator_obj__is_valid=True).first()
        if not gov:
            gov = Government(Country_obj=country, gov_level='Federal', gov_type='Congress', GovernmentNumber=int(congress), Region_obj=country)
            gov.StartDate = timezonify('est', introducedDate)
            gov.migrate_data()
            gov.LogoLinks = gov_logo_links
            gov.save()
            log.updateShare(gov)
        err = 1
        
        bill, billU, bill_is_new = get_model_and_update('Bill', Government_obj=gov, Country_obj=country, Region_obj=country, Chamber=originChamber, NumberCode=billCode, BillDocumentTypeName=billType)
        new_bill = bill_is_new
        if bill_is_new:
            bill.LegisLink = legisLink
            bill.NumberPrefix = billPrefix
            bill.Number = billNum
            bill.Started = timezonify('est', introducedDate)
            bill.save()
        if 'Status' not in billU.data:
            billU.data['Status'] = 'Introduced'
        if updateDate:
            billU.DateTime = timezonify('est', updateDate)
        if 'billVersions' not in billU.data:
            versions = None
            def versionizer(version, current=None):
                if not current and version == 'Introduced':
                    current = True
                return {'version':version, 'current':current, 'status':None, 'started_dt':None, 'completed_dt':None}
            if originChamber == 'Senate':
                if type.lower() == 'sres':
                    versions = [versionizer('Introduced'), versionizer('Senate')]
                elif type.lower() == 'sjres':
                    versions = [versionizer('Introduced'), versionizer('Senate'), versionizer('House'), versionizer('President'), versionizer('Law')]
                elif type.lower() == 'sconres':
                    versions = [versionizer('Introduced'), versionizer('Senate'), versionizer('House')]
                elif type.lower() == 's':
                    versions = [versionizer('Introduced'), versionizer('Senate'), versionizer('House'), versionizer('President'), versionizer('Law')]

            elif originChamber == 'House':
                if type.lower() == 'hres':
                    versions = [versionizer('Introduced'), versionizer('House')]
                elif type.lower() == 'hjres':
                    versions = [versionizer('Introduced'), versionizer('House'), versionizer('Senate'), versionizer('President'), versionizer('Law')]
                elif type.lower() == 'hconres':
                    versions = [versionizer('Introduced'), versionizer('House'), versionizer('Senate')]
                elif type.lower() == 'hr':
                    versions = [versionizer('Introduced'), versionizer('House'), versionizer('Senate'), versionizer('President'), versionizer('Law')]
            if versions:
                billU.data['billVersions'] = versions
        err = 2
        billU.data['data_link'] = url

        prnt('committees::')
        committees = billXML.find('committees')
        if committees:
            items = committees.findall('item')
            for i in items:
                systemCode = i.find('systemCode')
                name = i.find('name')
                chamber = i.find('chamber')
                type = i.find('type')

                activities = i.find('activities')
                if activities:
                    for x in activities.findall('item'):
                        name = x.find('name')
                        date = x.find('date')
                
                xml_str = ET.tostring(i, encoding='unicode')
                committee_data = xmltodict.parse(xml_str)
                # prnt("committee_data",committee_data)
                committee_data = committee_data['item']

                if not billU.extra:
                    billU.extra = {}
                if 'committees' not in billU.extra:
                    billU.extra['committees'] = []
                if committee_data not in billU.extra['committees']:
                    billU.extra['committees'].append(committee_data)

        err = 3
        prnt('committeeReports::')
        committeeReports = billXML.find('committeeReports')
        if committeeReports:
            if 'committeeReports' not in billU.data:
                billU.data['committeeReports'] = []
            for c in committeeReports:
                try:
                    report_url = None
                    citation = c.find('citation').text
                    # <citation>H. Rept. 118-353</citation>
                    a = citation.find('-')+len('-')
                    num = citation[a:]
                    from posts.views import get_ordinal
                    prnt(f'citation: {citation}')
                    report_url = f"https://www.congress.gov/congressional-report/{get_ordinal(gov.GovernmentNumber)}-congress/{bill.Chamber.lower()}-report/{num}/1"
                    
                except Exception as e:
                    prnt('bill err 385',str(e))
                
                xml_str = ET.tostring(c, encoding='unicode')
                committeeReport_data = xmltodict.parse(xml_str)
                # prnt("committeeReport_data",committeeReport_data)
                if 'item' in committeeReport_data:
                    committeeReport_data = committeeReport_data['item']
                if report_url and 'report_url' not in committeeReport_data:
                    committeeReport_data['report_url'] = report_url

                if not billU.extra:
                    billU.extra = {}
                if 'committeeReports' not in billU.extra:
                    billU.extra['committeeReports'] = []
                if committeeReport_data not in billU.extra['committeeReports']:
                    billU.extra['committeeReports'].append(committeeReport_data)
        err = 4
        prnt('relatedBills::')
        relatedBills = billXML.find('relatedBills')
        if relatedBills:
            if 'relatedBills' not in billU.data:
                billU.data['relatedBills'] = []
            for i in relatedBills.findall('item'):
                try:
                    title = i.find('title').text
                    congress = i.find('congress').text
                    number = i.find('number').text
                    type = i.find('type').text
                    if not any(d.get('title') == title for d in billU.data['relatedBills']):
                        rBill = Bill.objects.filter(Number=number, NumberPrefix__iexact=type.lower(), Government_obj__GovernmentNumber=int(congress), Validator_obj__is_valid=True)
                        if rBill:
                            r_data = {'billId':rBill.id, 'billNumber':rBill.NumberCode, 'title':title, 'congress':rBill.Government_obj.get_gov_num()}
                            if r_data not in billU.data['relatedBills']:
                                billU.data['relatedBills'].append(r_data)
                        else:
                            r_data = {'billNumber':f'{type}{number}', 'congress':congress, 'title':title}
                            if r_data not in billU.data['relatedBills']:
                                billU.data['relatedBills'].append(r_data)
                    # prnt(f'title: {title}')
                    # prnt(f'congress: {congress}')
                    # prnt(f'number: {number}')
                    # prnt(f'type: {type}')
                except Exception as e:
                    prnt('bill err 5921',str(e))

                latestAction = i.find('latestAction')
                if latestAction:
                    for x in latestAction:
                        actionDate = x.find('actionDate')
                        text = x.find('text')
                        # try:
                        #     prnt(f'actionDate: {actionDate.text}')
                        #     prnt(f'text: {text.text}')
                        # except Exception as e:
                        #     prnt(str(e))

                relationshipDetails = i.find('relationshipDetails')
                if relationshipDetails:
                    for x in relationshipDetails.findall('item'):
                        type = x.find('type')
                        identifiedBy = x.find('identifiedBy')
                        # try:
                        #     prnt(f'type: {type.text}')
                        #     prnt(f'identifiedBy: {identifiedBy.text}')
                        # except Exception as e:
                        #     prnt(str(e))
        err = 5
        prnt('actions::')
        actions = billXML.find('actions')
        if actions:
            prnt('action_url',url)
            previous_dt = None
            if not 'actionHistory' in billU.data:
                billU.data['actionHistory'] = []
            
            for i in actions.findall('item'):
                xml_str = ET.tostring(i, encoding='unicode')
                action_data = xmltodict.parse(xml_str)
                # prnt("action_data",action_data)
                action_data = action_data['item']

                if not billU.extra:
                    billU.extra = {}
                if 'billActions' not in billU.extra:
                    billU.extra['billActions'] = []
                if action_data not in billU.extra['billActions']:
                    billU.extra['billActions'].append(action_data)

                actionChamber = None
                actionDate = i.find('actionDate')
                actionTime = i.find('actionTime')
                # <actionDate>2024-01-31</actionDate>
                # <actionTime>20:33:22</actionTime>
                if actionTime is not None:
                    dt = timezonify('est', datetime.datetime.strptime(f'{actionDate.text}-{actionTime.text}', '%Y-%m-%d-%H:%M:%S'))
                else:
                    dt = timezonify('est', datetime.datetime.strptime(f'{actionDate.text}', '%Y-%m-%d'))
                # prnt('dt',dt)
                x = {'dt':dt_to_string(dt)}
                # try:
                #     actionCode = i.find('actionCode').text
                #     prnt(f'actionDate: {actionDate.text}')
                #     prnt(f'actionCode: {actionCode}')
                #     prnt(f'actionTime: {actionTime.text}')
                # except Exception as e:
                #     prnt(str(e))
                #     actionCode = ''
                
                
                calendarNumber = i.find('calendarNumber')
                if calendarNumber:
                    calendar = calendarNumber.find('calendar')
                    # try:
                    #     prnt(f'calendar: {calendar.text}')
                    # except:
                    #     pass
                
                committees = i.find('committees')
                if committees:
                    for z in committees.findall('item'):
                        systemCode = z.find('systemCode')
                        name = z.find('name')
                        # try:
                        #     prnt(f'name: {name.text}')
                        #     prnt(f'systemCode: {systemCode.text}')
                        # except Exception as e:
                        #     prnt(str(e))

                try:
                    actionText = i.find('text')
                    # prnt('actionText0',actionText)
                    x['text'] = actionText.text
                except Exception as e:
                    prnt('action err 385',str(e))
                    actionText = None
                try:
                    type = i.find('type')
                    x['type'] = type.text
                except:
                    pass

                # prnt('actionText1',actionText)
                sourceSystem = i.find('sourceSystem')
                if sourceSystem:
                    name = sourceSystem.find('name')
                    code = sourceSystem.find('code')
                    if actionText == None:
                        actionText = sourceSystem.find('actionText')
                        # prnt('actionText1.5',actionText)
                    # try:
                    #     # if not distinction or str(distinction) == '\\n':
                    #     #     distinction = code.text
                    #     prnt(f'name: {name.text}')
                    #     prnt(f'code: {code.text}')
                    # except Exception as e:
                    #     prnt('action err 58305',str(e))

                try:
                    distinction = actionText.text
                    actionText = actionText.text
                except Exception as e:
                    prnt('action err 47242',str(e))
                    if i.find('actionCode'):
                        distinction = i.find('actionCode').text
                        actionText = ''
                    elif type:
                        distinction = type.text
                        actionText = ''
                    else:
                        distinction = 'x'
                        actionText = ''

                recordedVotes = i.find('recordedVotes')
                if recordedVotes:
                    for v in recordedVotes.findall('recordedVote'):
                        # prnt('---')
                        rollNumber = v.find('rollNumber')
                        url = v.find('url')
                        chamber = v.find('chamber')
                        congress = v.find('congress')
                        date = v.find('date')
                        sessionNumber = v.find('sessionNumber')
                        # try:
                        #     prnt(f'rollNumber: {rollNumber.text}')
                        #     prnt(f'url: {url.text}')
                        #     prnt(f'chamber: {chamber.text}')
                        #     prnt(f'congress: {congress.text}')
                        #     prnt(f'date: {date.text}')
                        #     prnt(f'sessionNumber: {sessionNumber.text}')
                        # except Exception as e:
                        #     prnt(str(e))

                actionChamber = originChamber
                if actionText:
                    if 'house' in actionText.lower():
                        actionChamber = 'House'
                    elif 'senate' in actionText.lower():
                        actionChamber = 'Senate'
                    elif 'president' in actionText.lower():
                        actionChamber = 'Executive'
                if not bill.DateTime or dt < bill.DateTime:
                    bill.DateTime = dt
                
            if 'billVersions' in billU.data:
                statuses = {'introduced':'Introduced', 'received in the house':'in house', 'passed/agreed to in house':'House',
                            'submitted in house':'in house', 'submitted in senate':'in senate', 'received in the senate':'in senate',
                            'referred to the house':'in house', 'referred to the senate': 'in senate',
                            'passed/agreed to in senate':'Senate', 'resolving differences':'Resolving Differences', 'presented to president':'President', 'vetoed by president':'Vetoed by President',
                            'passed house over veto':'pass house veto', 'passed senate over veto':'pass senate veto', 'the objections of the president to the contrary notwithstanding failed':'Failed to pass over veto', 'became public law':'Law'
                            }
                prnt('current bill versions:\n',billU.data['billVersions'])
                # prnt('actions in reverse:')
                for i in list(reversed(actions.findall('item'))):
                    txt = i.find('text')
                    actionDate = i.find('actionDate')
                    actionTime = i.find('actionTime')
                    if actionTime is not None:
                        dt = timezonify('est', datetime.datetime.strptime(f'{actionDate.text}-{actionTime.text}', '%Y-%m-%d-%H:%M:%S'))
                    else:
                        dt = timezonify('est', datetime.datetime.strptime(f'{actionDate.text}', '%Y-%m-%d'))
                    prnt('dt',dt)
                    if txt is not None:
                        prnt('txt',txt.text)
                        passed_house_veto = False
                        passed_senate_veto = False
                        for key, value in statuses.items():
                            if key in txt.text.lower():
                                prnt('FOUND',key)
                                if value == 'in house':
                                    if bill.Chamber == 'House':
                                        value = 'Introduced'
                                    elif bill.Chamber == 'Senate':
                                        value = 'Senate'
                                elif value == 'in senate':
                                    if bill.Chamber == 'Senate':
                                        value = 'Introduced'
                                    elif bill.Chamber == 'House':
                                        value = 'House'
                                elif value == 'pass house veto':
                                    passed_house_veto = True
                                    value = None
                                    if passed_senate_veto:
                                        value = 'Passed over veto'
                                elif value == 'pass senate veto':
                                    passed_senate_veto = True
                                    value = None
                                    if passed_house_veto:
                                        value = 'Passed over veto'
                                elif value in ['Passed House','Passed Senate','To President','Became Law','Agreed to in House','Agreed to in Senate']:
                                    value = None
                                if value:
                                    # prnt('val',value)
                                    billU.data['Status'] = value
                                    exists = False
                                    for v in billU.data['billVersions']:
                                        # prnt('vversion',v['version'])
                                        if v['version'] == value:
                                            exists = True
                                            v['current'] = True
                                            if 'vetoed' in value.lower() or 'failed' in value.lower():
                                                v['status'] = 'failed'
                                            elif 'law' in value.lower():
                                                v['status'] = 'complete'
                                            else:
                                                v['status'] = 'current'
                                            if not v['started_dt']:
                                                v['started_dt'] = dt_to_string(dt)
                                        elif v['current'] == True:
                                            v['current'] = False
                                            v['status'] = 'passed'
                                            if not v['completed_dt']:
                                                v['completed_dt'] = dt_to_string(dt)
                                    if not exists:
                                        prnt('not exists')
                                        inserted = False
                                        versionHistory = billU.data['billVersions']
                                        billU.data['billVersions'] = []
                                        for v in versionHistory:
                                            if v['status'] in ['passed','failed']:
                                                billU.data['billVersions'].append(v)
                                            else:
                                                if 'vetoed' in value or 'failed' in value:
                                                    status = 'failed'
                                                else:
                                                    status = 'current'
                                                if not inserted:
                                                    billU.data['billVersions'].append({'version':value, 'current':True, 'status':status, 'started_dt':dt_to_string(dt), 'completed_dt':None})
                                                    inserted = True
                                                billU.data['billVersions'].append(v)
                    
        err = 6
        prnt('sponsors::')
        sponsors = billXML.find('sponsors')
        if sponsors:
            billU.data['cosponsors'] = []
            billU.data['sponsor_parties'] = {}
            for i in sponsors.findall('item'):
                bioguideId = i.find('bioguideId')
                fullName = i.find('fullName')
                firstName = i.find('firstName')
                lastName = i.find('lastName')
                middleName = i.find('middleName')
                party = i.find('party')
                state = i.find('state')
                district = i.find('district')
                isByRequest = i.find('isByRequest')
                try:
                    person = Person.objects.filter(GovIden=bioguideId.text, Country_obj=country, Validator_obj__is_valid=True).first()
                    prnt('p',person)
                    prnt('bill.Person_obj',bill.Person_obj,'bill.SponsorCode',bill.SponsorCode)
                    bill.SponsorPersonName = firstName.text + ' ' + lastName.text
                    bill.SponsorCode = bioguideId.text
                    try:
                        bill.Party_obj = Party.objects.filter(ShortName__iexact=party.text, gov_level='Federal', Region_obj=country, Validator_obj__is_valid=True).first()
                    except:
                        pass
                    prnt('bill.Party_obj',bill.Party_obj)
                    if bill.Party_obj:
                        if bill.Party_obj.ShortName not in billU.data['sponsor_parties']:
                            billU.data['sponsor_parties'][bill.Party_obj.ShortName] = {'colr':bill.Party_obj.Color, 'count':1}
                        else:
                            billU.data['sponsor_parties'][bill.Party_obj.ShortName]['count'] += 1
                    if person:
                        try:
                            personU = person.Update_obj
                            bill.Person_obj = person
                            if not bill.Party_obj:
                                bill.Party_obj = Party.objects.filter(id=personU.data['Party_id'], gov_level='Federal', Region_obj=country, Validator_obj__is_valid=True).first()
                        except:
                            pass
                        try:
                            bill.District_obj = District.objects.filter(id=personU.data['District_id'], gov_level='Federal', Region_obj=country, Validator_obj__is_valid=True).first()
                        except:
                            pass
                    if not person:
                        p_name = fullName.text
                        pu = Update.valid_objects.filter(Region_obj=country, pointerKey=ContentType.objects.get_for_model(Person), data__contains={'FullName': p_name}).order_by('-created').first()
                        if pu and pu.Pointer_obj:
                            person = pu.Pointer_obj
                    prnt('person2',person)
                    if person:
                        if person != bill.Person_obj:
                            personU = person.Update_obj
                            if not any(p['obj_id'] == person.id for p in billU.data['cosponsors']):
                                sponsor_dic = {'obj_id':person.id, 'fullName':personU.data['FullName']}
                                if 'Party_id' in personU.data and personU.data['Party_id']:
                                    prty = Party.objects.filter(id=personU.data['Party_id'], Validator_obj__is_valid=True).first()
                                    prnt('prty',prty)
                                    if prty:
                                        sponsor_dic['prty_colr'] = prty.Color
                                billU.data['cosponsors'].append(sponsor_dic)
                                if prty.ShortName not in billU.data['sponsor_parties']:
                                    billU.data['sponsor_parties'][prty.ShortName] = {'colr':prty.Color, 'count':1}
                                else:
                                    billU.data['sponsor_parties'][prty.ShortName]['count'] += 1
                    else:
                        if not any(p['fullName'] == p_name for p in billU.data['cosponsors']):
                            billU.data['cosponsors'].append({'obj_id':None, 'fullName':p_name})
                        

                    # prnt(f'bioguideId: {bioguideId.text}')
                    prnt(f'fullName: {fullName.text}')
                    # prnt(f'firstName: {firstName.text}')
                    # prnt(f'lastName: {lastName.text}')
                    # prnt(f'middleName: {middleName.text}')
                    # prnt(f'party: {party.text}')
                    # prnt(f'state: {state.text}')
                    # prnt(f'district: {district.text}')
                    # prnt(f'isByRequest: {isByRequest.text}')
                except Exception as e:
                    prnt('bill err 5912',str(e))
        err = 7
        prnt('cosponsors::')
        cosponsors = billXML.find('cosponsors')
        if cosponsors:
            if not 'cosponsors' in billU.data:
                billU.data['cosponsors'] = []
            if not 'sponsor_parties' in billU.data:
                billU.data['sponsor_parties'] = {}
            for i in cosponsors.findall('item'):
                bioguideId = i.find('bioguideId')
                fullName = i.find('fullName')
                firstName = i.find('firstName')
                lastName = i.find('lastName')
                middleName = i.find('middleName')
                party = i.find('party')
                state = i.find('state')
                district = i.find('district')
                sponsorshipDate = i.find('sponsorshipDate')
                isOriginalCosponsor = i.find('isOriginalCosponsor')
                try:
                    person = Person.objects.filter(GovIden=bioguideId.text, Country_obj=country, Validator_obj__is_valid=True).first()
                    if not person:
                        p_name = fullName.text
                        pu = Update.valid_objects.filter(Region_obj=country, pointerKey=ContentType.objects.get_for_model(Person), data__contains={'FullName': p_name}).order_by('-created').first()
                        if pu and pu.Pointer_obj:
                            person = pu.Pointer_obj
                    prnt('p',person)
                    if person:
                        if person != bill.Person_obj:
                            personU = person.Update_obj
                            prnt('personU',personU)
                            if not any(p['obj_id'] == person.id for p in billU.data['cosponsors']):
                                sponsor_dic = {'obj_id':person.id, 'fullName':personU.data['FullName']}
                                if 'Party_id' in personU.data and personU.data['Party_id']:
                                    prty = Party.objects.filter(id=personU.data['Party_id'], Validator_obj__is_valid=True).first()
                                    prnt('prty',prty)
                                    if prty:
                                        sponsor_dic['prty_colr'] = prty.Color
                                billU.data['cosponsors'].append(sponsor_dic)
                                if prty.ShortName not in billU.data['sponsor_parties']:
                                    billU.data['sponsor_parties'][prty.ShortName] = {'colr':prty.Color, 'count':1}
                                else:
                                    billU.data['sponsor_parties'][prty.ShortName]['count'] += 1
                    else:
                        if not any(p['fullName'] == p_name for p in billU.data['cosponsors']):
                            billU.data['cosponsors'].append({'obj_id':None, 'fullName':p_name})

                    # prnt(f'bioguideId: {bioguideId.text}')
                    prnt(f'fullName: {fullName.text}')
                    # prnt(f'firstName: {firstName.text}')
                    # prnt(f'lastName: {lastName.text}')
                    # prnt(f'middleName: {middleName.text}')
                    # prnt(f'party: {party.text}')
                    # prnt(f'state: {state.text}')
                    # prnt(f'district: {district.text}')
                    # prnt(f'sponsorshipDate: {sponsorshipDate.text}')
                    # prnt(f'isOriginalCosponsor: {isOriginalCosponsor.text}')
                except Exception as e:
                    prnt('bill err 6745',str(e))
        err = 8
        prnt('cboCostEstimates::')
        cboCostEstimates = billXML.find('cboCostEstimates')
        if cboCostEstimates:
            for i in cboCostEstimates.findall('item'):
                pubDate = i.find('pubDate')
                title = i.find('title')
                url = i.find('url')
                description = i.find('description')
                # try:
                #     prnt(f'pubDate: {pubDate.text}')
                #     prnt(f'title: {title.text}')
                #     prnt(f'url: {url.text}')
                #     prnt(f'description: {description.text}')
                # except Exception as e:
                #     prnt(str(e))
                
                xml_str = ET.tostring(i, encoding='unicode')
                cboCostEstimates_data = xmltodict.parse(xml_str)
                # prntn("cboCostEstimates_data",cboCostEstimates_data)
                if 'item' in cboCostEstimates_data:
                    cboCostEstimates_data = cboCostEstimates_data['item']

                if not billU.extra:
                    billU.extra = {}
                if 'cboCostEstimates' not in billU.extra:
                    billU.extra['cboCostEstimates'] = []
                if cboCostEstimates_data not in billU.extra['cboCostEstimates']:
                    billU.extra['cboCostEstimates'].append(cboCostEstimates_data)
        err = 9
        prnt('laws::')
        laws = billXML.find('laws')
        if laws:
            for i in laws.findall('item'):
                type = i.find('type')
                number = i.find('number')
                # try:
                #     prnt(f'type: {type.text}')
                #     prnt(f'number: {number.text}')
                # except Exception as e:
                #     prnt(str(e))

                xml_str = ET.tostring(i, encoding='unicode')
                laws_data = xmltodict.parse(xml_str)
                # prntn("laws_data",laws_data)
                if 'item' in laws_data:
                    laws_data = laws_data['item']

                if not billU.extra:
                    billU.extra = {}
                if 'laws' not in billU.extra:
                    billU.extra['laws'] = []
                if laws_data not in billU.extra['laws']:
                    billU.extra['laws'].append(laws_data)
        err = 10
        prnt('policyArea::')
        policyArea = billXML.find('policyArea')
        if policyArea:
            if 'subjects' not in billU.data:
                billU.data['subjects'] = []
            name = policyArea.find('name')
            try:
                if name.text not in billU.data['subjects']:
                    billU.data['subjects'].append(name.text)
                # prnt(f'name: {name.text}')
            except Exception as e:
                prnt('bill err 07965', str(e))
        err = 11
        prnt('subjects::')
        subjects = billXML.find('subjects')
        if subjects:
            if 'subjects' not in billU.data:
                billU.data['subjects'] = []
            legislativeSubjects = subjects.find('legislativeSubjects')
            if legislativeSubjects:
                for i in legislativeSubjects.findall('item'):
                    name = i.find('name')
                    try:
                        if name.text not in billU.data['subjects']:
                            billU.data['subjects'].append(name.text)
                        # prnt(f'name: {name.text}')
                    except Exception as e:
                        prnt('bill err 1932',str(e))
        err = 12
        prnt('summaries::')
        summaries = billXML.find('summaries')
        if summaries:
            # <summary>
            # <versionCode>00</versionCode>
            # <actionDate>2025-03-21</actionDate>
            # <actionDesc>Introduced in House</actionDesc>
            # <updateDate>2025-06-18T16:20:30Z</updateDate>
            # <cdata>
            # <text><p><strong>Wastewater Infrastructure Pollution Prevention and Environmental Safety Act or the WIPPES Act</strong></p><p>This bill requires entities responsible for the labeling or retail packaging of certain premoistened, nonwoven wipes (e.g., baby wipes, cleaning wipes, or personal care wipes) to label such products clearly and conspicuously with the phrase <em>Do Not Flush</em> and accompanying symbol as depicted under specified industry guidelines.</p><p>The Federal Trade Commission must enforce these requirements&nbsp;and may issue regulations to implement the bill.&nbsp;</p></text>
            # </cdata>
            # </summary>
            for s in summaries.findall('summary')[-1:]:
                versionCode = s.find('versionCode')
                actionDate = s.find('actionDate')
                actionDesc = s.find('actionDesc')
                updateDate = s.find('updateDate')
                cdata = s.find('cdata')
                try:
                    text = cdata.find('text')
                    prnt(f'bill summary2: {text}')
                    billU.data['Summary'] = text.text.replace(f'<p><strong>{x}</strong></p>','')
                    dt = timezonify('est', datetime.datetime.strptime(f'{actionDate.text}', '%Y-%m-%d'))
                    billU.data['summary_dt'] = dt_to_string(dt)
                    # prnt(f'actionDesc: {actionDesc}')
                    billU.data['summary_description'] = actionDesc.text
                    # prnt(f'updateDate: {updateDate.text}')
                except Exception as e:
                    prnt('bill summary err 587',str(e))
        err = 13
        prnt('title::')
        title = billXML.find('title')
        bill.Title = title.text
        if 'Summary' in billU.data and bill.Title in billU.data['Summary']:
            billU.data['Summary'] = billU.data['Summary'].replace(f'<p><strong>{bill.Title}</strong></p>','')
        titles = billXML.find('titles')
        if titles:
            for i in titles.findall('item'):
                titleType = i.find('titleType')
                title = i.find('title')
                chamberCode = i.find('chamberCode')
                chamberName = i.find('chamberName')
                billTextVersionName = i.find('billTextVersionName')
                billTextVersionCode = i.find('billTextVersionCode')
                # try:
                #     prnt(f'titleType: {titleType.text}')
                #     prnt(f'title: {title.text}')
                #     # prnt(f'billTextVersionName: {billTextVersionName.text}')
                #     # prnt(f'billTextVersionCode: {billTextVersionCode.text}')
                #     # prnt(f'chamberCode: {chamberCode.text}')
                #     # prnt(f'chamberName: {chamberName.text}')
                # except Exception as e:
                #     prnt('bill err 5204',str(e))
        err = 14  
        prnt('amendments::')
        amendments = billXML.find('amendments')
        if amendments:
            for a in amendments.findall('amendment'):
                number = a.find('number')
                congress = a.find('congress')
                type = a.find('type')
                description = a.find('description')
                updateDate = a.find('updateDate')
                latestAction = a.find('latestAction')

                xml_str = ET.tostring(a, encoding='unicode')
                amendments_data = xmltodict.parse(xml_str)
                # prntn("amendments_data",amendments_data)
                if 'item' in amendments_data:
                    amendments_data = amendments_data['item']

                if not billU.extra:
                    billU.extra = {}
                if 'amendments' not in billU.extra:
                    billU.extra['amendments'] = []
                if amendments_data not in billU.extra['amendments']:
                    billU.extra['amendments'].append(amendments_data)

                if latestAction:
                    actionDate = latestAction.find('actionDate')
                    text = latestAction.find('text')
                    actionTime = latestAction.find('actionTime')
                    # try:
                    #     # prnt(f'number: {number.text}')
                    #     # prnt(f'congress: {congress.text}')
                    #     # prnt(f'type: {type.text}')
                    #     # prnt(f'description: {description.text}')
                    #     # prnt(f'updateDate: {updateDate.text}')
                    #     prnt(f'latestAction: {latestAction.text}')
                    #     prnt(f'actionDate: {actionDate.text}')
                    #     prnt(f'text: {text.text}')
                    #     # prnt(f'actionTime: {actionTime.text}')
                    # except Exception as e:
                    #     prnt('bill err 6725', str(e))

                sponsors = a.find('sponsors')
                if sponsors:
                    for i in sponsors.findall('item'):
                        bioguideId = i.find('bioguideId')
                        fullName = i.find('fullName')
                        firstName = i.find('firstName')
                        lastName = i.find('lastName')
                        middleName = i.find('middleName')
                        party = i.find('party')
                        state = i.find('state')
                        district = i.find('district')
                        try:
                            prnt(f'bioguideId: {bioguideId.text}')
                            prnt(f'fullName: {fullName.text}')
                            # prnt(f'firstName: {firstName.text}')
                            # prnt(f'lastName: {lastName.text}')
                            # prnt(f'middleName: {middleName.text}')
                            # prnt(f'party: {party.text}')
                            # prnt(f'state: {state.text}')
                            # prnt(f'district: {district.text}')
                        except Exception as e:
                            prnt('bill err 5678', str(e))

                submittedDate = a.find('submittedDate')
                chamber = a.find('chamber')
                # try:
                #     prnt(f'submittedDate: {submittedDate.text}')
                #     prnt(f'chamber: {chamber.text}')
                # except Exception as e:
                #     prnt(str(e))

                amendedBill = a.find('amendedBill')
                if amendedBill:
                    congress = amendedBill.find('congress')
                    type = amendedBill.find('type')
                    originChamber = amendedBill.find('originChamber')
                    originChamberCode = amendedBill.find('originChamberCode')
                    number = amendedBill.find('number')
                    title = amendedBill.find('title')
                    updateDateIncludingText = amendedBill.find('updateDateIncludingText')
                    # try:
                    #     prnt(f'congress: {congress.text}')
                    #     prnt(f'type: {type.text}')
                    #     prnt(f'originChamber: {originChamber.text}')
                    #     prnt(f'originChamberCode: {originChamberCode.text}')
                    #     prnt(f'number: {number.text}')
                    #     prnt(f'title: {title.text}')
                    #     prnt(f'updateDateIncludingText: {updateDateIncludingText.text}')
                    # except Exception as e:
                    #     prnt(str(e))

                links = a.find('links')
                if links:
                    for link in links.findall('link'):
                        # prnt('---')
                        name = link.find('name')
                        url = link.find('url')
                        # try:
                        #     prnt(f'name: {name.text}')
                        #     prnt(f'url: {url.text}')
                        # except Exception as e:
                        #     prnt(str(e))

                actions = a.find('actions')
                if actions:
                    count = actions.find('count')
                    for action in actions.findall('actions'):
                        for i in action.findall('item'):
                            actionDate = i.find('actionDate')
                            actionTime = i.find('actionTime')
                            text = i.find('text')
                            type = i.find('type')
                            try:
                                actionCode = i.find('actionCode').text
                                prnt(f'actionDate: {actionDate.text}')
                                # prnt(f'actionTime: {actionTime.text}')
                                # prnt(f'actionCode: {actionCode}')
                                # prnt(f'text: {text.text}')
                                prnt(f'type: {type.text}')
                            except Exception as e:
                                prnt('bill err 3592', str(e))
                                actionCode = ''

                            sourceSystem = i.find('sourceSystem')
                            if sourceSystem:
                                name = sourceSystem.find('name')
                                code = sourceSystem.find('code')
                                # try:
                                #     prnt(f'name: {name.text}')
                                #     prnt(f'systemCode: {systemCode.text}')
                                # except Exception as e:
                                #     prnt(str(e))
        err = 15
        prnt('textVersions::')
        def get_text(bill, billU, soup):
            prnt('gettext')
            import hashlib

            def section_code(text, length=7):
                # return as 7 char unique string
                hash_object = hashlib.sha256(text.encode())
                hash_int = int(hash_object.hexdigest(), 16)
                return str(hash_int % 10**7).zfill(length)
            
            body = soup.find('body')
            finalText = str(body)
            for s in body.find_all(class_='lbexTocSectionOLC'):
                finalText.replace(str(s),'')
            if not billU.extra:
                billU.extra = {}

            toc_d = []
            for s in body.find_all(class_='lbexHangWithMargin'):
                if 'SECTION ' in s.text or 'SEC. ' in s.text:
                    code = section_code(s.text)
                    x = str(s).find('class="')+len('class="')
                    m = str(s)[:x] + code + ' ' + str(s)[x:]
                    finalText = finalText.replace(str(s), m)
                    toc_d.append({s.text : {'code':code, 'html':m}})

            if toc_d == []:
                for s in body.find_all(class_='lbexHeaderAppropIntermediate'):
                    code = section_code(str(s))
                    x = str(s).find('class="')+len('class="')
                    m = str(s)[:x] + code + ' ' + str(s)[x:]
                    finalText = finalText.replace(str(s), m)
                    toc_d.append({s.text : {'code':code, 'html':m}})
            if toc_d == []:
                for s in body.find_all(class_='lbexTocSectionIRCBold'):
                    code = section_code(str(s))
                    x = str(s).find('class="')+len('class="')
                    m = str(s)[:x] + code + ' ' + str(s)[x:]
                    finalText = finalText.replace(str(s), m)
                    toc_d.append({s.text : {'code':code, 'html':m}})

            if finalText:
                from legis.models import BillText
                from utils.locked import hash_obj_id
                bt = BillText(pointerId=bill.id)
                bt.text = bt.store_text(finalText)
                bt_id = hash_obj_id(bt)
                
                if not BillText.objects.filter(id=bt_id, Validator_obj__is_valid=True).exists():
                    b = BillText.objects.filter(id=bt_id, Validator_obj__is_valid=True).defer('text').first()
                    if b:
                        billText = b
                    else:
                        billText = bt
                        
                    billText = bt
                    billText.data['TextNav'] = toc_d
            else:
                billText = None

            billU.data['has_text'] = True
            prnt('billText',billText)
            return bill, billU, billText

        textVersions = billXML.find('textVersions')
        if textVersions:
            textFound = False
            for i in textVersions.findall('item'):
                if textFound:
                    break
                actionType = i.find('type')
                date = i.find('date')
                # <type>Engrossed Amendment Senate</type>
                # <date>2020-11-16T05:00:00Z</date>
                dt = None
                if billU.extra and 'bill_text_version' in billU.extra and actionType is not None and billU.extra['bill_text_version'] == actionType.text:
                    textFound = True
                    break
                try:
                    dt = timezonify('est', datetime.datetime.strptime(date.text, "%Y-%m-%dT%H:%M:%SZ"))
                    prnt(f'actionType: {actionType.text}')
                    prnt(f'date: {date.text}')
                except Exception as e:
                    prnt('bills err 345',str(e))
                formats = i.find('formats')
                if formats:
                    for x in formats.findall('item'):
                        url = x.find('url')
                        try:
                            prnt('getting text', url.text)

                            if not driver:
                                script_test_error(special, "opening browser")
                                driver = open_browser()
                            driver.get(url.text)
                            prnt('url loaded')
                            element_present = EC.presence_of_element_located((By.TAG_NAME, 'body'))
                            WebDriverWait(driver, 10).until(element_present)
                            soup = BeautifulSoup(driver.page_source, 'html.parser')
                            bill, billU, billText = get_text(bill, billU, soup)
                            prnt(f'url: {url.text}')
                            if billText: 
                                billText.data['url'] = url.text
                                do_save = False
                                if billText.id == '0' or not billText.signed or not billText.Validator_obj:
                                    do_save = True
                                if dt is not None:
                                    if 'date' not in billText.data or billText.data['date'] != dt_to_string(dt):
                                        billText.data['date'] = dt_to_string(dt)
                                        do_save = True
                                if actionType is not None:
                                    if 'bill_text_version' not in billText.data or billText.data['bill_text_version'] != actionType.text:
                                        billText.data['bill_text_version'] = actionType.text
                                        do_save = True
                                    billU.extra['bill_text_version'] = actionType.text
                                if do_save:
                                    billText.save(region=country)
                                    log.updateShare(billText)
                                textFound = True
                            break
                        except Exception as e:
                            prnt('bill text err 553', str(e))
                            # logError('failed to get_text', code='65434', func='add_bill', extra={'err':str(e), 'url.text':url.text})
        updated_bill = False
        prnt('latestaction::')
        latestAction = billXML.find('latestAction')
        if latestAction:
            actionDate = latestAction.find('actionDate')
            text = latestAction.find('text')
            if text is not None:
                if 'LatestBillEvent' in billU.data and billU.data['LatestBillEvent'] != text.text:
                    updated_bill = True
                billU.data['LatestBillEvent'] = text.text
            if actionDate is not None:
                dt = timezonify('est', datetime.datetime.strptime(actionDate.text, '%Y-%m-%d'))
                billU.data['LatestBillEventDateTime'] = dt_to_string(dt)
                billU.DateTime = dt
            # try:
            #     prnt(f'actionDate: {actionDate.text}')
            #     prnt(f'text: {text.text}')
            # except Exception as e:
            #     prnt('bill err 3304', str(e))
        err = 16
        bill, billU, bill_is_new, log = save_and_return(bill, billU, log)
        if new_bill and bill.Person_obj:
            script_test_error(special, 'send alerts')
            notification, notificationU, notification_is_new = get_model_and_update('Notification', Title=f'{bill.Person_obj.get_field("FullName")} has sponsored bill {bill.NumberCode}', Link=str(bill.get_absolute_url()), targetUsers={'follow_person' : bill.Person_obj.id}, pointerId=bill.id, Country_obj=country, Region_obj=country, Chamber=bill.Chamber, networkChainType=gov.id)
            notification, notificationU, notification_is_new, log = save_and_return(notification, notificationU, log)
        err = 17
        try:
            if updated_bill or new_bill:
                script_test_error(special, 'send alerts 2')
                if len(bill.Title) > 65:
                    title = bill.Title[:65] + '...'
                else:
                    title = bill.Title
                if billU.data['Status'] != 'Became Law':
                    if bill.Person_obj:
                        person_id = bill.Person_obj.id
                    else:
                        person_id = bill.SponsorCode
                    if UserData.objects.filter(Q(follow_topics__contains=bill.id)|Q(follow_topics__contains=person_id)).count() > 0:
                        notification, notificationU, notification_is_new = get_model_and_update('Notification', Title=f'Bill {bill.NumberCode} updated - {title}', Link=str(bill.get_absolute_url()), targetUsers={'follow_bill' : bill.id, 'follow_person' : person_id}, pointerId=bill.id, Country_obj=country, Region_obj=country, Chamber=bill.Chamber, networkChainType=gov.id)
                        notification, notificationU, notification_is_new, log = save_and_return(notification, notificationU, log)
                elif 'Became Law' in billU.data['Status']:
                    notification, notificationU, notification_is_new = get_model_and_update('Notification', Title=f'Bill {bill.NumberCode} has become Law - {title}', Link=str(bill.get_absolute_url()), targetUsers={'all_in_country' : country.id}, pointerId=bill.id, Country_obj=country, Region_obj=country, Chamber=bill.Chamber, networkChainType=gov.id)
                    notification, notificationU, notification_is_new, log = save_and_return(notification, notificationU, log)
        except Exception as e:
            prnt('create notify fail43',str(e))
            # logError(str(e), code='875167', func='add_bill')
            pass
        err = 'fini'
        prnt('bill done')
    except Exception as e:
        prnt('add_bill fail 453',str(e))
        # logError(e, code='68264', func=ref_func, region=country, extra={'url':url,'err':str(err)})

    return log, driver, driver_service


# not used
def get_live_house_debates(special=None, dt=now_utc(), iden=None):
    func = 'get_live_house_debates'
    log = []
    country = Region.supported_objects.filter(nameType='Country', Name='USA').first()
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = Government.objects.filter(Country_obj=country, gov_level='Federal').first()
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')

    url = 'https://live.house.gov/'

    try:
        driver = open_browser(url)

        element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="activity-table"]/tbody'))
        WebDriverWait(driver, 10).until(element_present)

        soup = BeautifulSoup(driver.page_source, 'html.parser')    
    except Exception as e:
        prnt(str(e))

    # close_browser(driver)

    dt = soup.find('span', {'class':'display-date'})
    # WEDNESDAY, JANUARY 10, 2024
    today = timezonify('est', datetime.datetime.strptime(dt.text, '%A, %B %d, %Y'))
    # utc_datetime = pytz.utc.localize(today)
    # est = pytz.timezone('US/Eastern')
    # est_today = utc_datetime.astimezone(est)

    prnt(today)
    
    table = soup.find('table', {'id':'activity-table'})
    body = table.find('tbody')
    trs = body.find_all('tr')
    A = None
    started = False
    ended = False
    position = 0
    for tr in reversed(trs):
        position += 1
        tds = tr.find_all('td')
        timeText = tds[0].text
        # 10:00:09 AM
        item_time = timezonify('est', datetime.datetime.strptime(dt.text + '/' + timeText, '%A, %B %d, %Y/%I:%M:%S %p'))
        billText = tds[1].text
        content = tds[2].text
        prnt(item_time)
        # prnt(billText)
        # prnt(content)
        # prnt()
        if not A:
            A = Agenda.objects.filter(DateTime__gte=date, DateTime__lt=today + datetime.timedelta(days=1), Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country).first()
            if A:
                A, Au, A_is_new = get_model_and_update('Agenda', obj=A)
            else:
                A, Au, A_is_new = get_model_and_update('Agenda', DateTime=today, Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country)
                if A_is_new:
                    A, Au, A_is_new, log = save_and_return(A, Au, log)
                # Au.data['CurrentStatus'] = 'Adjourned'

        if 'convened' in content.lower():
            started = True
            Au.data['CurrentStatus'] = 'In Session'
        elif 'adjourn' in content.lower():
            ended = True
            Au.data['CurrentStatus'] = 'Adjourned'
            Au.data['EndDateTime'] = item_time
            # A.save()

        agendaItem, agendaItemU, agendaItem_is_new = get_model_and_update('AgendaItem', position=position, Agenda_obj=A, DateTime=item_time, Country_obj=country, Government_obj=gov, Chamber=A.Chamber, Region_obj=country)

        if billText:
            bill = Bill.objects.filter(NumberCode=billText, Government_obj=gov).first()
            if bill:
                agendaItem.Bill_obj = bill
        agendaItem, agendaItemU, agendaItem_is_new, log = save_and_return(agendaItem, agendaItemU, log)
        
    
    meeting = Meeting.objects.filter(Agenda_obj=A).first()
    if meeting:
        meeting, meetingU, meeting_is_new = get_model_and_update('Meeting', obj=meeting)
    if started:
        if not meeting or meeting and meetingU.data['completed_model'] == False:
            text = driver.find_element(By.XPATH, '//*[@id="transcript"]')
            text.click()
            prnt('----clicked')
            element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="transcript-table"]/tbody'))
            WebDriverWait(driver, 10).until(element_present)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            close_browser(driver)
            dt = soup.find('span', {'class':'display-date'})
            # WEDNESDAY, JANUARY 10, 2024
            date = timezonify('est', datetime.datetime.strptime(dt.text, '%A, %B %d, %Y'))
            prnt(date)
            table = soup.find('table', {'id':'transcript-table'})
            body = table.find('tbody')
            trs = body.find_all('tr')
            recognizedState = None
            theSpeaker = None
            meeting_terms = {}
            for tr in trs:
                ItemId = tr['data-uniqueid']
                tds = tr.find_all('td')
                name = tds[0].text
                timeText = tds[1].text
                # 10:00:09 AM
                date_time = timezonify('est', datetime.datetime.strptime(dt.text + '/' + timeText, '%A, %B %d, %Y/%I:%M:%S %p'))
                content = tds[2].text.replace('[...]', '')
                if 'RECOGNIZES' in content or 'RECOGNIZED' in content or 'RECOGNITION' in content:
                    for state in state_list.values():
                        if state.upper() in content:
                            recognizedState = state
                            break

                if not meeting:
                    meeting, meetingU, meeting_is_new = get_model_and_update('Meeting', Agenda_obj=A, meeting_type='Debate', DateTime=date_time, Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country)
                    if meeting_is_new:
                        meetingU.data['completed_model'] = False
                        day = datetime.datetime.strftime(datetime.datetime.strptime(dt.text, '%A, %B %d, %Y'), '%Y-%B-%d')
                        meeting.GovPage = url + '?date=%s' %(day)
                        meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)

                prnt(date_time)
                person = None
                first_name = None
                last_name = None
                title = None
                if '. ' in name:
                    a = name.find('. ')+2
                    last_name = name[a:]
                else:
                    names = name.split()
                    last_name = names[-1]
                    first_name = names[0]
                # elif 'The Clerk' in name or 'The Speaker Pro Tempore' in name or 
                if 'The Speaker' in name:
                    title = 'The Speaker'
                    if not theSpeaker:
                        speakerRs = Role.objects.filter(gov_level='Federal', Position='Speaker of the House', Country_obj=country)
                        rUpdate = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Role), pointerId__in=[i.id for i in speakerRs], data__contains='"Current": true').first()
                        if rUpdate:
                            theSpeaker = speakerRs.filter(id=rUpdate.pointerId).first().Person_obj
                        else:
                            theSpeaker = None
                    person = theSpeaker

                if not person:
                    if first_name:
                        r = Role.objects.filter(Position='Congressional Representative').filter(Person_obj__LastName__icontains=last_name, Person_obj__FirstName__icontains=first_name).order_by('-created')
                    else:
                        r = Role.objects.filter(Position='Congressional Representative').filter(Person_obj__LastName__icontains=last_name).order_by('-created')
                    if r.count() > 1:
                        rU = None
                        if recognizedState:
                            refined_rs = r.filter(ProvState_obj__Name=recognizedState, Country_obj=country)
                            rU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Role), pointerId__in=[i.id for i in refined_rs], data__contains='"Current": true').first()
                        else:
                            refined_rs = r.filter(Country_obj=country)
                            rU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Role), pointerId__in=[i.id for i in refined_rs], data__contains='"Current": true', Country_obj=country).first()
                        if rU:
                            person = refined_rs.filter(id=rU.pointerId).first().Person_obj
                        else:
                            person = r[0].Person_obj
                    elif r.count() == 1:
                        person = r[0].Person_obj

                    else:
                        personName = name
                if person:
                    personName = person.FullName

                statement, statementU, statement_is_new = get_model_and_update('Statement', Content=content, PersonName=personName, ItemId=ItemId, Person_obj=person, DateTime=date_time, Meeting_obj=meeting, Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country)
                statement.order = ItemId
                if statement_is_new:
                    statement, statementU, statement_is_new, log = save_and_return(statement, statementU, log)
                
                
            meetingU.data['has_transcript'] = True
            meetingU = meeting.apply_terms(meetingU=meetingU)
            if Au.data['CurrentStatus'] ==' Adjourned':
                meetingU.data['completed_model'] = True
            meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)
    try:
        close_browser(driver)
    except:
        pass
    return finishScript(log, gov, special)


def add_house_rollcall(motion, motionU, motion_is_new, bill, country, log):
    func = 'add_house_rollcall'
    prnt(f'--{func} USA', now_utc())
    motion, motionU, motion_is_new, log = save_and_return(motion, motionU, log)
    url = motion.GovUrl
    try:
        r = requests.get(url)
    except Exception as e:
        prnt('add_house_rollcall fail',str(e))
        r = None
        # logEvent('add_house_rollcall FAIL 29482: ' + country.Name + '/' + str(e), log_type='Errors')
    if r:
        soup = BeautifulSoup(r.content, 'html.parser')

        section = soup.find('section', {'class':'content'})
        detail = section.find('h1', {'id':'pageDetail'})
        h1 = detail.text
        x = h1.find('Roll Call ')+len('Roll Call ')
        z = h1[x:].find(' | ')
        RC_num =h1[x:x+z]
        prnt('RC_num',RC_num)
        span = detail.find('span', {'class':'legisNum'})

        panel = soup.find('div', {'class':'panel'})
        detail = panel.find('div', {'class':'detailPage'})
        first_col = detail.find('div',{'class':'roll-call-first-col'})
        first = first_col.find('div', {'class':'first-row'}).text
        prnt('first',first)
        '''

                                    Jul 10, 2024, 05:22 PM 
                                | 
        118th Congress, 2nd Session                '''
        
        q = first.find('|')
        w = first[:q].strip()
        # prnt(w)
        date_time = timezonify('est', datetime.datetime.strptime(w, '%b %d, %Y, %I:%M %p'))
        prnt('z',z)

        first_row = first_col.find('p', {'class':'roll-call-first-row'}).text
        x = first_row.find('Vote Question: ')+len('Vote Question: ')
        vote_question = first_row[x:]

        descriptions = first_col.find_all('p',{'class':'roll-call-description'})
        vote_type = descriptions[1].text
        x = vote_type.find('Vote Type: ')+len('Vote Type: ')
        vType = vote_type[x:]
        prnt('vType',vType)
        status = descriptions[2].text
        x = status.find('Status: ')+len('Status: ')
        result = status[x:]
        prnt('result',result)
        motion.DateTime = date_time
        motion.DecisionType = vType
        
        all_votes = soup.find('div', {'class':'all-votes'})
        tbody = all_votes.find('tbody', {'id':'member-votes'})
        if tbody:
            trs = tbody.find_all('tr')
            yeas = 0
            nays = 0
            present = 0
            np = 0
            unknown = 0
            total = 0
            result_data = {'Parties':[], 'Votes':[], 'PartyData':{}}
            try:
                for tr in trs:
                    skip = tr.find('td', {'id':'nomatch'})
                    if skip:
                        pass
                    else:
                        a = tr.find('a', {'class':'library-link'})
                        prnt("a['href']",a['href'])
                        if 'members/' in a['href'].lower():
                            x = a['href'].lower().rfind('members/')+len('members/')
                            member_code = a['href'][x:]
                        elif '=' in a['href']:
                            x = a['href'].rfind('=')
                            member_code = a['href'][x+1:]
                        else:
                            member_code = a['href'][-7:]
                        prnt('member_code',member_code)
                        memberName = tr.find('td', {'data-label':'member'}).text
                        partyName = tr.find('td', {'data-label':'party'}).text
                        found = False
                        for i in result_data['Parties']:
                            if i['Name'] == partyName:
                                i['Count'] += 1
                                found = True
                                break
                        if not found:
                            result_data['Parties'].append({'Name':partyName, 'Count':1})
                        stateName = tr.find('td', {'data-label':'state'}).text
                        p = Person.objects.filter(GovIden__iexact=member_code, Country_obj=country, Validator_obj__is_valid=True).first()
                        person, personU, person_is_new = get_model_and_update('Person', obj=p)
                        if person and personU:
                            prnt('person,', person)
                            vote, voteU, vote_is_new = get_model_and_update('RepVote', Motion_obj=motion, Person_obj=person, PersonFullName=f'{personU.data["LastName"]}, {personU.data["FirstName"]}', ConstituencyProvStateName=stateName, CaucusName=partyName, Chamber='House', Country_obj=country, Government_obj=motion.Government_obj, Region_obj=country)
                            if 'District_id' in personU.data:
                                vote.District_obj = District.objects.filter(id=personU.data['District_id'], Validator_obj__is_valid=True).first()
                        else:
                            vote, voteU, vote_is_new = get_model_and_update('RepVote', Motion_obj=motion, PersonFullName=memberName, ConstituencyProvStateName=stateName, CaucusName=partyName, Chamber='House', Country_obj=country, Government_obj=motion.Government_obj, Region_obj=country)
                        prnt('vote:',vote)
                        vote.Party_obj = Party.objects.filter(Q(Name=partyName)|Q(AltName=partyName)|Q(ShortName=partyName), Validator_obj__is_valid=True).first()
                        vote.Chamber = 'House'
                        vote.DateTime = date_time
                        vote.PersonId = member_code
                        vote.IsVoteNay = False
                        vote.IsVoteYea = False
                        vote.IsVotePresent = False
                        vote.IsVoteAbsent = False
                        voteValue = tr.find('td', {'data-label':'vote'}).text
                        vote.VoteValue = voteValue
                        if voteValue.lower() == 'no' or voteValue.lower() == 'nay':
                            vote.IsVoteNay = True
                            nays += 1
                        elif voteValue.lower() == 'aye' or voteValue.lower() == 'yea':
                            vote.IsVoteYea = True
                            yeas += 1
                        elif voteValue.lower() == 'present':
                            vote.IsVotePresent = True
                            present += 1
                        elif voteValue.lower() == 'not voting':
                            vote.IsVoteAbsent = True
                            np += 1
                        else:
                            unknown += 1
                        found = False
                        for i in result_data['Votes']:
                            if i['Vote'] == voteValue:
                                i['Count'] += 1
                                found = True
                                break
                        if not found:
                            result_data['Votes'].append({'Vote':voteValue, 'Count':1})
                        total += 1
                        vote, voteU, vote_is_new, log = save_and_return(vote, voteU, log)
                motion.Yeas = yeas
                motion.Nays = nays
                motion.Present = present
                motion.Absent = np
                motion.TotalVotes = total
                motion.result_data = result_data
                prnt('result_data:',result_data)
                
                for i in result_data['Parties']:
                    party_name = i['Name']
                    count = i['Count']
                    party = Party.objects.filter(Country_obj=country, Region_obj=country, gov_level='Federal').filter(Q(Name=party_name)|Q(AltName=party_name), Validator_obj__is_valid=True).first()
                    if party:
                        i['short'] = party.ShortName
                        i['Color'] = party.Color
                        i['obj_id'] = party.id
                sorted_votes = sorted(result_data['Votes'], key=lambda item: item['Count'], reverse=True)
                result_data['Votes'] = sorted_votes
                sorted_parties = sorted(result_data['Parties'], key=lambda item: item['Count'], reverse=True)
                result_data['Parties'] = sorted_parties
                prnt('yeas',yeas)
                prnt('nays',nays)
                prnt('present',present)
                prnt('np',np)
                prnt('unknown',unknown)
                prnt('total',total)
                motion.Result = result
                motion.Subject = vote_question
                if bill:
                    motion.billCode = bill.NumberCode
                    motion.Bill_obj = bill
                motion.is_official = True
                time.sleep(2)
            except Exception as e:
                prnt('vote fail:',str(e))
                # logEvent(f'add_house_rollcall FAIL {str(e)}', region=country, code='6532', func=func, log_type='Errors')
                time.sleep(2)
        motion, motionU, motion_is_new, log = save_and_return(motion, motionU, log)
    return log

def get_house_rollcalls_us(special=None, dt=None, iden=None, target={}, job_dt=None, task=None, as_rq=True):
    func = 'get_house_rollcalls_us'
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    task = declare_var(task, 1)
    country = Region.supported_objects.filter(nameType='Country', Name='USA', Validator_obj__is_valid=True).first()
    if not job_dt:
        job_dt = dt
    log = create_share_object(func, country, special=special, dt=dt, iden=iden, job_dt=job_dt, task=task)
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, extra=target, log_type='Tasks')
    if target and 'url' in target and 'motion_num' in target:
        if 'gov_id' in target:
            gov = Government.objects.filter(id=target['gov_id'], Validator_obj__is_valid=True).first()
        else:
            gov = Government.objects.filter(Country_obj=country, Region_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
        if not gov or not country:
            prnt('gov',gov,'country',country)
            return finishScript(log, gov, special)
        bill = None
        if 'bill_id' in target:
            bill = Bill.objects.filter(id=target['bill_id'], Validator_obj__is_valid=True).first()
        motion, motionU, motion_is_new = get_model_and_update('Motion', VoteNumber=target['motion_num'], GovUrl=target['url'], Chamber='House', Country_obj=country, Region_obj=country)
        if motion_is_new or not motion.Result:
            motion.Government_obj = gov
            log = add_house_rollcall(motion, motionU, motion_is_new, bill, country, log)

    else:
        proceed = True
        gov = Government.objects.filter(Country_obj=country, Region_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
        if not gov and country:
            return finishScript(log, gov, special)
        if not gov.menuItem_array or 'RollCalls' not in gov.menuItem_array:
            if not gov.signed:
                gov.add_menu_item('RollCalls')
            else:
                if not modded_gov:
                    modded_gov = gov.propose_modification()
                modded_gov.add_menu_item('RollCalls')
                log.updateShare(modded_gov)

        motion = Motion.objects.filter(Country_obj=country, Chamber='House', DateTime__gte=dt-datetime.timedelta(hours=24), Validator_obj__is_valid=True).exclude(TotalVotes=0).values('id', 'TotalVotes').first()

        if special or not motion or motion['TotalVotes'] > RepVote.objects.filter(Motion_obj__id=motion['id'], Validator_obj__is_valid=True).count():
            starting_url = 'https://clerk.house.gov/Votes'
            try:
                driver = open_browser(starting_url)

                element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="votes"]'))
                WebDriverWait(driver, 10).until(element_present)

                soup = BeautifulSoup(driver.page_source, 'html.parser')
            except Exception as e:
                prnt('house roll call fail 3032',str(e))
                proceed = False
                # logEvent(str(e)[:100], region=country, code='09751', func=func, extra={})
            if proceed:
                section = soup.find('section', {'class':'content'})
                currentCongress = section.find('div', {'id':'currentCongress'}).text.replace('st','').replace('nd','').replace('rd','').replace('th','')
                currentSession = section.find('div', {'id':'currentSession'}).text.replace('st','').replace('nd','').replace('rd','').replace('th','')

                gov, govU, gov_is_new = get_model_and_update('Government', Country_obj=country, gov_level='Federal', GovernmentNumber=int(currentCongress), SessionNumber=int(currentSession), Region_obj=country)
                if gov_is_new:
                    from utils.models import round_time
                    gov.StartDate = timezonify('est', round_time(dt=now_utc(), dir='down', amount='day'))
                    gov.migrate_data()
                    gov.LogoLinks = gov_logo_links
                    # log.updateShare(gov.end_previous(func))
                    gov, govU, gov_is_new, log = save_and_return(gov, govU, log)
                if not gov.menuItem_array or 'RollCalls' not in gov.menuItem_array:
                    if not gov.signed:
                        gov.add_menu_item('RollCalls')
                    else:
                        if not modded_gov:
                            modded_gov = gov.propose_modification()
                        modded_gov.add_menu_item('RollCalls')
                        log.updateShare(modded_gov)

                member_info = soup.find('div', {'id':'member-info'})
                menus = member_info.find_all('div', {'class':'dropdown-menu_right'})

                def get_leadership(lis):
                    for li in lis:
                        try:
                            if 'Speaker of the House' in li.text:
                                fullName = li.text.replace('Rep. ', '').replace('Speaker of the House', '').strip()
                                position = 'Speaker of the House'
                            elif 'Majority Leader' in li.text:
                                fullName = li.text.replace('Rep. ', '').replace('Majority Leader', '').replace('(','').replace(')','').replace('Democratic Leader', '').replace('Republican Leader', '').strip()
                                position = 'Majority Leader'
                            elif 'Majority Whip' in li.text:
                                fullName = li.text.replace('Rep. ', '').replace('Majority Whip', '').strip()
                                position = 'Majority Whip'
                            elif 'Minority Leader' in li.text:
                                fullName = li.text.replace('Rep. ', '').replace('Minority Leader', '').replace('(','').replace(')','').replace('Democratic Leader', '').replace('Republican Leader', '').strip()
                                position = 'Minority Leader'
                            elif 'Minority Whip' in li.text:
                                fullName = li.text.replace('Rep. ', '').replace('Minority Whip', '').strip()
                                position = 'Minority Whip'
                            names = fullName.split(' ')
                            prnt('position and name:',names[0], names[-1], position)
                            personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Country_obj=country, data__Role__contains=position, data__FirstName__icontains=names[0], data__LastName__icontains=names[-1]).first()
                            if not personU:
                                personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Country_obj=country, data__Position__contains='Congressional Representative', data__FirstName__icontains=names[0], data__LastName__icontains=names[-1], extra__roles__contains={'Congressional Representative':{'current':True}}).first()
                                if personU:
                                    personU.data['Role'] = position
                                    personU.pointer_obj.update_role(personU, position, current=True)
                                    personU.func = func
                                    personU.save_if_new()
                                    log.updateShare(personU)
                                    prnt('added')
                                    oldRoles = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Country_obj=country, data__Role__contains=position, ).exclude(id=personU.Pointer_obj.id)
                                    for r in oldRoles:
                                        if 'Role' in r.data and r.data['Role'] == position:
                                            del r.data['Role']
                                        r.pointer_obj.update_role(personU, position, current=False)
                                        r.func = func
                                        r.save_if_new()
                                        log.updateShare(r)
                        except:
                            pass

                get_leadership(menus[0].find_all('li', {'role':'listitem'}))
                get_leadership(menus[1].find_all('li', {'role':'listitem'}))

                foundBills = []
                votes = section.find('div', {'id':'votes'})
                role_calls = votes.find_all('div', {'class':'role-call-vote'})
                if special == 'testing' or testing():
                    role_calls = role_calls[:2]
                for m in role_calls:
                    header = m.find('div', {'class':'heading'})
                    motion_link = header.find_all('a')[0]
                    motion_num = motion_link.text
                    if len(header.find_all('a')) > 1:
                        bill_link = header.find_all('a')[1]
                        a = bill_link.text.rfind(' ')
                        a = bill_link['href'].find('bill/')+len('bill/')
                        b = bill_link['href'][a:].find('/')
                        bCongress = bill_link['href'][a:a+b]
                        c = bill_link['href'][a+b+1:].find('/')
                        bill_prefix = bill_link['href'][a+b+1:a+b+1+c]
                        bill_code = bill_link.text.replace(' ', '')
                        prnt("bill_link['href']",bill_link['href'])
                        bill = Bill.objects.filter(Country_obj=country, Government_obj__GovernmentNumber=int(bCongress), NumberCode=bill_code, Validator_obj__is_valid=True).first()
                        if bill:
                            foundBills.append(bill)
                        else:
                            prnt('get bill')
                            time.sleep(1)
                            driver_service = None
                            url = f'https://www.govinfo.gov/bulkdata/BILLSTATUS/{bCongress}/{bill_prefix.lower()}/BILLSTATUS-{bCongress}{bill_code.replace(".","").lower()}.xml'
                            log, driver, driver_service = add_bill(url=url, log=log, driver=driver, driver_service=driver_service, country=country, ref_func=func)
                            bill = Bill.objects.filter(Country_obj=country, Government_obj__GovernmentNumber=int(bCongress), NumberCode=bill_code, Validator_obj__is_valid=True).first()
                            if bill:
                                foundBills.append(bill)
                    
                try:
                    close_browser(driver)
                except:
                    pass

                for m in role_calls:
                    task += 1
                    # consider checking only last few days by date instead of all 10 listed
                    header = m.find('div', {'class':'heading'})
                    motion_link = header.find_all('a')[0]
                    motion_num = motion_link.text
                    bill = None
                    if len(header.find_all('a')) > 1:
                        bill_link = header.find_all('a')[1]
                        a = bill_link['href'].find('bill/')+len('bill/')
                        b = bill_link['href'][a:].find('/')
                        bCongress = bill_link['href'][a:a+b]
                        bill_code = bill_link.text.replace(' ', '')
                        prnt("bill_link['href']",bill_link['href'])
                        for bill in foundBills:
                            if bill.NumberCode == bill_code and bill.Government_obj.GovernmentNumber == int(bCongress):
                                break
                                
                    detail = m.find('div', {'class':'detail-button'})
                    mLink = 'https://clerk.house.gov' + detail.find('a')['href']
                    prnt('mLink',mLink)
                    target = {'url':mLink, 'motion_num':motion_num, 'gov_id':gov.id}
                    if bill:
                        target['bill_id'] = bill.id
                    
                    motion = Motion.objects.filter(VoteNumber=target['motion_num'], GovUrl=target['url'], Government_obj=gov, Region_obj=country, Validator_obj__is_valid=True).values('id', 'TotalVotes').first()
                    if not motion or motion['TotalVotes'] > RepVote.objects.filter(Motion_obj__id=motion['id'], Validator_obj__is_valid=True).count():
                        queue = django_rq.get_queue('low')
                        queue.enqueue(get_house_rollcalls_us, special=special, target=target, job_dt=job_dt, task=task, job_timeout=runTimes[func], result_ttl=7200)
                        
    return finishScript(log, gov, special)


def add_official_debate_transcript(country, gov, chamber, log, url, driver=None, driver_service=None):
    func = 'add_official_debate_transcript'
    prnt(f'--{func} USA', now_utc())
    prnt(url)
    meeting = None
    proceed = True
    if not driver:
        driver = open_browser()
    try:
        driver.get(url)
        prnt('loaded')
        element_present = EC.presence_of_element_located((By.CLASS_NAME, 'table'))
        WebDriverWait(driver, 10).until(element_present)
        content = driver.find_element(By.XPATH, '//*[@id="contentdetaildocinContextview"]')
        panels = content.find_elements(By.CLASS_NAME, 'panel-default')
        for panel in panels:
            if chamber in panel.text:
                panel.click()
                prnt('clicked', chamber)
                element_id = panel.get_attribute('id').replace('panel','')
                target_id = 'collapseOne' + element_id
                element_present = EC.presence_of_element_located((By.XPATH, f'//*[@id="{target_id}"]/div/table[1]'))
                WebDriverWait(driver, 10).until(element_present)
                break
    except Exception as e:
        prnt('debate_transcript fail 1', str(e))
        proceed = False
        # logEvent('error loading page', region=country, code='598252', log_type='Errors', func=func, extra={'url':url, 'err':str(e)[:200]})
    if proceed:
        try:
            prnt('ready2')
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            def clean_text(text):
                # Replace single newlines with a space, but leave double newlines
                subbedText = re.sub(r'(?<!\n)\n(?!\n|\s)', ' ', text)
                while '[[Page' in subbedText:
                    a = subbedText.find('[[Page')
                    b = subbedText[a:].find(']]')+len(']]')
                    subbedText = subbedText[:a].strip() + ' ' + subbedText[a+b:].strip()
                return re.sub(r'\n{3,}', '\n\n', subbedText.strip())

            def find_first_title(text):
                pattern = r'  (Mr\.|Mrs\.|Ms\.|The ACTING PRESIDENT pro tempore\.|The PRESIDING OFFICER\.|The PRESIDING OFFICER |\[Rollcall Vote No\.|The SPEAKER\.|The SPEAKER |The SPEAKER pro tempore\.|The SPEAKER pro tempore )\s+(\b(?!President\b)(?!Speaker\b)\w+)'
                match = re.search(pattern, text)
                
                if match:
                    if 'The ACTING PRESIDENT pro tempore' in match.group() or 'The PRESIDING OFFICER.' in match.group() or 'Rollcall Vote No' in match.group() or 'The SPEAKER pro tempore.' in match.group() or 'The SPEAKER.' in match.group():
                        a = match.group().find('. ')
                        return match.group()[:a]
                    else:
                        return match.group()
                else:
                    return None
                    
            def make_statement(speaker, quote, subtitle, order, log):
                prnt('statement by:', speaker)
                party = None
                district = None

                def check_mentioned_state(text, dictionary, n=5):
                    first_words = set(text.split()[:n])
                    for value in dictionary.values():
                        if value in first_words:
                            return value 
                    return None
                reg_id = None
                mentioned_state = check_mentioned_state(quote, state_list)
                if mentioned_state:
                    reg = Region.objects.filter(ParentRegion_obj=country, Name__iexact=mentioned_state, Validator_obj__is_valid=True).first()
                    if reg:
                        reg_id = reg.id

                if speaker:
                    speaker = speaker.strip()
                    officers = {'the president officer':'The Presiding Officer', 'the acting president pro tempore':'The Acting President pro tempore', 'the speaker pro tempore':'The Speaker pro tempore', 'the speaker':'The Speaker'}
                    if speaker.lower() in officers:
                        speaker = officers[speaker.lower()]
                        prnt('office speaker',speaker)
                        personName = speaker
                        speaker_obj = None
                    elif 'Rollcall' in speaker:
                        prnt('presiding officer speakers:')
                        personName = 'Presiding Officer'
                        speaker_obj = None
                        quote = '[Rollcall Vote No. ' + quote
                    else:
                        prnt('speaker:', speaker)
                        personName = speaker
                        speakerName = speaker.replace('Mr. ','').replace('Mrs. ','').replace('Ms. ','').strip()
                        if reg_id:
                            personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__LastName__icontains=speakerName, data__ProvState_id__contains=reg_id, extra__roles__contains=[{'current':True,'gov_level':'Federal'}]).first()

                        else:
                            personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__LastName__icontains=speakerName, extra__roles__contains=[{'current':True,'gov_level':'Federal'}]).first()
                        if personU:
                            speaker_obj = personU.Pointer_obj
                            try:
                                party = Party.objects.filter(id=personU.data['Party_id'], Validator_obj__is_valid=True).first()
                            except:
                                pass
                            try:
                                district = District.objects.filter(id=personU.data['District_id'], Validator_obj__is_valid=True).first()
                            except:
                                pass
                        else:
                            speaker_obj = None
                elif proTempore or chairAppointee:
                    prnt('pro/chair')
                    if proTempore:
                        personName = proTempore.data['FullName']
                        speaker_obj = proTempore.Pointer_obj
                        try:
                            party = Party.objects.filter(id=proTempore.data['Party_id'], Validator_obj__is_valid=True).first()
                        except:
                            pass
                        try:
                            district = District.objects.filter(id=proTempore.data['District_id'], Validator_obj__is_valid=True).first()
                        except:
                            pass
                    else:
                        personName = chairAppointee
                        speaker_obj = None
                else:
                    prnt('else1')
                    if chamber == 'Senate':
                        personName = 'Presiding Officer'
                        speaker_obj = None
                    elif chamber == 'House':
                        personName = 'The Speaker'
                        speaker_obj = None
                lines = quote.splitlines()
                # Get the first non-empty line (without stripping spaces)
                first_line = next((line for line in lines if line.strip()), '')
                left_spaces = len(first_line) - len(first_line.lstrip())
                first_line_length = len(first_line.strip()) + (left_spaces*2)
                if left_spaces >= 3 and first_line_length >= 70 and first_line_length <= 74: # line is centered (71 chars total)
                    prntDebug('next1')
                    first_empty_line = None
                    for line_num, line in enumerate(quote):
                        if not line.strip():
                            prntDebug('line_num',line_num, isinstance(line_num, int))
                            first_empty_line = line_num + 1
                            break
                    if first_empty_line and first_empty_line >= 1 and first_empty_line <= 2:
                        subtitle = first_line.strip()
                        prnt('new subtitle',subtitle)
                        quote = quote.replace(first_line, '').strip()
                prnt('stage 3')
                content = clean_text(quote)
                statement, statementU, statement_is_new = get_model_and_update('Statement', Content=content, PersonName=personName, DateTime=starting_dt, source_link=statementLink, Meeting_obj=meeting, order=order, Chamber=chamber, Government_obj=gov, Country_obj=country, Region_obj=country)
                if speaker_obj:
                    statement.Person_obj = speaker_obj
                statement.Party_obj = party
                statement.District_obj = district
                statement.SubjectOfBusiness = subtitle
                if not subtitle in meeting_terms:
                    meeting_terms[subtitle] = 1
                else:
                    meeting_terms[subtitle] += 1
                statement, statementU, statement_is_new, log = save_and_return(statement, statementU, log)
                if statement.keyword_array:
                    for text in statement.keyword_array[:10]:
                        if '.' in text:
                            z = text.rfind('.')
                            q = text[:z].replace('.','').lower()
                            if q in billTypes:
                                if not statement.bill_dict or text not in statement.bill_dict:
                                    if not statement.bill_dict:
                                        statement.bill_dict = {}
                                    statement.bill_dict[text] = text
                        if not text in meeting_terms:
                            meeting_terms[text] = 1
                        else:
                            meeting_terms[text] += 1
                return order, log
            
            tables = soup.find_all('table', {'class':'table'})
            prnt('tables')
            order = 1
            next_meeting = None
            last_item = False
            chairAppointee = None
            proTempore = None
            starting_dt = None
            meetingTitle = None
            meeting_terms = {}
            if chamber == 'Senate':
                position = 'Senator'
            elif chamber == 'House':
                position = 'Congressional Representative'
            for table in tables:
                err = 1
                if last_item:
                    prnt('last_item break')
                    break
                td = table.find_all('td')
                subtitle = ''
                try:
                    err = 2
                    link = None
                    p = td[0].find('p')
                    if p:
                        p = p.text
                        a = p.find(' - ')+len(' - ')
                        subtitle = p[a:].replace('(Executive Session)','').replace('(Executive Calendar)','').strip()
                        prnt('subtitle', subtitle)
                        
                        p = td[1].find('p')
                        if p:
                            p = p.text
                            words = p.split(' ')
                            previousIsCaps = None
                            wordIsTitle = False
                            speaker = None
                            personName = ''
                            regarding = None
                            bill = None
                            if not starting_dt:
                                err = 3
                                try:
                                    dt = p.replace('Congressional Record. ','').strip()
                                    starting_dt = parse(dt)
                                    starting_dt = timezonify('est', starting_dt)
                                    prnt('starting_dt',starting_dt)
                                except Exception as e:
                                    prnt('starting_dt err 1',str(e))
                                    pass
                            if 'Regarding' in p and starting_dt:
                                err = 4
                                a = p.find('Regarding ')+len('Regarding ')
                                pattern = r' (Mr\.|Mrs\.|Ms\.)'
                                match = re.search(pattern, p)
                                if match:
                                    b = p[a:].find(match.group())
                                else:
                                    b = p[a:].find(starting_dt.strftime("%B"))
                                bill_code = p[a:a+b].strip()
                                if bill_code.endswith('.'):
                                    bill_code = bill_code[:-1]
                                a = bill_code.rfind(' ')
                                bill_prefix = bill_code[:a].replace(' ','')
                                regarding = bill_code.replace(' ','')
                                prnt('regarding',regarding)
                                bill = Bill.objects.filter(NumberCode=regarding, Government_obj=gov, Country_obj=country, Validator_obj__is_valid=True).first()
                                if not bill:
                                    err = 5
                                    def fetch_bill(govNum, log, driver, driver_service):
                                        try:
                                            time.sleep(1.5)
                                            bill_url = f'https://www.govinfo.gov/bulkdata/BILLSTATUS/{govNum}/{bill_prefix.replace(".","").lower()}/BILLSTATUS-{govNum}{regarding.replace(".","").lower()}.xml'
                                            return add_bill(url=bill_url, log=log, driver=driver, country=country, ref_func=func)
                                        except Exception as e:
                                            prnt('fetch_bill err 1',str(e))
                                            return log, driver, driver_service

                                    log, driver, driver_service = fetch_bill(gov.GovernmentNumber, log, driver, driver_service)
                                    bill = Bill.objects.filter(NumberCode=regarding, Government_obj=gov, Country_obj=country, Validator_obj__is_valid=True).first()
                                    if not bill:
                                        log, driver, driver_service = fetch_bill(gov.GovernmentNumber - 1, log, driver, driver_service)
                                        bill = Bill.objects.filter(NumberCode=regarding, Government_obj__GovernmentNumber=gov.GovernmentNumber-1, Country_obj=country, Validator_obj__is_valid=True).first()
                                        if not bill:
                                            log, driver, driver_service = fetch_bill(gov.GovernmentNumber - 2, log, driver, driver_service)
                                            bill = Bill.objects.filter(NumberCode=regarding, Government_obj__GovernmentNumber=gov.GovernmentNumber-2, Country_obj=country, Validator_obj__is_valid=True).first()

                            err = 6
                            for word in words:
                                if word == 'Mr.' or word == 'Mrs.' or word == 'Ms.':
                                    title = word
                                    wordIsTitle = True
                                elif wordIsTitle:
                                    word = word.replace('.','').replace(',','')
                                    speaker = title + ' ' + word
                                    previousIsCaps = word
                                    wordIsTitle = False
                                elif previousIsCaps and word.isupper():
                                    word = word.replace('.','').replace(',','')
                                    fullName = title + ' ' + previousIsCaps + ' ' + word
                                    if previousIsCaps in speaker:
                                        speaker = fullName
                                else:
                                    previousIsCaps = None
                                    wordIsTitle = False
                            err = 7
                            links = td[1].find_all('a')
                            for link in links:
                                if 'Text' in link.text:
                                    err = 8
                                    statementLink = 'https://www.govinfo.gov' + link['href']
                                    statement = Statement.objects.filter(Meeting_obj=meeting, source_link=statementLink, Validator_obj__is_valid=True).order_by('-order').first()
                                    if statement:
                                        order = statement.order + 1
                                    else:
                                        err = 9
                                        if not meeting:
                                            meeting, meetingU, meeting_is_new = get_model_and_update('Meeting', GovPage=url, meeting_type='Debate', Chamber=chamber, Government_obj=gov, Country_obj=country, Region_obj=country)
                                            meeting.hide_time = 'hour'
                                            meetingU.data['has_transcript'] = True
                                            if meeting_is_new:
                                                meetingU.data['completed_model'] = False
                                                meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)
                                        prnt('statementLink',statementLink)
                                        order += 1
                                        time.sleep(1.5)
                                        try:
                                            r = requests.get(statementLink) # link does not always load, consider second request if fail or dummy statement with link - currently should try again with later job if statement is missing
                                            bs = BeautifulSoup(r.content, 'html.parser')
                                            pre = bs.find('pre').text
                                        except:
                                            prnt('fetch attempt 2')
                                            time.sleep(2)
                                            r = requests.get(statementLink)
                                            bs = BeautifulSoup(r.content, 'html.parser')
                                            pre = bs.find('pre').text
                                        pre = pre.replace('____________________','').replace('[Senate]','')
                                        if '...' in subtitle:
                                            newSub = subtitle[:40]
                                            a = pre.find(newSub)
                                            b = pre[a:].find('\n\n')
                                            subtitle = pre[a:a+b]
                                            prnt('new subtitle:', subtitle)
                                        if subtitle in pre:
                                            a = pre.find(subtitle)+len(subtitle)
                                            prnt('found')
                                        else:
                                            a = pre.find('.gov]')+len('.gov]')
                                            prnt('not found')
                                        subtitle = subtitle.replace('-Continued','')
                                        if len(subtitle) > 150:
                                            subtitle = subtitle[:150] + '...'
                                        prnt('subtitle',subtitle)
                                        err = 10
                                        text = pre[a:].replace('______','')
                                        if subtitle == 'APPOINTMENT OF ACTING PRESIDENT PRO TEMPORE':
                                            err = 11
                                            a = text.find('hereby appoint the Honorable ')+len('hereby appoint the Honorable ')
                                            b = text[a:].find(', ')
                                            chairAppointee = text[a:a+b].strip()
                                            names = chairAppointee.split(' ')

                                            pkey = ContentType.objects.get_for_model(Person)
                                            personU = Update.valid_objects.filter(pointerKey=pkey, Region_obj=country, data__FirstName__icontains=names[0], data__LastName__icontains=names[-1], extra__roles__contains=[{'role':'Senator','current':True}]).first()
                                            
                                            if personU:
                                                proTempore = personU
                                                prnt('Acting President pro tempore!!:', proTempore.data['FullName'], names)
                                            else:
                                                prnt('Acting President pro tempore not found:',  names)
                                                pass

                                            content = clean_text(text.replace('The PRESIDING OFFICER. ',''))
                                            
                                            statement, statementU, statement_is_new = get_model_and_update('Statement', Content=content, PersonName=chairAppointee, DateTime=starting_dt, source_link=statementLink, Meeting_obj=meeting, order=order, Chamber=chamber, Government_obj=gov, Country_obj=country, Region_obj=country)
                                            if proTempore and proTempore.Pointer_obj:
                                                statement.Person_obj = proTempore.Pointer_obj,
                                            try:
                                                statement.Party_obj = Party.objects.filter(id=proTempore.data['Party_id'], Validator_obj__is_valid=True).first()
                                            except:
                                                pass
                                            try:
                                                statement.District_obj = District.objects.filter(id=proTempore.data['District_id'], Validator_obj__is_valid=True).first()
                                            except:
                                                pass
                                            statement.order = order
                                            statement.SubjectOfBusiness = subtitle
                                            if not subtitle in meeting_terms:
                                                meeting_terms[subtitle] = 1
                                            else:
                                                meeting_terms[subtitle] += 1
                                            err = 12
                                            statement, statementU, statement_is_new, log = save_and_return(statement, statementU, log)
                                            if statement.keyword_array:
                                                for text in statement.keyword_array[:10]:
                                                    if '.' in text:
                                                        z = text.rfind('.')
                                                        q = text[:z].replace('.','').lower()
                                                        if q in billTypes:
                                                            if not statement.bill_dict or text not in statement.bill_dict:
                                                                if not statement.bill_dict:
                                                                    statement.bill_dict = {}
                                                                b = Bill.objects.filter(NumberCode__iexact=text, Region_obj=country, Validator_obj__is_valid=True).first()
                                                                if b:
                                                                    statement.bill_dict[b.NumberCode] = {'obj_id':b.id}
                                                    if not text in meeting_terms:
                                                        meeting_terms[text] = 1
                                                    else:
                                                        meeting_terms[text] += 1
                                            err = 13
                                        else:
                                            if subtitle in ['House of Representatives', 'Senate'] or ' met at ' in subtitle:
                                                err = 14
                                                if not meetingTitle:
                                                    a = pre.find('Congressional Record ')+len('Congressional Record ')
                                                    b = pre[a:].find(' (')
                                                    meetingTitle = pre[a:a+b]
                                                    meeting.Title = meetingTitle
                                                    meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)
                                                a = None
                                                if 'The Senate met at ' in text:
                                                    a = text.strip().find('The Senate met at ')+len('The Senate met at ')
                                                elif 'The House met at ' in text:
                                                    a = text.strip().find('The House met at ')+len('The House met at ')
                                                if a:
                                                    err = 15
                                                    b = None
                                                    if 'a.m.' in text:
                                                        b = text.strip()[a:].find('a.m.')+len('a.m.')
                                                        hour = text.strip()[a:a+b]
                                                    elif 'p.m.' in text:
                                                        b = text.strip()[a:].find('p.m.')+len('p.m.')
                                                        hour = text.strip()[a:a+b]
                                                    elif 'noon' in text:
                                                        hour = '12 p.m.'
                                                    if starting_dt:
                                                        err = 16
                                                        if hour:
                                                            err = 17
                                                            working_dt = dt + ' ' + hour
                                                            working_dt = working_dt.replace('.','').replace('seconds','second')
                                                            prnt('working_dt',working_dt)
                                                            # logError('get debate time test', code='48367423', func='add_official_debate_transcript', region=country, extra=str(working_dt))
                                                            try:
                                                                starting_dt = parse(working_dt)
                                                            except:
                                                                try:
                                                                    starting_dt = datetime.datetime.strptime(working_dt, '%B %d, %Y %I %p')
                                                                except:
                                                                    try:
                                                                        starting_dt = datetime.datetime.strptime(working_dt, '%B %d, %Y %I:%M %p')
                                                                    except:
                                                                        try:
                                                                            starting_dt = datetime.datetime.strptime(working_dt, '%B %d, %Y %I:%M and %S second %p')
                                                                        except:
                                                                            try:
                                                                                starting_dt = datetime.datetime.strptime(working_dt, '%B %d, %Y %I and %S second %p')
                                                                            except:
                                                                                try:
                                                                                    starting_dt = datetime.datetime.strptime(working_dt, '%B %d, %Y %I')
                                                                                except:
                                                                                    # December 26, 2024 2:30 and 1 second pm
                                                                                    # December 30, 2024 12:30 and 1 second pm
                                                                                    # December 26, 2024 2:30 and 1 second pm
                                                                                    # December 23, 2024 9:53 and 24 seconds am
                                                                                    # December 27, 2024 noo
                                                                                    # January 2, 2025 12 and 46 second pm
                                                                                    # January 27, 2025 12
                                                                                    # January 29, 2025 12
                                                                                    # logError('get starting time fail', code='487153', func='add_official_debate_transcript', region=country, extra=str(working_dt))
                                                                                    pass
                                                        err = 18
                                                        try:
                                                            starting_dt = timezonify('est', starting_dt)
                                                        except Exception as e:
                                                            pass
                                                        prnt('starting_dt222',starting_dt)
                                                        meeting.DateTime = starting_dt
                                                        meetingU.DateTime = starting_dt
                                                        meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)
                                                        err = 18
                                            if 'adjourned until' in text:
                                                err = 19
                                                prnt('adjourned until')
                                                last_item = True
                                                def is_month(word):
                                                    days_of_week = list(calendar.month_name)
                                                    return word in days_of_week

                                                def is_day_of_week(word):
                                                    days_of_week = [day.lower() for day in calendar.day_name]
                                                    days_abbrev = [day.lower() for day in calendar.day_abbr]
                                                    return word.lower() in days_of_week or word.lower() in days_abbrev

                                                working_text = text.replace('\n', '').strip()
                                                a = working_text.rfind('adjourned until ')+len('adjourned until ')
                                                x = working_text[a:]
                                                words = x.split(' ')
                                                date_string = ''
                                                match = False
                                                next_meeting_dt = None
                                                if 'noon' in x:
                                                    if 'tomorrow' in x and meeting.DateTime:
                                                        next_day = meeting.DateTime + datetime.timedelta(days=1)
                                                        next_meeting_dt = next_day.replace(hour=12, minute=0, second=0, microsecond=0)
                                                    else:
                                                        day_of_week = None
                                                        date_num = None
                                                        month = None
                                                        for word in words:
                                                            if is_month(word):
                                                                month = word.lower()
                                                            elif is_day_of_week(word):
                                                                day_of_week = word.lower()
                                                            elif isinstance(word, int):
                                                                date_num = word
                                                        if month and day_of_week and date_num:
                                                            date_string = f'{month} {date_num} {now_utc().year} at 12 PM'
                                                if not next_meeting_dt and not date_string:
                                                    for word in words:
                                                        word = word.replace(',','')
                                                        if is_month(word):
                                                            match = True
                                                        if match:
                                                            date_string = date_string + ' ' + word
                                                err = 20
                                                date_string = date_string.replace('.','').strip()
                                                prnt('date_string',date_string)
                                                if not next_meeting_dt and date_string:
                                                    err = 21
                                                    date_string = date_string.replace(' for morning-hour debate','')
                                                    # until 3 p.m. on Monday, September 9;
                                                    # date_string,January 22 2025 at 10 am for morning-hour debate
                                                    # it stand adjourned until 12 noon on Monday, January 27;
                                                    # stand adjourned until noon tomorrow for morning-hour debate and 2 p.m. for legislative business.
                                                    # t stand adjourned until 10 a.m. on Tuesday, January 28; that following the prayer and pledge, the Journal of proceedings be approved to d
                                                    try:
                                                        next_meeting_dt = datetime.datetime.strptime(date_string, '%B %d %Y at %I %p')
                                                    except Exception as e:
                                                        # prnt(str(e))
                                                        # logError('get next_meeting_dt fail', code='8364', func='add_official_debate_transcript', region=country, extra={'link':link,'dt_sting':str(date_string)})
                                                        #  'get next_meeting_dt fail', 'reg': 'USA', 'code': '8364', 'func': 'add_official_debate_transcript', 'extra': "Pursuant to H Res 43 and without objection Members will now proceed to the rotunda to attend the inaugural ceremonies for the President and Vice President of the United States Thereupon at 10 o'clock and 6 minutes am the Members of the House preceded by the Sergeant at Arms and the Speaker pro tempore proceeded to the rotunda of the Capitol"}
                                                        try:
                                                            next_meeting_dt = datetime.datetime.strptime(date_string, '%B %d %Y at %I:%M %p')
                                                        except Exception as e:
                                                            # prnt(str(e))
                                                            next_meeting_dt = None
                                                    if next_meeting_dt:
                                                        next_meeting_dt = timezonify('est', next_meeting_dt)
                                                        prnt('next_meeting_dt',next_meeting_dt)
                                                    err = 22
                                                if next_meeting_dt:
                                                    err = 23
                                                    A = Agenda.objects.filter(DateTime=next_meeting_dt, Chamber=chamber, Government_obj=gov, Country_obj=country, Region_obj=country, Validator_obj__is_valid=True).first()
                                                    if not A:
                                                        A = Agenda(DateTime=next_meeting_dt, Chamber=chamber, Government_obj=gov, Country_obj=country, Region_obj=country, func=log.data['func'])
                                                        A.save()
                                                        log.updateShare(A)
                                                    prnt("A",A)
                                            if '  Mr.' in text or '  Mrs.' in text or '  Ms.' in text or '  The PRESIDING OFFICER' in text or '  The ACTING PRESIDENT pro tempore.' in text or '[Rollcall Vote No' in text or '  the speaker' in text.lower():
                                                err = 24
                                                prnt('FOUND INSTANCE')
                                                x = find_first_title(text)
                                                nextSpeaker = x
                                                prnt('nextSpeaker1',nextSpeaker)
                                                snippedText = text
                                                while x:
                                                    err = 25
                                                    a = snippedText.find(x)
                                                    firstQuote = snippedText[:a].strip()
                                                    if firstQuote:
                                                        err = 26
                                                        snippedText = snippedText.replace(firstQuote, '', 1)
                                                        prnt('make_statement-a')
                                                        order, log = make_statement(speaker, firstQuote, subtitle, order, log)
                                                        x = find_first_title(snippedText)
                                                        nextSpeaker = x
                                                        prnt('nextSpeaker2',nextSpeaker)
                                                    else:
                                                        err = 27
                                                        prnt('else x')
                                                        a2 = a+len(x)
                                                        b = snippedText[a2:].find('. ')+len('. ')
                                                        snippedText = snippedText[a2+b:]
                                                        x = find_first_title(snippedText)
                                                        prnt('x',x)
                                                        if x:
                                                            a = snippedText.find(x)
                                                            if snippedText[:a].endswith(':\n'):
                                                                b = snippedText.find('\n\n')
                                                                snippedText = snippedText[:b].strip()
                                                                x = find_first_title(snippedText[b:])
                                                        speaker = nextSpeaker
                                                        nextSpeaker = x
                                                        prnt('nextSpeaker3',nextSpeaker)
                                                err = 28
                                                prnt('make_statement-b')
                                                order, log = make_statement(speaker, snippedText, subtitle, order, log)
                                            else:
                                                err = 29
                                                prnt('make_statement-c')
                                                order, log = make_statement(speaker, text, subtitle, order, log)
                                        prnt('--next')
                                        time.sleep(1)
                except Exception as e:
                    prnt('debate fail 1', str(e))
                    # logEvent(str(e), region=country, code='58362', func=func, extra={'err':err,'url':url,'subtitle':subtitle,'link':link}, log_type='Errors')

        except Exception as e:
            prnt('failed debate 2', str(e))
            # logEvent(str(e)[:250], region=country, code='39586', log_type='Errors', func=func, extra={'url':url})
            # pass
    if meeting:
        prnt('order_count', order)
        meeting, meetingU, meeting_is_new = meeting.apply_terms(meeting, meetingU, meeting_is_new)
        if 'statement_count' in meetingU.data and meetingU.data['statement_count'] > 0:
            meetingU.data['completed_model'] = True
        meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)
    return log, driver, driver_service


def get_house_debates_us(special=None, dt=None, iden=None, target={}, driver=None, driver_service=None, job_dt=None, task=None, as_rq=True):
    func = 'get_house_debates_us'
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    task = declare_var(task, 1)
    country = Region.supported_objects.filter(nameType='Country', Name='USA', Validator_obj__is_valid=True).first()
    if not job_dt:
        job_dt = dt
    log = create_share_object(func, country, special=special, dt=dt, iden=iden, job_dt=job_dt, task=task)
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, extra=target, log_type='Tasks')
    if target and 'link' in target:
        if 'gov_id' in target:
            gov = Government.objects.filter(id=target['gov_id'], Validator_obj__is_valid=True).first()
        else:
            gov = Government.objects.filter(Country_obj=country, Region_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
        if not gov and country:
            return finishScript(log, gov, special)
        run_job = True
        meetings = Meeting.objects.filter(Country_obj=country, Chamber='House', meeting_type='Debate', GovPage__icontains=target['link'], Validator_obj__is_valid=True).order_by('DateTime')
        if meetings:
            meetingsU = Update.objects.filter(pointerId__in=[i.id for i in meetings], data__contains={'completed_model': True}).order_by('DateTime')
            for u in meetingsU:
                if 'statement_count' in u.data and u.data['statement_count'] > 0:
                    if Statement.objects.filter(Meeting_obj__id=u.pointerId, Validator_obj__is_valid=True).count() == u.data['statement_count']:
                        if u.validated or u.created > now_utc() - datetime.timedelta(minutes=60):
                            run_job = False
        if run_job:
            log, driver, driver_service = add_official_debate_transcript(country, gov, 'House', log, target['link'], driver=driver, driver_service=driver_service)
    else:
        gov = Government.objects.filter(Country_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
        if not gov and country:
            return finishScript(log, gov, special)
        if not gov.menuItem_array or 'Debates' not in gov.menuItem_array:
            if not gov.signed:
                gov.add_menu_item('Debates')
            else:
                if not modded_gov:
                    modded_gov = gov.propose_modification()
                modded_gov.add_menu_item('Debates')
                log.updateShare(modded_gov)

        search_range = 7
        meetings = Meeting.objects.filter(Country_obj=country, Chamber='House', meeting_type='Debate', DateTime__gte=dt-datetime.timedelta(days=7), Validator_obj__is_valid=True).order_by('DateTime')
        if meetings:
            meetingsU = Update.objects.filter(pointerId__in=[i.id for i in meetings], data__contains={'completed_model': True}).order_by('DateTime')
            for u in meetingsU:
                if 'statement_count' in u.data and u.data['statement_count'] > 0:
                    if Statement.objects.filter(Meeting_obj__id=u.pointerId, Validator_obj__is_valid=True).count() == u.data['statement_count']:
                        if u.validated or u.created > now_utc() - datetime.timedelta(minutes=60):
                            dt_difference = dt - u.DateTime
                            search_range = dt_difference.days

        if search_range > 0:
            while search_range >= 0:
                utc = dt - datetime.timedelta(days=search_range)
                est = pytz.timezone('US/Eastern')
                today = utc.astimezone(est)
                prnt("EST Time:", today)
                link = f"https://www.govinfo.gov/app/details/CREC-{today.strftime('%Y-%m-%d')}/context"
                prnt('link',link)
                target = {'link': link, 'gov_id':gov.id}
                task += 1
                if not testing():
                    create_job(get_house_debates_us, job_timeout=runTimes[func], worker='low', clear_chrome_job=True, special=special, target=target, job_dt=job_dt, task=task)
                else:
                    get_house_debates_us(special=special, target=target)
                search_range -= 1
        else:
            utc = dt - datetime.timedelta(days=search_range)
            est = pytz.timezone('US/Eastern')
            today = utc.astimezone(est)
            prnt("EST Time:", today)
            link = f"https://www.govinfo.gov/app/details/CREC-{today.strftime('%Y-%m-%d')}/context"
            log, driver, driver_service = add_official_debate_transcript(country, gov, 'House', log, link, driver=driver, driver_service=driver_service)

    try:
        close_browser(driver)
    except:
        pass
    return finishScript(log, gov, special)

def get_senate_debates_us(special=None, dt=None, iden=None, target={}, driver=None, driver_service=None, job_dt=None, task=None, as_rq=True):
    func = 'get_senate_debates_us'
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    task = declare_var(task, 1)
    country = Region.supported_objects.filter(nameType='Country', Name='USA', Validator_obj__is_valid=True).first()
    if not job_dt:
        job_dt = dt
    log = create_share_object(func, country, special=special, dt=dt, iden=iden, job_dt=job_dt, task=task)
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, extra=target, log_type='Tasks')
    
    if target and 'link' in target:
        if 'gov_id' in target:
            gov = Government.objects.filter(id=target['gov_id'], Validator_obj__is_valid=True).first()
        else:
            gov = Government.objects.filter(Country_obj=country, Region_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
        if not gov and country:
            return finishScript(log, gov, special)
        log, driver, driver_service = add_official_debate_transcript(country, gov, 'Senate', log, target['link'], driver=driver, driver_service=driver_service)

    else:
        gov = Government.objects.filter(Country_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
        if not gov and country:
            return finishScript(log, gov, special)
        if not gov.menuItem_array or 'Debates' not in gov.menuItem_array:
            if not gov.signed:
                gov.add_menu_item('Debates')
            else:
                if not modded_gov:
                    modded_gov = gov.propose_modification()
                modded_gov.add_menu_item('Debates')
                log.updateShare(modded_gov)
        meetingU = None
        meetings = Meeting.objects.filter(Country_obj=country, Chamber='Senate', meeting_type='Debate', DateTime__gte=dt-datetime.timedelta(hours=24), Validator_obj__is_valid=True)
        if meetings:
            meetingU = Update.valid_objects.filter(pointerId__in=[i.id for i in meetings], data__contains={'completed_model': True}).first()
        if not meetingU:
            linkList, driver, driver_service = get_senate_activity('debates')
            checkLinks = [link for link in reversed(linkList[:5])]
            meetings = Meeting.objects.filter(Country_obj=country, Chamber='Senate', meeting_type='Debate', GovPage__in=checkLinks, Validator_obj__is_valid=True).order_by('DateTime')
            if meetings:
                meetingsU = Update.objects.filter(pointerId__in=[i.id for i in meetings], data__contains={'completed_model': True}).order_by('DateTime')
                for u in meetingsU:
                    if 'statement_count' in u.data and u.data['statement_count'] > 0:
                        if u.Pointer_obj.GovPage in checkLinks:
                            if Statement.objects.filter(Meeting_obj__id=u.pointerId, Validator_obj__is_valid=True).count() == u.data['statement_count']:
                                if u.validated or u.created > now_utc() - datetime.timedelta(minutes=60):
                                    checkLinks.remove(u.Pointer_obj.GovPage)
            if checkLinks:
                if len(checkLinks) == 1:
                    log, driver, driver_service = add_official_debate_transcript(country, gov, 'Senate', log, checkLinks[0], driver=driver, driver_service=driver_service)
                else:
                    for link in checkLinks:
                        target = {'link':link, 'gov_id':gov.id}
                        task += 1
                        create_job(get_senate_debates_us, job_timeout=runTimes[func], worker='low', clear_chrome_job=True, special=special, target=target, job_dt=job_dt, task=task)

    try:
        close_browser(driver)
    except:
        pass
    return finishScript(log, gov, special)


def get_senate_rollcalls_us(special=None, dt=None, iden=None, target={}, driver=None, driver_service=None, job_dt=None, task=None, as_rq=True):
    func = 'get_senate_rollcalls_us'
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    task = declare_var(task, 1)
    country = Region.supported_objects.filter(nameType='Country', Name='USA').first()
    if not job_dt:
        job_dt = dt
    log = create_share_object(func, country, special=special, dt=dt, iden=iden, job_dt=job_dt, task=task)
    gov = Government.objects.filter(Country_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
    if not gov and country:
        return finishScript(log, gov, special)
    if not gov.menuItem_array or 'RollCalls' not in gov.menuItem_array:
        if not gov.signed:
            gov.add_menu_item('RollCalls')
        else:
            if not modded_gov:
                modded_gov = gov.propose_modification()
            modded_gov.add_menu_item('RollCalls')
            log.updateShare(modded_gov)
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, extra=target, log_type='Tasks')
    
    if target and 'link' in target:
        if 'gov_id' in target:
            gov = Government.objects.filter(id=target['gov_id'], Validator_obj__is_valid=True).first()
        else:
            gov = Government.objects.filter(Country_obj=country, Region_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
        log = add_senate_rollcall(country, gov, log, target['link'])
    else:
        gov = Government.objects.filter(Country_obj=country, gov_level='Federal').first()
        motion = Motion.objects.filter(Country_obj=country, Chamber='Senate', DateTime__gte=dt-datetime.timedelta(hours=24), Validator_obj__is_valid=True).exclude(TotalVotes=0).values('id', 'TotalVotes').first()
        
        if special or not motion or motion['TotalVotes'] > RepVote.objects.filter(Motion_obj__id=motion['id'], Validator_obj__is_valid=True).count():
            grouping, driver, driver_service = get_senate_activity('motions')
            if True == False:
                for link in motionLinks[:1]:
                    motion = Motion.objects.filter(Country_obj=country, GovUrl=link).exclude(TotalVotes=0).first()
                    if not motion:
                        time.sleep(1)
                        log  = add_senate_rollcall(country, gov, log, link)
            else:
                get_motions = []
                for group in reversed(grouping):
                    motionLinks = grouping[group]['rollcalls']
                    if motionLinks:
                        motions = Motion.objects.filter(Country_obj=country, GovUrl__in=motionLinks, Validator_obj__is_valid=True).exclude(TotalVotes=0).values('id', 'TotalVotes', 'GovUrl')
                        for motion in motions:
                            if motion['GovUrl'] in motionLinks and motion['TotalVotes'] <= RepVote.objects.filter(Motion_obj__id=motion['id'], Validator_obj__is_valid=True).count():
                                motionLinks.remove(motion['GovUrl'])

                    for link in motionLinks:
                        if link not in get_motions:
                            get_motions.append(link)
                        billLinks = []
                        billData = grouping[group]['bills']
                        for b in billData:
                            q = b['link'].find('/bill/')
                            if q:
                                q += len('/bill/')
                                govNum = b['link'][q:q+3]
                                if 'house' in b['link'].lower() or 'senate' in b['link'].lower():
                                    a = b['title'].rfind('.')
                                    bill_prefix = b['title'][:a].replace(' ','').replace('.','').lower()
                                    bill_num = b['title'][a:].replace('.','').strip()
                                    url = f'https://www.govinfo.gov/bulkdata/BILLSTATUS/{govNum}/{bill_prefix}/BILLSTATUS-{govNum}{bill_prefix}{bill_num}.xml'
                                    if url not in billLinks:
                                        billLinks.append(url)
                        if billLinks:
                            billUpdates = Update.objects.filter(pointerKey=ContentType.objects.get_for_model(Bill), Region_obj=country, data__data_link__in=billLinks).filter(Q(validated=True)|Q(created__gte=now_utc() - datetime.timedelta(minutes=60))).distinct('pointerId').order_by('pointerId','-created')
                            for u in billUpdates:
                                if u.data['data_link'] in billLinks:
                                    billLinks.remove(u.data['data_link'])

                            for url in billLinks:
                                log, driver, driver_service = add_bill(url=url, log=log, driver=driver, driver_service=driver_service, country=country, ref_func=func)
                                if url != billLinks[-1]:
                                    time.sleep(1)

                if len(get_motions) == 1:
                    log = add_senate_rollcall(country, gov, log, get_motions[0])
                else:
                    for link in get_motions:
                        target = {'link':link, 'gov_id':gov.id}
                        task += 1
                        prnt('add_job',link)
                        create_job(get_senate_rollcalls_us, job_timeout=runTimes[func], worker='low', clear_chrome_job=False, special=special, target=target, job_dt=job_dt, task=task)
                        
                try:
                    close_browser(driver)
                except:
                    pass
    return finishScript(log, gov, special)

def get_senate_activity(target):
    driver_service = None
    url = 'https://www.senate.gov/legislative/LIS/floor_activity/all-floor-activity-files.htm'
    try:
        driver = open_browser(url)
        element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="floor_activity_table"]/tbody'))
        WebDriverWait(driver, 10).until(element_present)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        soup = None
        prnt('senate activitiy fail 3434', str(e))

    debateLinks = []
    motionLinks = {}
    billLinks = []
    grouping = {}
    if soup:
        tbody = soup.find('tbody')
        trs = tbody.find_all('tr', {'role':'row'})
        group = 0
        for tr in trs:
            group += 1
            grouping[group] = {'rollcalls':[],'bills':[]}
            tds = tr.find_all('td')
            for td in tds:
                try:
                    span = td.find('span')
                except:
                    pass
                links = td.find_all('a')
                for link in links:
                    if 'Congressional Record' in link.text and target == 'debates':
                        prnt("link['href']1", link['href'])
                        debateLinks.append(link['href'])
                    elif 'roll_call_vote' in link['href'] and target == 'motions':
                        prnt("link['href']2",link['href'])
                        if link['href'] not in grouping[group]['rollcalls']:
                            grouping[group]['rollcalls'].append(link['href'])
                    elif 'bill' in link['href'] and 'n/a' not in link.text and target == 'motions':
                        prnt("link['href']3",link['href'])
                        bill = {'title':link.text.replace(' ',''), 'link':link['href']}
                        if bill not in grouping[group]['bills']:
                            grouping[group]['bills'].append(bill)
    if target == 'debates':
        return debateLinks, driver, driver_service
    else:
        return grouping, driver, driver_service

def add_senate_rollcall(country, gov, log, url):
    func = 'add_senate_rollcall'
    prnt(f'--{func} USA', now_utc())
    # url = 'https://www.senate.gov/legislative/LIS/roll_call_votes/vote1182/vote_118_2_00128.xml'
    xml = url.replace('htm', 'xml')
    if not xml.startswith('https://www.senate.gov'):
        xml = f'https://www.senate.gov{xml}'
    prnt(xml)
    r = requests.get(xml)
    root = ET.fromstring(r.content)

    congress = root.find('congress').text
    session = root.find('session').text
    congress_year = root.find('congress_year').text
    vote_number = root.find('vote_number').text
    vote_date = root.find('vote_date').text
    # July 11, 2024, 01:22 PM
    vote_dt = timezonify('est', datetime.datetime.strptime(vote_date, '%B %d, %Y, %I:%M %p'))
    prnt('vote_dt',vote_dt)
    modify_date = root.find('modify_date').text
    vote_question_text = root.find('vote_question_text').text
    vote_document_text = root.find('vote_document_text').text
    vote_result_text = root.find('vote_result_text').text
    question = root.find('question').text
    vote_title = root.find('vote_title').text
    majority_requirement = root.find('majority_requirement').text
    vote_result = root.find('vote_result').text
    prnt(gov)
    if int(congress) != gov.GovernmentNumber or int(session) != gov.SessionNumber:
        prnt('return sen roll call x')
        return log

    prnt(f"vote_number: {vote_number}")
    prnt(f"vote_date: {vote_date}")
    prnt(f"vote_question_text: {vote_question_text}")
    prnt(f"vote_result_text: {vote_result_text}")
    prnt(f"question: {question}")
    prnt(f"vote_title: {vote_title}")
    prnt(f"vote_result: {vote_result}")

    try:
        document = root.find('document')
        document_congress = document.find('document_congress').text
        document_type = document.find('document_type').text
        document_number = document.find('document_number').text
        document_name = document.find('document_name').text
        document_title = document.find('document_title').text
        document_short_title = document.find('document_short_title').text
        prnt(f"document_number: {document_number}")
        bill = Bill.objects.filter(NumberCode=document_name.replace(' ',''), Country_obj=country, Government_obj=gov, Validator_obj__is_valid=True).first()
    except:
        document_name = None
        bill = None

    try:
        amendment = root.find('amendment')
        amendment_number = amendment.find('amendment_number').text
        amendment_to_amendment_number = amendment.find('amendment_to_amendment_number').text
        amendment_to_amendment_to_amendment_number = amendment.find('amendment_to_amendment_to_amendment_number').text
        amendment_to_document_number = amendment.find('amendment_to_document_number').text
        amendment_to_document_short_title = amendment.find('amendment_to_document_short_title').text
        amendment_purpose = amendment.find('amendment_purpose').text
    except:
        pass

    count = root.find('count')
    yeas = count.find('yeas').text
    nays = count.find('nays').text
    present = count.find('present').text
    absent = count.find('absent').text
    tie_breaker = root.find('tie_breaker')
    by_whom = tie_breaker.find('by_whom').text
    tie_breaker_vote = tie_breaker.find('tie_breaker_vote').text

    motion, motionU, motion_is_new = get_model_and_update('Motion', VoteNumber=vote_number, GovUrl=url, Chamber='Senate', Country_obj=country, Government_obj=gov, Region_obj=country)
    if motion_is_new:
        motion.DateTime = vote_dt
        motion.DecisionType = majority_requirement
        motion.Result = vote_result
        motion.MotionText = vote_document_text
        motion.Subject = vote_question_text
        motion.billCode = document_name
        motion.Bill_obj = bill
        motion.Yeas = yeas
        motion.Nays = nays
        motion.Present = present
        motion.Absent = absent
        motion.is_official = True
        motion.save()

        yea_count = 0
        nay_count = 0
        present_count = 0
        np_count = 0
        unknown_count = 0
        total_count = 0

        result_data = {'Parties':[], 'Votes':[], 'PartyData':{}}
        members = root.find('members')
        for member in members:
            member_full = member.find('member_full').text
            last_name = member.find('last_name').text
            first_name = member.find('first_name').text
            party_short = member.find('party').text
            stateShort = member.find('state').text
            voteValue = member.find('vote_cast').text
            lis_member_id = member.find('lis_member_id').text

            if party_short == 'R':
                party_name = 'Republican'
            elif party_short == 'D':
                party_name = 'Democrat'
            elif party_short == 'I':
                party_name = 'Independent'
            else:
                party_name = party_short
            found = False
            for i in result_data['Parties']:
                if i['Name'] == party_name:
                    i['Count'] += 1
                    found = True
                    break
            if not found:
                result_data['Parties'].append({'Name':party_name, 'Count':1})

            stateName = state_list[stateShort]
            personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__Position__contains='Senator', data__member_detail__icontains=member_full).first()
            if not personU:
                personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__Position__contains='Senator', data__LastName__icontains=last_name, data__FirstName__icontains=first_name).first()

            if personU:
                p = personU.Pointer_obj
                vote, voteU, vote_is_new = get_model_and_update('RepVote', Motion_obj=motion, Person_obj=p, PersonFullName=f'{personU.data["LastName"]}, {personU.data["FirstName"]}', Chamber='Senate', ConstituencyProvStateName=stateName, CaucusName=party_name, Country_obj=country, Government_obj=motion.Government_obj, Region_obj=country)
            else:
                p = None
                memberName = last_name + ', ' + first_name
                vote, voteU, vote_is_new = get_model_and_update('RepVote', Motion_obj=motion, PersonFullName=memberName, Chamber='Senate', ConstituencyProvStateName=stateName, CaucusName=party_name, Country_obj=country, Government_obj=motion.Government_obj, Region_obj=country)
            prnt('person:',p)

            vote.Party_obj = Party.objects.filter(ShortName=party_short, Validator_obj__is_valid=True).first()
            vote.DateTime = vote_dt
            vote.PersonId = lis_member_id
            vote.IsVoteNay = False
            vote.IsVoteYea = False
            vote.IsVotePresent = False
            vote.IsVoteAbsent = False
            vote.VoteValue = voteValue
            if voteValue.lower() == 'no' or voteValue.lower() == 'nay':
                vote.IsVoteNay = True
                nay_count += 1
            elif voteValue.lower() == 'aye' or voteValue.lower() == 'yea':
                vote.IsVoteYea = True
                yea_count += 1
            elif voteValue.lower() == 'present':
                vote.IsVotePresent = True
                present_count += 1
            elif voteValue.lower() == 'not voting':
                vote.IsVoteAbsent = True
                np_count += 1
            else:
                unknown_count += 1
            found = False
            for i in result_data['Votes']:
                if i['Vote'] == voteValue:
                    i['Count'] += 1
                    found = True
                    break
            if not found:
                result_data['Votes'].append({'Vote':voteValue, 'Count':1})
            total_count += 1
            vote, voteU, vote_is_new, log = save_and_return(vote, voteU, log)

        for i in result_data['Parties']:
            party_name = i['Name']
            count = i['Count']
            party = Party.objects.filter(Country_obj=country, Region_obj=country, gov_level='Federal').filter(Q(Name=party_name)|Q(AltName=party_name), Validator_obj__is_valid=True).first()
            if party:
                i['Color'] = party.Color
                i['obj_id'] = party.id
        sorted_votes = sorted(result_data['Votes'], key=lambda item: item['Count'], reverse=True)
        result_data['Votes'] = sorted_votes
        sorted_parties = sorted(result_data['Parties'], key=lambda item: item['Count'], reverse=True)
        result_data['Parties'] = sorted_parties
        motion.result_data = result_data
        motion.TotalVotes = total_count
        motion, motionU, motion_is_new, log = save_and_return(motion, motionU, log)
    return log



def get_general_election_candidates(special=None, dt=None, iden=None):
    
    func = 'get_general_election_candidates'
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    country = Region.supported_objects.filter(nameType='Country', Name='USA').first()
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = Government.objects.filter(Country_obj=country, gov_level='Federal').first()
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')
    

    to_zone = tz.gettz(country.timezone)
    local_dt = now_utc().astimezone(to_zone)
    today = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    # dayOfWeek = today.weekday()
    # prnt(dayOfWeek)

    def get_presidential(dt, log):
        prnt('get_presidential')
        url = f'https://ballotpedia.org/Presidential_candidates,_{dt.year}'

        r = requests.get(url)
        soup = BeautifulSoup(r.content, 'html.parser')
        election = None
        election_date = None
        get_candidates = None
        infobox = soup.find('table',{'class':'infobox'})
        for tr in infobox.find_all('tr'):
            if not election and 'date' in tr.text.lower():
                x = tr.text.lower().find('date')
                dt = tr.text[x:].replace('Date:','').strip()
                election_date = timezonify('est', datetime.datetime.strptime(dt, '%B %d, %Y'))
                prnt('election_date',election_date)
                election, electionU, election_is_new = get_model_and_update('Election', DateTime=election_date, type='Presidential', gov_level='Federal', Chamber='Executive', Country_obj=country, Region_obj=country, Government_obj=gov)
                electionU.data['url'] = url
                if election_is_new:
                    election, electionU, election_is_new, log = save_and_return(election, electionU, log)
            elif election and 'presidential candidates' in tr.text.lower() and get_candidates == None:
                get_candidates = True
            elif election and get_candidates:
                get_candidates = False
                candidate_name = None
                person_page = None
                party = None
                thumbnail_link = None
                get_party = True
                get_candidate = False
                for a in tr.find_all('a'):
                    if get_party:
                        party_name = a['title']
                        prnt('party',party_name)
                        party_name, party_short, alt_name = find_party(party_name=party_name)
                        party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=country, Region_obj=country, gov_level='Federal')
                        if party_is_new:
                            if get_wiki:
                                try:
                                    time.sleep(1)
                                    search_name = party_name + ' american federal political party'
                                    prnt(search_name)
                                    link = wikipedia.search(search_name)[0].replace(' ', '_')
                                    party.Wiki = 'https://en.wikipedia.org/wiki/' + link
                                    prnt('party.Wiki',party.Wiki)
                                except Exception as e:
                                    prnt('party err 8:',str(e))
                                    pass
                            party, partyU, party_is_new, log = save_and_return(party, partyU, log)
                        get_party = False
                        get_candidate = True
                    elif get_candidate:
                        person_page = a['href']
                        candidate_text = a.text
                        x = candidate_text.find(' (')
                        y = candidate_text.find(')')
                        party_short = candidate_text[x+2:y]
                        candidate_name = candidate_text[:x]
                        prnt('candidate',candidate_name)
                        prnt('party_short',party_short)

                        image_grid = soup.find('div',{'class':'image-grid'})
                        for div in image_grid.find_all('div',{'class':'bp-card-round'}):
                            name = div.find('div',{'class':'p-4'})
                            if name:
                                if name.text == candidate_text:
                                    icon = div.find('div',{'class':'icon-container-xl'})
                                    if icon:
                                        img = icon.find('img')
                                        thumbnail_link = img['src']
                                        prnt('thumbnail',thumbnail_link)
                                        break
                        get_party = True
                        get_candidate = False
                if candidate_name:
                    personUpdate = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__FullName=candidate_name).first()
                    if not personUpdate:
                        personUpdate = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__FirstName__icontains=candidate_name.split(' ')[0], data__LastName__icontains=candidate_name.split(' ')[-1]).first()
                    
                    if personUpdate:
                        person, personU, person_is_new = get_model_and_update('Person', id=personUpdate.pointerId, Country_obj=country, Region_obj=country)
                    else:
                        person, personU, person_is_new = get_model_and_update('Person', GovIden=candidate_name, Country_obj=country, Region_obj=country)
                    personU.data['FirstName'] = candidate_name.split(' ')[0]
                    personU.data['LastName'] = candidate_name.split(' ')[-1]
                    personU.data['FullName'] = candidate_name
                    if thumbnail_link:
                        if 'PhotoLink' not in personU.data or personU.data['PhotoLink'] == '':
                            personU.data['PhotoLink'] = thumbnail_link
                    data = {'role':'Presidential Candidate','current':True,'gov_level':'Federal','Election_id':election.id,'election_date':dt_to_string(election_date)}
                    if party:
                        data['Party_id'] = party.id
                    if person_page:
                        data['ballotpedia_link'] = person_page
                    person.update_role(personU, data=data)
                    person, personU, person_is_new, log = save_and_return(person, personU, log)
        return log

    def get_congress(dt, log):
        url = f'https://ballotpedia.org/United_States_Congress_elections,_{dt.year}'

        r = requests.get(url)
        soup = BeautifulSoup(r.content, 'html.parser')
        election_date = None
        infobox = soup.find('table',{'class':'infobox'})
        for tr in infobox.find_all('tr'):
            if not election_date and 'election date' in tr.text.lower():
                dt = tr.text.replace('Election Date','').strip()
                election_date = timezonify('est', datetime.datetime.strptime(dt, '%B %d, %Y'))
                prnt('election_date',election_date)

        tabs = soup.find_all('div',{'role':'tabpanel'})
        for tab in tabs:
            state = None
            caption = tab.find('caption')
            if caption and 'Candidates - 2024' in caption.text:

                c = caption.text.lower().find('candidates')
                state_chamber = caption.text[:c]
                if 'House' in state_chamber:
                    chamber = 'House'
                    state_name = state_chamber.replace('House','').strip()
                elif 'Senate' in state_chamber:
                    chamber = 'Senate'
                    state_name = state_chamber.replace('Senate','').strip()
                
                if election_date:
                    election, electionU, election_is_new = get_model_and_update('Election', DateTime=election_date, type='Congressional', gov_level='Federal', Chamber=chamber, Country_obj=country, Region_obj=country, Government_obj=gov)
                    electionU.data['url'] = url
                    if election_is_new:
                        election, electionU, election_is_new, log = save_and_return(election, electionU, log)

                    state = Region.objects.filter(Name__icontains=state_name, nameType='State', ParentRegion_obj=country).first()

                    prnt('\n---',caption.text)
                    tbody = tab.find('tbody')
                    for tr in tbody.find_all('tr'):
                        candidate_name = None
                        person_page = None
                        thumbnail_link = None
                        party = None
                        district = None
                        candidate_status = None
                        for td in tr.find_all('td'):
                            if td['data-cell'] == 'candidate':
                                info = td.find('div',{'class':'widget-candidate-info'})
                                candidate_name = info.text
                                a = info.find('a')
                                person_page = a['href']

                        thumb = td.find('div',{'class':'widget-candidate-thumbnail'})
                        if thumb:
                            img = thumb.find('img')
                            if img:
                                thumbnail_link = img['src']

                        if td['data-cell'] == 'party':
                            span = td.find('span',{'class':'party-affiliation'})
                            if span:
                                party_name = span.text
                                party_name, party_short, alt_name = find_party(party_name=party_name)
                                party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=country, Region_obj=country, gov_level='Federal')
                                if party_is_new:
                                    if get_wiki:
                                        try:
                                            time.sleep(1)
                                            search_name = party_name + ' american federal political party'
                                            prnt(search_name)
                                            link = wikipedia.search(search_name)[0].replace(' ', '_')
                                            party.Wiki = 'https://en.wikipedia.org/wiki/' + link
                                            prnt('party.Wiki',party.Wiki)
                                        except Exception as e:
                                            prnt('party err 89:',str(e))
                                            pass
                                    party, partyU, party_is_new, log = save_and_return(party, partyU, log)

                        if td['data-cell'] == 'office':
                            a = td.find('a')
                            if a:
                                office_name = a.text
                                x = office_name.find(state_name)+len(state_name)
                                district_name = office_name[x:].strip()
                                district = District.objects.filter(Name__iexact=district_name, Country_obj=country, Region_obj=country, ProvState_obj=state, gov_level='Federal', nameType='Congressional District').first()

                        if td['data-cell'] == 'status':
                            if 'on the ballot' in td.text.lower() and 'general' in td.text.lower():
                                candidate_status = td.text
                                for span in td.find_all('span',{'class':'sub-detail'}):
                                    candidate_status = candidate_status.replace(span.text,'')    

                    if candidate_status:
                        prnt('candidate_name',candidate_name)
                        prnt('party',party)
                        prnt('district',district)
                        prnt('candidate_status',candidate_status)    
                        prnt('') 
                    if candidate_name:
                        personUpdate = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__FullName=candidate_name).first()
                        if not personUpdate:
                            personUpdate = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__FirstName__icontains=candidate_name.split(' ')[0], data__LastName__icontains=candidate_name.split(' ')[-1]).first()
                        
                        if personUpdate:
                            person, personU, person_is_new = get_model_and_update('Person', id=personUpdate.pointerId, Country_obj=country, Region_obj=country)
                        else:
                            person, personU, person_is_new = get_model_and_update('Person', GovIden=candidate_name, Country_obj=country, Region_obj=country)
                        
                        personU.data['FirstName'] = candidate_name.split(' ')[0]
                        personU.data['LastName'] = candidate_name.split(' ')[-1]
                        personU.data['FullName'] = candidate_name
                        if thumbnail_link:
                            if 'PhotoLink' not in personU.data or personU.data['PhotoLink'] == '':
                                personU.data['PhotoLink'] = thumbnail_link
                        r = f'{chamber} Candidate'
                        data = {'role':r,'current':True,'gov_level':'Federal','Election_id':election.id,'election_date':dt_to_string(election_date),'ProvState_id':state.id,'status':candidate_status}
                        if party:
                            data['Party_id'] = party.id
                        if person_page:
                            data['ballotpedia_link'] = person_page
                        if district:
                            data['District_id'] = district.id
                        person.update_role(personU, data=data)
                        person, personU, person_is_new, log = save_and_return(person, personU, log)
        return log
    
    if today.day <= 7 or special == 'testing':
        log = get_presidential(local_dt, log)
        log = get_congress(local_dt, log)

    else:
        pres_election = Election.objects.filter(DateTime__gte=local_dt + datetime.timedelta(days=90), type='Presidential', gov_level='Federal', Chamber='Executive', Country_obj=country, Region_obj=country).first()
        if pres_election:
            log = get_presidential(local_dt, log)
        
        cong_election = Election.objects.filter(DateTime__gte=local_dt + datetime.timedelta(days=90), type='Congressional', gov_level='Federal', Country_obj=country, Region_obj=country).first()
        if cong_election:
            log = get_congress(local_dt, log)

    return finishScript(log, gov, special)

def get_general_elections_results(special=None, dt=None, iden=None):
    func = 'get_general_elections_results'
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    country = Region.supported_objects.filter(nameType='Country', Name='USA').first()
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = Government.objects.filter(Country_obj=country, gov_level='Federal').first()
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')
    
    url = 'https://ballotpedia.org/Election_results,_2024#Results_summary'

    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html.parser')
    votebox = soup.find('div',{'class':'votebox'})
    header = votebox.find('div',{'race_header'})
    if 'Presidential' in header.text:
        tbody = votebox.find('tbody')
        for tr in tbody.find_all('tr'):
            try:
                td = tr.find_all('td')
                for a in td[2].find_all('a'):
                    prnt(a.text)
                percentage = td[3].find('div',{'class':'percentage_number'})
                if percentage:
                    prnt(percentage.text)
                
                pop_votes = td[4].text
                prnt(pop_votes)
                elec_votes = td[5].text
                prnt(elec_votes)
            except:
                pass
        
    # example prntout

    # Electoral votes

    # Donald Trump
    # J.D. Vance
    # 50.5
    # 19,784,173
    # 168

    # Kamala D. Harris
    # Tim Walz
    # 48.7
    # 19,088,078
    # 92

    # Chase Oliver
    # Mike ter Maat
    # 0.3
    # 120,247
    # 0

    # Jill Stein
    # 0.3
    # 118,108
    # 0

    # Robert F. Kennedy Jr.
    # Nicole Shanahan
    # 0.1
    # 45,191
    # 0

    # Peter Sonski
    # Lauren Onak
    # 0.0
    # 12,893
    # 0
    return finishScript(log, gov, special)



def get_user_region(address=None, city=None, zip_code=None, state=None, special=None, dt=None, iden=None):
    func = 'get_user_region'
    prnt(f'--{func} USA', now_utc())
    dt = declare_var(dt, now_utc())
    country = Region.supported_objects.filter(nameType='Country', Name='USA').first()
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = Government.objects.filter(Country_obj=country, gov_level='Federal').first()
    # if not special:
    #     logEvent('scrapeAssignment: ' + country.Name + ' ' + func + ' ' + str(now_utc()))
    if not address:
        address = '721 5th avenue'
        city = 'New York City'
        zip_code = '10022'
        state = 'New York'

    try:
        from sonet.special.api_keys import google_civicInfo
    except:
        google_civicInfo = '1111'
    url = f'https://civicinfo.googleapis.com/civicinfo/v2/representatives?address={address} {city}, {state} {zip_code}&key={google_civicInfo}'
    prnt(url)
    r = requests.get(url)
    data = r.json()
        
    context = {'country':[], 'administrativeArea1':[], 'administrativeArea2':[], 'locality':[], 'unknown':[]}

    for i in data['divisions']:
        try:
            level = 'unknown'
            # prnt('division:',data['divisions'][i])
            indices = data['divisions'][i]['officeIndices']
            # for n in indices:
            #     officials = data['officials'][n]
            # prnt('--offices:')
            for n in indices:
                temp = {'division':data['divisions'][i], 'offices':[]}
                officeData = data['offices'][n]
                # prnt('office:',officeData)
                level = officeData['levels'][0]
                # prnt('level:',level)
                office = {'office':officeData, 'officials':[]}
                officialIndices = officeData['officialIndices']
                # prnt('--officials:')
                for o in officialIndices:
                    # prnt(data['officials'][o])
                    office['officials'].append(data['officials'][o])
                temp['offices'].append(office)
                context[level].append(temp)
        except:
            pass

    prnt('next\n')
    def process_me(level, returnData, log):
        prnt('ROCESS ME:',level)
        if level == 'locality':
            gov_level = 'City'
        elif level == 'administrativeArea2':
            gov_level = 'County'
        elif level == 'administrativeArea1':
            gov_level = 'State'
        elif level == 'country':
            gov_level = 'Federal'

        # "administrativeArea1"
        # "administrativeArea2"
        # "country"
        # "international"
        # "locality"
        # "regional"
        # "special"
        # "subLocality1"
        # "subLocality2"
        if gov_level not in returnData:
            returnData[gov_level] = {}
        for i in context[level]:

            # prnt(i['division'])
            prnt(i['division']['name'])
            for office in i['offices']:
                # prnt(office['office'])
                person = None
                chamber = None
                state = None
                district = None
                region = None
                office_name = office['office']['name']
                if 'U.S. Representative' in office_name:
                    office_name = 'Congressional Representaive'
                    chamber = 'House'
                if 'Senator' in office_name:
                    office_name = 'Senator'
                    chamber = 'Senate'
                if 'President' in office_name:
                    chamber = 'Executive'
                prnt(office_name)
                returnData[gov_level][office_name] = []
                prnt('roles:')
                for r in office['office']['roles']:
                    prnt(r)
                iden = office['office']['divisionId']
                prnt(iden)
                if 'state:' in iden:
                    a = iden.find('state:')+len('state:')
                    b = iden[a:].find('/')
                    if b > 0:
                        state_short_name = iden[a:a+b]
                        prnt('get provstate:', state_short_name)
                    else:
                        state_short_name = iden[a:]
                        prnt('get provstate:', state_short_name)
                    state_name = state_list[state_short_name.upper()]
                    state = Region.objects.filter(Name=state_name, ParentRegion_obj=country, nameType='State').first()
                    if not state:
                        state = Region(Name=state_name, ParentRegion_obj=country, nameType='State', AbbrName=state_short_name.upper(), Office_array=[office_name], func=func)
                        state.update_data()
                        log.updateShare(state)
                if 'cd:' in iden:
                    a = iden.find('cd:')+len('cd:')
                    district_name = iden[a:]
                    prnt('get congressionsiaonl district', district_name)
                    chamber = 'House'
                    district = District.objects.filter(Name=district_name, ProvState_obj=state, gov_level=gov_level).first()
                    if not district:
                        district = District(Name=district_name, ProvState_obj=state, gov_level=gov_level, Country_obj=country, Chamber=chamber, nameType='Congressional District', Office_array=[office_name], func=func)
                        district.update_data()
                        log.updateShare(district)
                    elif not district.Office_array or office_name not in district.Office_array:
                        district = district.propose_modification()
                        district.add_office(office_name)
                        log.updateShare(district)
                elif 'sldl:' in iden:
                    a = iden.find('sldl:')+len('sldl:')
                    state_assembly_district = iden[a:]
                    prnt('get state assembly district', state_assembly_district)
                    chamber = 'House'
                    district = District.objects.filter(Name=state_assembly_district, ProvState_obj=state, gov_level=gov_level, Chamber=chamber).first()
                    if not district:
                        district = District(Name=state_assembly_district, ProvState_obj=state, gov_level=gov_level, Country_obj=country, Chamber=chamber, nameType='Assembly District', Office_array=[office_name], func=func)
                        district.update_data()
                        log.updateShare(district)
                    elif not district.Office_array or office_name not in district.Office_array:
                        district = district.propose_modification()
                        district.add_office(office_name)
                        log.updateShare(district)
                elif 'sldu:' in iden:
                    a = iden.find('sldu:')+len('sldu:')
                    state_senate_district = iden[a:]
                    prnt('get state senate district', state_senate_district)
                    chamber = 'Senate'
                    district = District.objects.filter(Name=state_senate_district, ProvState_obj=state, gov_level=gov_level, Chamber=chamber).first()
                    if not district:
                        district = District(Name=state_senate_district, ProvState_obj=state, gov_level=gov_level, Country_obj=country, Chamber=chamber, nameType='State District', Office_array=[office_name], func=func)
                        district.update_data()
                        log.updateShare(district)
                    elif not district.Office_array or office_name not in district.Office_array:
                        district = district.propose_modification()
                        district.add_office(office_name)
                        log.updateShare(district)
                elif 'county:' in iden:
                    a = iden.find('county:')+len('county:')
                    # county_name = iden[a:].replace('_',' ').title()
                    county_name = i['division']['name']
                    prnt('get county', county_name)
                    region = Region.objects.filter(Name=county_name, ParentRegion_obj=state, nameType='County').first()
                    if not region:
                        region = Region(Name=county_name, ParentRegion_obj=state, nameType='County', Office_array=[office_name], func=func)
                        region.update_data()
                        log.updateShare(region)
                    # region.add_office(office_name)
                    elif not region.Office_array or office_name not in region.Office_array:
                        region = region.propose_modification()
                        region.add_office(office_name)
                        log.updateShare(region)
                elif 'place:' in iden:
                    a = iden.find('place:')+len('place:')
                    # locality_name = iden[a:].replace('_',' ').title()
                    locality_name = i['division']['name']
                    prnt('get municpality', locality_name)
                    region = Region.objects.filter(Name=locality_name, ParentRegion_obj=country, nameType='City').first()
                    if not region:
                        region = Region(Name=locality_name, ParentRegion_obj=country, nameType='City', Office_array=[office_name], func=func)
                        region.update_data()
                        log.updateShare(region)
                    elif not region.Office_array or office_name not in region.Office_array:
                        region = region.propose_modification()
                        region.add_office(office_name)
                        log.updateShare(region)
                prnt('-')
                for p in office['officials']:
                    # prnt(p)
                    if not region:
                        region = country
                    if 'name' in p:
                        person_name = p['name']
                        prnt('----PERSON NASME---',person_name, office_name)
                        z = person_name.find(',')
                        if z > 0:
                            p_name2 = person_name[:z]
                        else:
                            p_name2 = person_name
                        role = None
                        xRoles = Role.objects.filter(Position=office_name, Country_obj=country, gov_level=gov_level, Person_obj__FullName__icontains=p_name2)
                        # prnt(xRoles)
                        roleU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Role), pointerId__in=[i.id for i in xRoles], data__contains={'Current': True}).first()
                        # prnt(roleU)
                        if roleU:
                            # prnt('11')
                            role = xRoles.filter(id=roleU.pointerId).first()
                            # prnt(role)
                            person = role.Person_obj
                        else:
                            # prnt('else')
                            person = Person.objects.filter(FullName__icontains=p_name2, Country_obj=country).first()
                            if not person:
                                names = p_name2.split(' ')
                                person = Person.objects.filter(FirstName__icontains=names[0], LastName__icontains=names[-1], Country_obj=country).first()
                                if not person:
                                    person = Person(FirstName=names[0], LastName=names[-1], FullName=person_name, Country_obj=country, func=func)
                                    person.update_data()
                                    log.updateShare(person)

                        person.Position = office_name
                        if role:
                            role, roleU, role_is_new = get_model_and_update('Role', obj=role)
                        else:
                            role, roleU, role_is_new = get_model_and_update('Role', Person_obj=person, Position=office_name, Chamber=chamber, gov_level=gov_level, ProvState_obj=state, Country_obj=country, Region_obj=region, District_obj=district)

                    if 'address' in p:
                        if role_is_new:
                            role.Addresses = []
                        else:
                            roleU.data['Addresses'] = []
                        for a in p['address']:
                            prnt('address:')
                            prnt(a['line1'])
                            prnt(a['city'])
                            prnt(a['state'])
                            prnt(a['zip'])
                            addr = a['line1'] + ' ' + a['city'] + ' ' + a['state'] + ' ' + a['zip']
                            if role_is_new:
                                role.Addresses.append(addr)
                            else:
                                roleU.data['Addresses'].append(addr)
                        # prnt(p['address'])
                    if 'party' in p:
                        party_name = p['party'].replace(' Party','')
                        prnt(party_name)
                        party = Party.objects.filter(Name=party_name, Country_obj=country, gov_level=gov_level).first()
                        if not party:
                            party = Party(Name=party_name, Country_obj=country, gov_level=gov_level, ProvState_obj=state, Region_obj=region, func=func)
                            party.update_data()
                            log.updateShare(party)
                        person.Party_obj = party
                        role.Party_obj = party
                        # if not role_is_new:
                        #     roleU.Party_obj = party
                    if 'phones' in p:
                        prnt('telephone:')
                        for t in p['phones']:
                            prnt(t)
                        person.Telephones = p['phones']
                        role.Telephones = p['phones']
                        if not role_is_new:
                            roleU.data['Telephones'] = p['phones']
                    if 'photoUrl' in p:
                        photo_url = p['photoUrl']
                        prnt(photo_url)
                        person.PhotoLink = photo_url
                        role.PhotoLink = photo_url
                        if not role_is_new:
                            roleU.data['PhotoLink'] = photo_url
                    if 'urls' in p:
                        prnt('urls:')
                        person.Websites = []
                        role.Websites = []
                        for u in p['urls']:
                            prnt(u)
                            if 'wiki' in u:
                                person.Wiki = u
                            else:
                                person.Websites.append(u)
                                role.Websites.append(u)
                            if '.gov' in u:
                                role.GovPage = u
                                if not role_is_new:
                                    roleU.data['GovPage'] = u
                    if 'emails' in p:
                        prnt('emails:')
                        for e in p['emails']:
                            prnt(e)
                        person.Emails = p['emails']
                        role.Emails = p['emails']
                        if not role_is_new:
                            roleU.data['Emails'] = p['emails']
                    if 'channels' in p:
                        prnt('socials:')
                        for c in p['channels']:
                            prnt(c['type'])
                            prnt(c['id'])
                        person.Socials = p['channels']
                        role.Socials = p['channels']
                        if not role_is_new:
                            roleU.data['Socials'] = p['channels']
                    person.func = func
                    person.update_data()
                    roleU.data['Current'] = True
                    roleU.data['Position'] = office_name
                    role, roleU, role_is_new, log = save_and_return(role, roleU, log)
                    # try:
                    xRoles = Role.objects.filter(Position=office_name, Country_obj=country, gov_level=gov_level).exclude(Person_obj=person)
                    previousRoleUs = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Role), pointerId__in=[i.id for i in xRoles], data__contains={'Current': True})
                    for u in previousRoleUs:
                        # data = json.loads(u.data)
                        u.data['Current'] = False
                        # u.data = json.dumps(data)
                        u.save()
                        log.updateShare(u)


                    prnt()
                    returnData[gov_level][office_name].append(role.id)
            prnt('-----')
        prnt()
        prnt()
        return returnData, log
    returnData = {}
    returnData, log = process_me('country', returnData, log)
    returnData, log = process_me('administrativeArea1', returnData, log)
    returnData, log = process_me('administrativeArea2', returnData, log)
    returnData, log = process_me('locality', returnData, log)
    prnt(context['unknown'])

    prnt('returnData:', returnData)

    for i in log:
        skip = False
        if i.objType == 'Update':
            post = Post.objects.filter(pointerId=i.pointerId).first()
            if not post:
                if has_method(i, 'boot'):
                    i.get_pointer().boot()
                    post = Post.objects.filter(pointerId=i.pointerId).first()
                if not post:
                    skip = True
            if not skip and post.Update_obj != i:
                if post.Update_obj:
                    # post.Update_obj.delete()
                    post.Update_obj.log_deletion(data={'replaced_by':i.id})
                # this will need validation and update.sync_with_post
                post.Update_obj = i
                post.DateTime = i.DateTime
                post.save()

    if special:
        return return_test_result(log)
    elif super:
        super_share(log, gov, func)
    else:
        # send_for_validation(log, gov, func)
        return returnData, log


