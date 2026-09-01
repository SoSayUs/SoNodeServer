

from django.contrib.contenttypes.models import ContentType
import django_rq

from accounts.models import *
from legis.models import *
from legis.utils import get_gov, get_region, modify_gov, add_gov_menu_item
from posts.models import *
from utils.models import (
    timezonify, dt_to_string, open_browser, finishScript, create_share_object, 
    logEvent, testing, declare_var, save_and_return,
    save_image
    )

import datetime
from dateutil.parser import parse
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import pytz
import time
import re
import json
import operator

from selenium import webdriver 
from selenium.webdriver.common.by import By 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

province_list = {
    "Alberta": "AB",
    "British Columbia": "BC",
    "Manitoba": "MB",
    "New Brunswick": "NB",
    "Newfoundland and Labrador": "NL",
    "Northwest Territories": "NT",
    "Nova Scotia": "NS",
    "Nunavut": "NU",
    "Ontario": "ON",
    "Prince Edward Island": "PE",
    "Quebec": "QC",
    "Saskatchewan": "SK",
    "Yukon": "YT"
}
prov_or_terr = {
    "Alberta": "Province",
    "British Columbia": "Province",
    "Manitoba": "Province",
    "New Brunswick": "Province",
    "Newfoundland and Labrador": "Province",
    "Northwest Territories": "Territory",
    "Nova Scotia": "Province",
    "Nunavut": "Territory",
    "Ontario": "Province",
    "Prince Edward Island": "Province",
    "Quebec": "Province",
    "Saskatchewan": "Province",
    "Yukon": "Territory"
}

runTimes = {
    'initialize_region' : 1000,
    'get_bills' : 1000, 'get_senate_bills' : 1000, 'get_house_bills' : 1000, 'get_all_bills' : 7200, 
    'get_house_agendas' : 200, 'get_house_debates' : 1000, 'get_senate_debates' : 1000,
    'get_house_persons' : 2000, 'get_senate_persons' : 2000, 'get_senate_agendas' : 200,
    'get_house_motions' : 200, 'get_senate_motions' : 200, 'get_senate_committees' : 200, 'get_house_expenses' : 600,
    'get_todays_xml_agenda' : 1000, 'get_house_committees' : 1000, 'get_upcoming_senate_committees' : 200,
    }

typical = ['get_house_agendas', 'get_senate_agendas', 'get_todays_xml_agenda',
    ]

functions = { # in gov_region timezone
    "2025-03-13" : [
    # {'date' : [1], 'dayOfWeek' : ['x'], 'hour' : [2], 'cmds' : ['get_house_expenses']},
    {'date' : ['x'], 'dayOfWeek' : [6,2], 'hour' : [5], 'cmds' : ['get_house_persons', 'get_senate_persons']},
    # # mon - sat
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [8, 10, 12, 18, 24], 'cmds' : ['get_house_agendas'] },
    # {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [8, 10, 12, 18, 24], 'cmds' : ['get_house_agendas', 'get_senate_agendas', 'get_todays_xml_agenda'] },
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [3, 7, 10, 12, 13, 15, 17, 20, 23], 'cmds' : ['get_bills'] },
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [2, 6, 12, 18, 22], 'cmds' : ['get_house_debates', 'get_house_motions']},
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [4, 8, 13, 19, 23], 'cmds' : ['get_senate_debates', 'get_senate_motions']},
    # {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [0, 24], 'cmds' : ['get_senate_debates']},
    ],
}

approved_models = {
    'initialize_region' : ['Government', 'Agenda', 'AgendaTime', 'AgendaItem', 'Person', 'Party', 'District', 'Region', 'ImageFile'],
    'get_house_agendas' : ['Government', 'Agenda', 'AgendaTime', 'AgendaItem'],
    'get_house_persons' : ['Government', 'Person', 'Party', 'District', 'Region', 'ImageFile'],
    'get_senate_persons' : ['Government', 'Person', 'District', 'Party', 'Region', 'ImageFile'],
    'get_bills' : ['Bill', 'BillText', 'Committee', 'Meeting', 'Government', 'Notification', 'Person'],
    'get_house_bills' : ['Bill', 'BillVersion', 'Role', 'Person', 'Notification'],
    'get_senate_bills' : ['Bill', 'BillVersion', 'Role', 'Person', 'Notification'],
    'get_house_debates' : ['Meeting', 'Statement', 'Agenda', 'Government', 'Person', 'Bill'],
    'get_senate_debates' : ['Meeting', 'Statement', 'Bill'],
    'get_house_motions' : ['Government', 'Motion', 'RepVote', 'Interaction', 'Person'],
    'get_senate_motions' : ['Government', 'Motion', 'RepVote', 'Interaction'],
    'get_user_region' : ['District', 'Region', 'Role', 'Party', 'Person'],
}

gov_logo_links = {"House": "img/regions/canada/house.png", "Senate": "img/regions/canada/senate.png"}

get_wiki = not testing()

def initialize_region(special=None, dt=None, iden=None):
    get_house_agendas(special=special, iden=iden)
    get_house_persons(special=special, iden=iden)
    get_senate_persons(special=special, iden=iden)
        

def find_party(party_short=None, party_name=None):
    party_list = {
        'Liberal':{'short':'L','alt':'Lib'},
        'Conservative':{'short':'C','alt':'Con'},
        'NDP':{'short':'NDP','alt':'New Democratic Party'},
        'Green Party':{'short':'G','alt':'Greens'},
        'Bloc Quebecios':{'short':'BQ','alt':'Bloc'},
        "People's Party":{'short':'PP','alt':'Peoples'},
        "Progressive Senate Group":{'short':'PSG','alt':'Progressive'},
        "Canadian Senators Group":{'short':'CSG','alt':'CSG'},
        "Independent Senators Group":{'short':'ISG','alt':'Independent Group'},
        "Non-affiliated":{'short':'NA','alt':'Independent'},
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
    

def get_house_persons(special=None, value='current', dt=None, iden=None, func='get_house_persons'):
    prnt(f'--{func} Canada', now_utc())
    dt = declare_var(dt, now_utc())
    gov = None
    country = get_region('Canada')
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = get_gov(country)
    gov = modify_gov(gov, [{'Office_array':'Member of Parliament'},{'Chamber_array':'House'},{'menuItem_array':'Officials'}])
    log.updateShare(gov)
    
    if not special:
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')

    def get_data(url, log):
        current_mps = []
        r = requests.get(url)
        # r = proxy_request(url, country='CA')
        soup = BeautifulSoup(r.content, 'html.parser')
        m_list = []
        members = soup.find_all('div', {'class':'ce-mip-mp-tile-container'})
        for member in members:
            a = member.find('a',{'class':'ce-mip-mp-tile-link'})
            page = 'https://www.ourcommons.ca' + a['href']
            img = member.find(['img'])
            picture = 'https://www.ourcommons.ca' + img['src']
            name = member.find('div', {'class':'ce-mip-mp-name'}).text
            party = member.find('div', {'class':'ce-mip-mp-party'}).text
            con = member.find('div', {'class':'ce-mip-mp-constituency'}).text
            prov_name = member.find('div', {'class':'ce-mip-mp-province'}).text
            AbbrName = None
            if prov_name in province_list:
                AbbrName = province_list[prov_name]
            if prov_name in prov_or_terr:
                region_type = prov_or_terr[prov_name]
            else:
                region_type = 'Province'
            prov = Region.objects.filter(Name=prov_name, AbbrName=AbbrName, nameType=region_type, ParentRegion_obj=log.Region_obj, Validator_obj__is_valid=True).first()
            if not prov:
                prov = Region(func=func, Name=prov_name, AbbrName=AbbrName, nameType=region_type, ParentRegion_obj=log.Region_obj)
                prov.save()
            if not prov.Validator_obj or not prov.Validator_obj.is_valid:
                log.updateShare(prov)

            a = page.find('(')+1
            b = page[a:].find(')')
            iden = page[a:a+b]
            m = {}
            m['name'] = name
            m['picture'] = picture
            m['link'] = page
            m['iden'] = iden
            m_list.append(m)
        
        url = 'https://www.ourcommons.ca/Members/en/search/XML'
        r = requests.get(url)
        root = ET.fromstring(r.content)
        members = root.findall('MemberOfParliament')
        for member in members:
            first = member.find('PersonOfficialFirstName').text
            last = member.find('PersonOfficialLastName').text
            prntDebug(first, last)
            elected = member.find('FromDateTime').text
            elecdate = timezonify('est', datetime.datetime.strptime(elected, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.UTC))
            for m in m_list:
                if first in m['name'] and last in m['name']:
                    person, personU, person_is_new = get_model_and_update('Person', GovProfilePage=m['link'], Country_obj=log.Region_obj, Region_obj=log.Region_obj)
                    if person_is_new:
                        personU.data['FirstName'] = first
                        personU.data['LastName'] = last
                        personU.data['FullName'] = first + ' ' + last
                        personU.data['PhotoLink'] = m['picture']
                        person.GovIden = m['iden']
                        # must save person before profile info can be assigned
                        person, personU, person_is_new, log = save_and_return(person, personU, log)

                    if personU.data['PhotoLink'] and not ImageFile.objects.filter(pointerId=person.id, Validator_obj__is_valid=True).exists():
                        img_url = personU.data['PhotoLink']
                        try:
                            img_obj = save_image(img_url, f'legis/canada/', pointerId=person.id, region=country)
                            log.updateShare(img_obj)
                        except Exception as e:
                            prnt('img err121',str(e))
                    time.sleep(1.5)
                    log = get_MP(person, personU, person_is_new, log, chamber='House')
                    current_mps.append(person.id)
                    break
        prntDebug('done get_data')
        return current_mps, log
    if value == 'alltime':
        parliaments = ['44', '43', '42', '41', '40', '39', '38', '37', '36']
        for p in parliaments:
            url = 'https://www.ourcommons.ca/Members/en/search/xml?parliament=%s&caucusId=all&province=all&gender=all' %(p)
            current_mps, log = get_data(url, log)
    elif value == 'current':
        url = 'https://www.ourcommons.ca/Members/en/search'
        current_mps, log = get_data(url, log)
        prntDebug('len:', len(current_mps))
        if len(current_mps) > 300:
            repUpdates = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, extra__roles__contains=[{'role':'Member of Parliament','current':True, 'gov_level':'Federal'}]).exclude(pointerId__in=current_mps)
            for u in repUpdates:
                prntDebug('removing:::',u.pointerId)
                update = u.create_next_version()
                if 'Position' in update.data and update.data['Position'] == 'Member of Parliament':
                    del update.data['Position']
                
                data = {'role':'Member of Parliament','current':True,'gov_level':'Federal'}
                update.Pointer_obj.update_role(update, data=data)
                update, u_is_new = update.save_if_new(func=func)
                if u_is_new:
                    log.updateShare(update)                    
    
    prntDebug('done gather mps')
    return finishScript(log, gov, special)

def get_MP(person, personU, person_is_new, log, chamber='House'):
    func = 'get_mp'
    prnt(f'--{func} Canada', now_utc())
    if chamber == 'House':
        office = 'Member of Parliament'
    elif chamber == 'Senate':
        office = 'Senator'
    else:
        office = None
    if 'http' not in person.GovProfilePage:
        url = 'https:%s/roles' %(person.GovProfilePage)
    else:
        url = '%s/roles' %(person.GovProfilePage)
    if not person.GovIden:
        a = person.GovProfilePage.find('members/')+len('members/')
        person.GovIden = person.GovProfilePage[a:]
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html.parser')
    h1 = soup.find('h1', {'class':'mt-0'}).text

    if 'Hon' in h1:
        personU.data['Honorific'] = 'Hon.'
    if not personU.data['PhotoLink']:
        try:
            div = soup.find('div', {'class':'ce-mip-mp-picture-container'})
            img = div.find('img')['src']
            personU.data['PhotoLink'] = 'https://www.ourcommons.ca' + img
        except:
            pass
    try:
        personU.data['Position'] = office
        party_name = soup.find('div', {'class':'ce-mip-mp-party'})
        party_name = party_name.text
        party_name, party_short, alt_name = find_party(party_name=party_name)
        party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=log.Region_obj, Region_obj=log.Region_obj, gov_level='Federal')
        if party_is_new and get_wiki:
            try:
                time.sleep(1)
                search_name = f'Canadian {party_name} federal political party'
                prnt(search_name)
                link = wikipedia.search(search_name)[0].replace(' ', '_')
                party.Wiki = 'https://en.wikipedia.org/wiki/' + link
                prnt('party.Wiki',party.Wiki)
            except Exception as e:
                prnt('party err:',str(e))
                pass
        party, partyU, party_is_new, log = save_and_return(party, partyU, log)
        prov_name = soup.find('div', {'class':'ce-mip-mp-province'}).text
        prov = Region.objects.filter(Name=prov_name, nameType='Province', ParentRegion_obj=log.Region_obj, Validator_obj__is_valid=True).first()
        constituency_name = soup.find('div', {'class':'ce-mip-mp-constituency'}).text
        district = District.objects.filter(Q(Name=constituency_name)|Q(AltName=constituency_name.replace('—', ''))).filter(Country_obj=log.Region_obj, Region_obj=log.Region_obj, ProvState_obj=prov, gov_level='Federal', nameType='Federal District', Validator_obj__is_valid=True).first() # the character being removed is not a regular dash
        if district:
            if not district.Office_array or 'Member of Parliament' not in district.Office_array:
                modded_district = district.propose_modification()
                modded_district.add_office('Member of Parliament')
                district, districtU, district_is_new, log = save_and_return(district, None, log)
        if not district:
            district = District(func=log.data['func'], Name=constituency_name, AltName=constituency_name.replace('—', ''), Country_obj=log.Region_obj, Region_obj=log.Region_obj, ProvState_obj=prov, gov_level='Federal', nameType='Federal District')
            if get_wiki:
                try:
                    time.sleep(1)
                    search_name = f'Canadian federal district of {constituency_name}'
                    prntDebug('search_name',search_name)
                    title = wikipedia.search(search_name)[0].replace(' ', '_')
                    district.Wiki = 'https://en.wikipedia.org/wiki/' + title
                    prntDebug('district.Wiki',district.Wiki)
                except Exception as e:
                    prntDebug(str(e))
            district.add_office(office)
        if not district.Validator_obj or not district.Validator_obj.is_valid:
            log.updateShare(district)
        personU.data['Chamber'] = chamber
        personU.data['District_id'] = district.id
        personU.data['ProvState_id'] = prov.id
        personU.data['Position'] = office
        personU.data['gov_level'] = 'Federal'
        personU.data['Party_id'] = party.id
        person.update_role(personU, data={'role':office,'gov_level':'Federal','current':True})

    except Exception as e:
        prntDebug('fail get mp 345', str(e))

    ordered = 0
    group_link = None
    try:
        prntDebug('roles-mp')
        table = soup.find('table', {'id':'roles-mp'})
        tbody = table.find('tbody')
        roles = tbody.find_all('tr', {'role':'row'})
        ordered += 1
        for r in roles:
            try:
                td = r.find_all('td')
                constituency_name = td[0].text
                province_name = td[1].text
                start = td[2].text
                end = td[3].text
                start_date = timezonify('est', datetime.datetime.strptime(start, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                if end:
                    end_date = timezonify('est', datetime.datetime.strptime(end, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                else:
                    end_date = None
                prov = Region.objects.filter(Name=prov_name, nameType='Province', ParentRegion_obj=log.Region_obj, Validator_obj__is_valid=True).first()
                district = District.objects.filter(Q(Name=constituency_name)|Q(AltName=constituency_name.replace('—', ''))).filter(Country_obj=log.Region_obj, Region_obj=log.Region_obj, ProvState_obj=prov, gov_level='Federal', nameType='Federal District', Validator_obj__is_valid=True).first() #that character being removed is important, it is not a regular dash
                if district:
                    if not district.Office_array or 'Member of Parliament' not in district.Office_array:
                        modded_district = district.propose_modification()
                        modded_district.add_office('Member of Parliament')
                        log.updateShare(modded_district)
                if not district:
                    district = District(func=log.data['func'], Name=constituency_name, AltName=constituency_name.replace('—', ''), Country_obj=log.Region_obj, Region_obj=log.Region_obj, ProvState_obj=prov, gov_level='Federal', nameType='Federal District')
                    district.add_office(office)
                    log.updateShare(district)
                rolData = {'role':office,'chamber':chamber,'gov_level':'Federal','District_id':district.id,'ProvState_id':prov.id,'start_date':dt_to_string(start_date)}
                if end_date == None:
                    rolData['current'] = True
                else:
                    rolData['current'] = False
                    rolData['end_date'] = dt_to_string(end_date)
                person.update_role(personU, data=rolData)
            except Exception as e:
                prntDebug('mp roll error 4092', str(e))
    except Exception as e:
        prntDebug('mp error 23634', str(e))
    try: 
        prntDebug('roles-affiliation')
        table = soup.find('table', {'id':'roles-affiliation'})
        tbody = table.find('tbody')
        roles = tbody.find_all('tr', {'role':'row'})
        ordered += 1
        for r in roles:
            try:
                td = r.find_all('td')
                one = td[0].text
                party_name = td[1].text
                start = td[2].text
                end = td[3].text
                start_date = timezonify('est', datetime.datetime.strptime(start, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                if end:
                    end_date = timezonify('est', datetime.datetime.strptime(end, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                else:
                    end_date = None
                
                party_name, party_short, alt_name = find_party(party_name=party_name)
                party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=log.Region_obj, Region_obj=log.Region_obj, gov_level='Federal')
                if party_is_new:
                    party, partyU, party_is_new, log = save_and_return(party, partyU, log)
                    
                rolData = {'role':'Caucus Member','gov_level':'Federal','Party_id':party.id,'start_date':dt_to_string(start_date)}
                if end_date == None:
                    rolData['current'] = True
                else:
                    rolData['current'] = False
                    rolData['end_date'] = dt_to_string(end_date)
                person.update_role(personU, data=rolData)

            except Exception as e:
                prntDebug('mp role error 643', str(e))
    except Exception as e:
        prntDebug('mp error roles-affiliation 3565', str(e))
    try:
        prntDebug('roles-offices')
        
        table = soup.find('table', {'id':'roles-offices'})
        tbody = table.find('tbody')
        roles = tbody.find_all('tr', {'role':'row'})
        ordered += 1
        # personU.data['GovernmentPosition'] = ''
        for r in roles:
            # prntDebug(r)
            try:
                td = r.find_all('td')
                one = td[0].text
                two = td[1].text
                start = td[2].text
                end = td[3].text
                prnt('start',start)
                prnt('end',end)
                start_date = timezonify('est', datetime.datetime.strptime(start, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                if end:
                    end_date = timezonify('est', datetime.datetime.strptime(end, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                else:
                    end_date = None
                rolData = {'role':'Parliamentary Position','title':two,'parliament_number':one,'gov_level':'Federal','start_date':dt_to_string(start_date)}
                if end_date == None:
                    rolData['current'] = True
                else:
                    rolData['current'] = False
                    rolData['end_date'] = dt_to_string(end_date)
                person.update_role(personU, data=rolData)
            except Exception as e:
                prntDebug('mp role error 6424', str(e))
            
    except Exception as e:
        prntDebug('mp roles-offices error 753', str(e))
    try:
        prntDebug('roles-committees')
        table = soup.find('table', {'id':'roles-committees'})
        tbody = table.find('tbody')
        roles = tbody.find_all('tr', {'role':'row'})
        ordered += 1
        for r in roles:
            try:
                td = r.find_all('td')
                one = td[0].text
                two = td[1].text
                three = td[2].text
                try:
                    group_link = td[2]['src']
                except:
                    pass
                start = td[3].text
                end = td[4].text
                start_date = timezonify('est', datetime.datetime.strptime(start, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                if end:
                    end_date = timezonify('est', datetime.datetime.strptime(end, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                else:
                    end_date = None 
                rolData = {'role':'Committee Member','affiliation':two,'group':three,'parliament_session':one,'gov_level':'Federal','start_date':dt_to_string(start_date)}
                if group_link:
                    rolData['group_link'] = group_link
                if end_date == None:
                    rolData['current'] = True
                else:
                    rolData['current'] = False
                    rolData['end_date'] = dt_to_string(end_date)
                person.update_role(personU, data=rolData)
            except Exception as e:
                prntDebug('mp roles error 18', str(e))
    except Exception as e:
        prntDebug('mp roles-committees error 66', str(e))
    try:
        prntDebug('roles-iia')
        table = soup.find('table', {'id':'roles-iia'})
        tbody = table.find('tbody')
        roles = tbody.find_all('tr', {'role':'row'})
        ordered += 1
        for r in roles:
            try:
                td = r.find_all('td')
                one = td[0].text
                two = td[1].text
                three = td[2].text
                start = td[3].text
                end = td[4].text
                start_date = timezonify('est', datetime.datetime.strptime(start, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                if end:
                    end_date = timezonify('est', datetime.datetime.strptime(end, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                else:
                    end_date = None
                rolData = {'role':'Parliamentary Association','group':three,'parliament_session':one,'gov_level':'Federal','start_date':dt_to_string(start_date)}
                if group_link:
                    rolData['group_link'] = group_link
                if end_date == None:
                    rolData['current'] = True
                else:
                    rolData['current'] = False
                    rolData['end_date'] = dt_to_string(end_date)
                person.update_role(personU, data=rolData)
            except Exception as e:
                prntDebug('mp roles error 54', str(e))
    except Exception as e:
        prntDebug('mp roles-iia error 23', str(e))
    try:
        prntDebug('roles-elections')
        table = soup.find('table', {'id':'roles-elections'})
        tbody = table.find('tbody')
        roles = tbody.find_all('tr', {'role':'row'})
        ordered += 1
        for r in roles:
            try:
                td = r.find_all('td')
                end = td[0].text
                if end:
                    start_date = timezonify('est', datetime.datetime.strptime(end, '%A, %B %d, %Y').replace(tzinfo=pytz.UTC))
                else:
                    start_date = None
                two = td[1].text
                constituency_name = td[2].text
                province_name = td[3].text
                result = td[4].text

                prov = Region.objects.filter(Name=province_name, nameType='Province', ParentRegion_obj=log.Region_obj, Validator_obj__is_valid=True).first()
                district = District.objects.filter(Q(Name=constituency_name)|Q(AltName=constituency_name.replace('—', ''))).filter(Country_obj=log.Region_obj, Region_obj=log.Region_obj, ProvState_obj=prov, gov_level='Federal', nameType='Federal District', Validator_obj__is_valid=True).first() #that character being removed is important, it is not a regular dash
                if district:
                    if not district.Office_array or 'Member of Parliament' not in district.Office_array:
                        modded_district = district.propose_modification()
                        modded_district.add_office('Member of Parliament')
                        log.updateShare(modded_district)
                if not district:
                    district = District(func=log.data['func'], Name=constituency_name, AltName=constituency_name.replace('—', ''), Country_obj=log.Region_obj, Region_obj=log.Region_obj, ProvState_obj=prov, gov_level='Federal', nameType='Federal District')
                    district.add_office(office)
                    log.updateShare(district)
                rolData = {'role':'Election Candidate','result':result,'group':two,'parliament_session':one,'gov_level':'Federal','start_date':dt_to_string(start_date)}
                if group_link:
                    rolData['group_link'] = group_link
                if end_date == None:
                    rolData['current'] = True
                else:
                    rolData['current'] = False
                    rolData['end_date'] = dt_to_string(end_date)
                person.update_role(personU, data=rolData)

            except Exception as e:
                prntDebug('mp roles error 87', str(e))
    except Exception as e:
        prntDebug('mp roles-elections error 90', str(e))
    person, personU, person_is_new, log = save_and_return(person, personU, log)

    prntDebug('done get _MP', url)
    return log

def get_senate_persons(special=None, dt=None, iden=None, func='get_senate_persons'):
    prnt(f'--{func} Canada', now_utc())
    dt = declare_var(dt, now_utc())
    country = get_region('Canada')
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = get_gov(country)
    gov = modify_gov(gov, [{'Office_array':'Senator'},{'Chamber_array':'Senate'},{'menuItem_array':'Officials'}])
    log.updateShare(gov)
    if not gov and country:
        return finishScript(log, gov, special)
    
    if not special:
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')

    prnt('gov',gov)
    chamber = 'Senate'
    url = 'https://sencanada.ca/en/senators'
    driver = open_browser(url, headless=True)
    element_present = EC.presence_of_element_located((By.CLASS_NAME, 'sc-senators-political-card'))
    WebDriverWait(driver, 10).until(element_present)
    s_cards = driver.find_elements(By.CLASS_NAME, 'sc-senators-political-card')
    updated_senators = []
    order_num = 0
    first_batch = []
    for c in s_cards:
        a = c.find_element(By.CSS_SELECTOR, "a").get_attribute('href')
        govPage = a
        # govPage = url + a
        src = c.find_element(By.CSS_SELECTOR, "img").get_attribute('src')
        try:
            title = c.find_element(By.CLASS_NAME, 'sc-senators-political-card-title').text
        except Exception as e:
            prntDebug('get_senate_persons err1',str(e))
            title = None
        prntDebug('title',title)
        h = c.find_element(By.CSS_SELECTOR, 'h5').text
        h1 = h.find(', ')
        last_name = h[:h1]
        first_name = h[h1+2:]
        prntDebug('name',first_name, last_name)
        party = None
        prov = None
        district = None
        region_name = None
        district_name = None
        party_prov = c.find_element(By.CLASS_NAME, 'sc-senators-political-card-text-province').text
        
        if ' - ' in party_prov:
            # PSG - Prince Edward Island (Epekwitk, Mi'kma'ki)
            # ISG - Quebec - Gulf
            # Non-affiliated - Manitoba

            a = party_prov.find(' - ')
            party_short = party_prov[:a]
            party_name, party_short, alt_name = find_party(party_short=party_short)
            party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=log.Region_obj, Region_obj=log.Region_obj, gov_level='Federal')
            if party_is_new and get_wiki:
                try:
                    time.sleep(1)
                    search_name = f'Canadian {party_name} federal political party'
                    prnt(search_name)
                    link = wikipedia.search(search_name)[0].replace(' ', '_')
                    party.Wiki = 'https://en.wikipedia.org/wiki/' + link
                    prnt('party.Wiki',party.Wiki)
                except Exception as e:
                    prnt('party err:',str(e))
                    pass
                
            if ' - ' in party_prov[a+len(' - '):]:
                b = party_prov[a+len(' - '):].find(' - ')
                district_name = party_prov[a+len(' - ')+b+len(' - '):].strip()
                region_name = party_prov[a+len(' - '):a+len(' - ')+b].strip()
            elif ' (' in party_prov[a+len(' - '):]:
                b = party_prov[a+len(' - '):].find('(')
                district_name = party_prov[a+len(' - ')+b+1:].replace(')','').strip()
                region_name = party_prov[a+len(' - '):a+len(' - ')+b].strip()
            else:
                district_name = party_prov[a+len(' - '):].strip()
                region_name = district_name
        prnt('region_name',region_name,'district_name',district_name)
        if region_name:
            AbbrName = None
            if region_name in province_list:
                AbbrName = province_list[region_name]
            if region_name in prov_or_terr:
                region_type = prov_or_terr[region_name]
            else:
                region_type = 'Province'
            prov = Region.objects.filter(Name=region_name, AbbrName=AbbrName, nameType=region_type, ParentRegion_obj=country, Validator_obj__is_valid=True).first()
            if not prov:
                prov = Region(func=func, Name=region_name, AbbrName=AbbrName, nameType=region_type, ParentRegion_obj=country)
                prov.save()
            if not prov.Validator_obj or not prov.Validator_obj.is_valid:
                log.updateShare(prov)

            if district_name:
                district = District.objects.filter(Name=district_name, Country_obj=country, Region_obj=country, ProvState_obj=prov, gov_level='Federal', nameType='Federal District', Validator_obj__is_valid=True).first()
                if district:
                    if not district.Office_array or 'Senator' not in district.Office_array:
                        modded_district = district.propose_modification()
                        modded_district.add_office('Senator')
                        log.updateShare(modded_district)
                else:
                    district = District(func=func, Name=district_name, Country_obj=country, Region_obj=country, ProvState_obj=prov, gov_level='Federal', nameType='Federal District')
                    district.add_office('Senator')
                if not district.Validator_obj or not district.Validator_obj.is_valid:
                    log.updateShare(district)

        person, personU, person_is_new = get_model_and_update('Person', GovProfilePage=govPage, Country_obj=log.Region_obj, Region_obj=log.Region_obj)
        prnt('person:',person)
        
        personU.data['FirstName'] = first_name
        personU.data['LastName'] = last_name
        personU.data['FullName'] = first_name + ' ' + last_name
        personU.data['PhotoLink'] = src
        personU.data['Chamber'] = chamber
        if district:
            personU.data['District_id'] = district.id
        personU.data['ProvState_id'] = prov.id if prov else prov
        personU.data['Position'] = 'Senator'
        personU.data['gov_level'] = 'Federal'
        personU.data['Party_id'] = party.id if party else party
        person.update_role(personU, data={'role':'Senator','gov_level':'Federal','current':True})
        
        order_num += 1
        first_batch.append(govPage)
        updated_senators.append({'link':govPage,'order_num':order_num,'data':{'person':person,'personU':personU,'person_is_new':person_is_new}})
        
    prntDebug('--second list--')
    s_cards = driver.find_elements(By.CLASS_NAME, 'sc-senators-senator-card')
    for c in s_cards:
        a = c.find_element(By.CSS_SELECTOR, "a").get_attribute('href')
        govPage = a
        src = c.find_element(By.CSS_SELECTOR, "img").get_attribute('src')
        name_text = c.find_element(By.CLASS_NAME, 'sc-senators-senator-card-text-name').text
        h1 = name_text.find(', ')
        last_name = name_text[:h1]
        first_name = name_text[h1+2:]
        prntDebug('name',first_name,last_name)
        p = c.find_element(By.CSS_SELECTOR, "p").text
        p1 = p.find(' - ')
        p2 = p[p1+3:]
        try:
            p3 = p2.find(' (')
            provName = p2[:p3]
        except:
            provName = p2
        
        if govPage not in first_batch:
            party = None
            prov = None
            region_name = None
            district_name = None
            party_prov = c.find_element(By.CLASS_NAME, 'sc-senators-senator-card-text-province').text
            if ' - ' in party_prov:
                # PSG - Prince Edward Island (Epekwitk, Mi'kma'ki)
                # ISG - Quebec - Gulf
                # Non-affiliated - Manitoba

                a = party_prov.find(' - ')
                party_short = party_prov[:a]
                party_name, party_short, alt_name = find_party(party_short=party_short)
                party, partyU, party_is_new = get_model_and_update('Party', Name=party_name, AltName=alt_name, ShortName=party_short, Country_obj=log.Region_obj, Region_obj=log.Region_obj, gov_level='Federal')
                if party_is_new and get_wiki:
                    try:
                        time.sleep(1)
                        search_name = f'Canadian {party_name} federal political party'
                        prnt(search_name)
                        link = wikipedia.search(search_name)[0].replace(' ', '_')
                        party.Wiki = 'https://en.wikipedia.org/wiki/' + link
                        prnt('party.Wiki',party.Wiki)
                    except Exception as e:
                        prnt('party err2:',str(e))
                        pass
                    
                if ' - ' in party_prov[a+len(' - '):]:
                    b = party_prov[a+len(' - '):].find(' - ')
                    district_name = party_prov[a+len(' - ')+b+len(' - '):].strip()
                    region_name = party_prov[a+len(' - '):a+len(' - ')+b].strip()
                elif ' (' in party_prov[a+len(' - '):]:
                    b = party_prov[a+len(' - '):].find('(')
                    district_name = party_prov[a+len(' - ')+b+1:].replace(')','').strip()
                    region_name = party_prov[a+len(' - '):a+len(' - ')+b].strip()
                else:
                    district_name = party_prov[a+len(' - '):].strip()
                    region_name = district_name

            prnt('region_name',region_name,'district_name',district_name)
            if region_name:
                AbbrName = None
                if region_name in province_list:
                    AbbrName = province_list[region_name]
                if region_name in prov_or_terr:
                    region_type = prov_or_terr[region_name]
                else:
                    region_type = 'Province'
                prov = Region.objects.filter(Name=region_name, AbbrName=AbbrName, nameType=region_type, ParentRegion_obj=country, Validator_obj__is_valid=True).first()
                if not prov:
                    prov = Region(func=func, Name=region_name, AbbrName=AbbrName, nameType=region_type, ParentRegion_obj=country)
                    prov.save()
                    log.updateShare(prov)

                if district_name:
                    district = District.objects.filter(Name=district_name, Country_obj=country, Region_obj=country, ProvState_obj=prov, gov_level='Federal', nameType='Federal District', Validator_obj__is_valid=True).first()
                    if district:
                        if not district.Office_array or 'Senator' not in district.Office_array:
                            modded_district = district.propose_modification()
                            modded_district.add_office('Senator')
                            log.updateShare(modded_district)
                    else:
                        district = District(func=func, Name=district_name, Country_obj=country, Region_obj=country, ProvState_obj=prov, gov_level='Federal', nameType='Federal District')
                        
                        district.add_office('Senator')
                        log.updateShare(district)

            person, personU, person_is_new = get_model_and_update('Person', GovProfilePage=govPage, Country_obj=log.Region_obj, Region_obj=log.Region_obj)
            prnt('person2:',person)
            order_num += 1
            personU.data['FirstName'] = first_name
            personU.data['LastName'] = last_name
            personU.data['PhotoLink'] = src
            personU.data['Chamber'] = chamber
            personU.data['ProvState_id'] = prov.id if prov else prov
            personU.data['Position'] = 'Senator'
            personU.data['gov_level'] = 'Federal'
            personU.data['Party_id'] = party.id if party else party
            person.update_role(personU, data={'role':'Senator','gov_level':'Federal','current':True})
            
            updated_senators.append({'link':govPage,'order_num':order_num,'data':{'person':person,'personU':personU,'person_is_new':person_is_new}})

    prntDebug('--current senators--')
    current_senators = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, extra__roles__contains=[{'role':'Senator','current':True, 'gov_level':'Federal'}])
    for update in current_senators:
        if not any(i for i in updated_senators if i['data']['person'].id == update.pointerId):
            prnt('upd',update)
            if 'Position' in update.data and update.data['Position'] == 'Senator':
                del update.data['Position']
            update.Pointer_obj.update_role(personU, data={'role':'Senator','gov_level':'Federal','current':False})
            update.save_if_new()
            log.updateShare(update)

    prnt('--updated senators:--')
    for i in updated_senators:
        person = i['data']['person']
        personU = i['data']['personU']
        person_is_new = i['data']['person_is_new']
        prntDebug('link',i['link'])
        if person_is_new or not person.GovIden:
            try:
                time.sleep(1)
                driver.get(i['link'])
                prntDebug('retreived')
                element_present = EC.presence_of_element_located((By.ID, 'senatorbiography'))
                WebDriverWait(driver, 20).until(element_present)
                time.sleep(2)
                items = driver.find_elements(By.CLASS_NAME, 'sc-senator-bio-senatorheader-content-card-list-item')
                for item in items:
                    if 'Personal Website' in item.text:
                        personU.data['Website'] = item.text.replace('Personal Website: ', '')
                    elif 'Email' in item.text:
                        personU.data['Email'] = item.text.replace('Email: ', '').replace('Electronic card', '').replace('&nbsp;', '')
                        links = item.find_elements(By.CSS_SELECTOR, 'a')
                        for l in links:
                            if 'vcard/senator' in l.get_attribute('href'):
                                href = l.get_attribute('href')
                                print('vcard', href)
                                a = href.find('/senator/en/')+len('/senator/en/')
                                iden = href[a:]
                                prntDebug('idn',iden)
                                person.GovIden = iden
                    elif 'Telephone' in item.text:
                        personU.data['Telephone'] = item.text.replace('Telephone: ', '')
                    elif 'Follow' in item.text:
                        links = item.find_elements(By.CSS_SELECTOR, 'a')
                        for l in links:
                            if 'twitter' in l.get_attribute('href'):
                                personU.data['XTwitter'] = l.get_attribute('href')
                prnt('personU.data',personU.data)
                bio = driver.find_element(By.ID, 'senatorbiography').text
                personU.extra['Bio'] = bio
            except Exception as e:
                prntDebug('fail get senator details', str(e))
                time.sleep(2)
            
        if person.GovIden:
            person, personU, person_is_new, log = save_and_return(person, personU, log)
            
            if personU.data['PhotoLink'] and not ImageFile.objects.filter(pointerId=person.id, Validator_obj__is_valid=True).exists():
                img_url = personU.data['PhotoLink']
                try:
                    img_obj = save_image(img_url, f'legis/canada/', pointerId=person.id, region=country)
                    log.updateShare(img_obj)
                except Exception as e:
                    prnt('img err122',str(e))
        prntDebug('saved')
        time.sleep(2)
    try:
        driver.quit()
    except:
        pass
    return finishScript(log, gov, special)

def get_house_agendas(url='https://www.ourcommons.ca/en/parliamentary-business/', special=None, dt=None, iden=None):
    func = 'get_house_agendas'
    prnt(f'--{func} Canada', now_utc())
    dt = declare_var(dt, now_utc())
    gov = None
    country = get_region('Canada')
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    if special != 'testing':
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')

    date_time = None
    dt_now = now_utc()
    today = dt_now - datetime.timedelta(hours=dt_now.hour, minutes=dt_now.minute, seconds=dt_now.second, microseconds=dt_now.microsecond)
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html.parser')
    try:
        session = soup.find('span', {'class':'session-subtitle'})
        prntDebug('session',session)
        '(44th Parliament, 1st Session)'
        t = session.text.replace('(', '').replace(')','')
        a = t.find(' Parliament, ')
        b = t.find(' Session')
        parl = t[:a].replace('st', '').replace('nd', '').replace('rd', '').replace('th', '')
        sess = t[a+len(' Parliament, '):b].replace('st', '').replace('nd', '').replace('rd', '').replace('th', '')
        today = soup.find('span', {'class':'session-title'}).text
        # prntDebug(today)
        # 'Sunday, June 25, 2023'
        d = today.rfind(',')
        e = today[d-2:d]
        if e[0] == ' ':
            e = '0' + e[1]
            today = today[:d-1] + e + today[d:]
        dt = datetime.datetime.strptime(today, '%A, %B %d, %Y')
        prntDebug('dt',dt)
        gov = get_gov(country, Country_obj=country, gov_level='Federal', gov_type='Parliament', GovernmentNumber=int(parl), SessionNumber=int(sess), Region_obj=country)
        prnt('gov',gov)
        if not gov.StartDate:
            from utils.models import round_time
            gov.StartDate = timezonify('est', round_time(dt=now_utc(), dir='down', amount='day'))
            gov.migrate_data()
            gov.LogoLinks = gov_logo_links
        gov = modify_gov(gov, [{'Office_array':'Member of Parliament'},{'Chamber_array':'House'},{'menuItem_array':['Bills','Debates','Motions','Officials']}])
        log.updateShare(gov)
    except Exception as e:
        prntDebug('err 5475',str(e))
        dt = today
        gov = Government.objects.filter(Region_obj=country, Country_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
        if not gov:
            url = 'https://www.parl.ca/LegisInfo/en/overview/xml/recentlyintroduced'
            r = requests.get(url, verify=False)
            root = ET.fromstring(r.content)
            bills = root.findall('Bill')
            for b in bills:
                ShortTitle = b.find('ShortTitle').text
                prntDebug('ShortTitle',ShortTitle)
                parl = b.find('ParliamentNumber').text
                sess = b.find('SessionNumber').text
                if parl:
                    break
            gov = get_gov(country, Country_obj=country, gov_level='Federal', gov_type='Parliament', GovernmentNumber=int(parl), SessionNumber=int(sess), Region_obj=country)
            prnt('gov',gov)
            if not gov.StartDate:
                from utils.models import round_time
                gov.StartDate = timezonify('est', round_time(dt=now_utc(), dir='down', amount='day'))
                gov.migrate_data()
                gov.LogoLinks = gov_logo_links
            gov = modify_gov(gov, [{'Office_array':'Member of Parliament'},{'Chamber_array':'House'},{'menuItem_array':['Bills','Debates','Motions','Officials']}])
            log.updateShare(gov)
            
        elif not gov.Validator_obj or not gov.Validator_obj.is_valid:
            log.updateShare(gov)

    try:
        section = soup.find('section', {'class':'block-in-the-chamber'})
        watch = section.find('div', {'class':'watch-previous'})
        watch_link = watch.find('a')['href']
    except Exception as e:
        prnt('agenda fail 453',str(e))
        return finishScript(log, gov, special)

    try:
        status = soup.find('p', {'class':'chamber-status'})
        prntDebug('status:',status.text.replace('.','').replace('\r','').replace('\n','').strip())
        # 'The House is adjourned until Monday, December 5, 2022 at 11:00 a.m. (EST).'
        # time data 'The House is adjourned until Monday, January 27, 2025' does not match format 'The House is adjourned until %A, %B %d, %Y at %H:%M %p (EDT)'
        if 'a.m.' in status.text or 'p.m.' in status.text:
            if '(EST)' in status.text:
                date_time = datetime.datetime.strptime(status.text.replace('.','').replace('\r','').replace('\n','').strip(), 'The House is adjourned until %A, %B %d, %Y at %H:%M %p (EST)')
            elif '(EDT)' in status.text:
                date_time = datetime.datetime.strptime(status.text.replace('.','').replace('\r','').replace('\n','').strip(), 'The House is adjourned until %A, %B %d, %Y at %H:%M %p (EDT)')
            else:
                date_time = datetime.datetime.strptime(status.text.replace('.','').replace('\r','').replace('\n','').strip(), 'The House is adjourned until %A, %B %d, %Y at %H:%M %p')
        else:
            if '(EST)' in status.text:
                date_time = datetime.datetime.strptime(status.text.replace('.','').replace('\r','').replace('\n','').strip(), 'The House is adjourned until %A, %B %d, %Y (EST)')
            elif '(EDT)' in status.text:
                date_time = datetime.datetime.strptime(status.text.replace('.','').replace('\r','').replace('\n','').strip(), 'The House is adjourned until %A, %B %d, %Y (EDT)')
            else:
                date_time = datetime.datetime.strptime(status.text.replace('.','').replace('\r','').replace('\n','').strip(), 'The House is adjourned until %A, %B %d, %Y')

    except Exception as e:
        prntDebug('err 4324',str(e))
    try:
        widget = section.find('div', {'class':'agenda-widget-content-wrapper'})
        if widget:
            date = widget.find('div').text.strip()
            prntDebug('date',date)
            'Agenda for Monday, November 28, 2022'
            date_time = datetime.datetime.strptime(date, 'Agenda for %A, %B %d, %Y')
    except Exception as e:
        prntDebug('err 875',str(e))
    if not date_time:
        return finishScript(log, gov, special)
    date_time = timezonify('est', date_time.replace(tzinfo=pytz.UTC))

    def get_video_code():
        r = requests.get('http:' + watch_link, verify=False)
        soup = BeautifulSoup(r.content, 'html.parser')
        iden = str(soup).find('contentEntityId')+len('contentEntityId')
        a = str(soup)[iden:].find(' = ')+len(' = ')
        b = str(soup)[iden+a:].find(';')
        special = str(soup)[iden+a:iden+a+b]
        return int(special)
    prntDebug('date_time',date_time)
    agenda = Agenda.objects.filter(DateTime__gte=date_time, DateTime__lt=date_time + datetime.timedelta(days=1), Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country, Validator_obj__is_valid=True).first()
    if agenda:
        agenda, agendaU, agenda_is_new = get_model_and_update('Agenda', obj=agenda)
    else:
        agenda, agendaU, agenda_is_new = get_model_and_update('Agenda', DateTime=date_time, Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country)
        agenda, agendaU, agenda_is_new, log = save_and_return(agenda, agendaU, log)
    prntDebug('agenda',agenda)
    if not 'VideoURL' in agendaU.data or agendaU.data['VideoURL'] != watch_link:
        agendaU.data['VideoURL'] = get_video_code()
    try:
        if 'adjourned' in status.text:
            # time data 'The House is adjourned until Monday, January 27, 2025' does not match format 'The House is adjourned until %A, %B %d, %Y at %I:%M %p (%Z)'
            if 'a.m.' in status.text or 'p.m.' in status.text:
                nextDt = datetime.datetime.strptime(status.text.strip().replace('.', ''), 'The House is adjourned until %A, %B %d, %Y at %I:%M %p (%Z)')
            else:
                nextDt = datetime.datetime.strptime(status.text.strip().replace('.', ''), 'The House is adjourned until %A, %B %d, %Y')
            nextDt = timezonify('est', nextDt.replace(tzinfo=pytz.UTC))
            agendaU.data['NextDateTime'] = dt_to_string(nextDt)
        agendaU.data['CurrentStatus'] = status.text.strip()
    except Exception as e:
        prntDebug('err 6539',str(e))
        agendaU.data['CurrentStatus'] = 'Adjourned'
        prnt('Adjourned')
    if widget:
        agenda_html = widget.find('div', {'class':'agenda-items'})
        divs = agenda_html.find_all('div', {'class':'row'})
        position = 0
        start_time = None
        agendaTime = None
        if not agenda.data:
            agenda.data = {}
        for div in divs:
            position += 1
            try:
                hour = div.find('span', {'class':'the-time'}).text.strip()
                item_time = datetime.datetime.strptime(date + ' / ' + hour.replace('.',''), 'Agenda for %A, %B %d, %Y / %I:%M %p')
                item_time = timezonify('est', item_time.replace(tzinfo=pytz.UTC))
                prntDebug('item_time',item_time)
                if not start_time:
                    start_time = item_time
                    agenda.DateTime = item_time
                agendaTime = dt_to_string(item_time)
            except Exception as e:
                prntDebug('err 9769', str(e))
            agenda.data[position] = {'dt':agendaTime}
            try:
                title = div.find('div', {'class':'agenda-item-title'}).text.strip()
                prntDebug('title,title')
                agenda.data[position]['text'] = title
                if ' ╼ ' in title:
                    a = title.find(' ╼ ')
                    bill = Bill.objects.filter(NumberCode=title[:a], Government_obj=gov, Country_obj=country, Region_obj=country, Validator_obj__is_valid=True).first()
                    if bill:
                        if not agenda.bill_dict:
                            agenda.bill_dict = {}
                        agenda.bill_dict[bill.NumberCode] = bill.id
            except Exception as e:
                prntDebug('err 9214',str(e))
    agenda, agendaU, agenda_is_new, log = save_and_return(agenda, agendaU, log)
    return finishScript(log, gov, special)


def get_bills(special=None, dt=None, iden=None, period='session', target_links=None, target_dt=None, job_dt=None, task=None, as_rq=True):
    func = 'get_bills'
    prnt(f'--{func} Canada', now_utc())
    dt = declare_var(dt, now_utc())
    task = declare_var(task, 1)
    prnt('-get bills', 'period',period, 'target_dt',target_dt, 'job_dt',job_dt, 'as_rq',as_rq)
    country = get_region('Canada')
    if not job_dt:
        job_dt = dt
    log = create_share_object(func, country, special=special, dt=dt, iden=iden, job_dt=job_dt, task=task)
    gov = get_gov(country)
    log = add_gov_menu_item(gov, 'Bills', log)
    if not special:
        logEvent('scrapeAssignment', region=country, func=func, log_type='Tasks')

    if target_links:
        for link in target_links:
            if link:
                try:
                    r = requests.get(link)
                    root = ET.fromstring(r.content)
                    bills = root.findall('Bill')
                    for bill in bills:
                        try:
                            log = add_bill(bill, func, special=special, country=country, log=log, iden=None)
                        except Exception as e:
                            prnt('get_bill err 231', str(e))
                            prnt('bill:',str(bill)[:500])
                    if link != target_links[-1]:
                        time.sleep(2)
                except Exception as e:
                    prnt('get_bill err 494', str(e))
                    prnt('link',link)
                    time.sleep(1)

    else:
        if period == 'alltime':
            url = 'https://www.parl.ca/LegisInfo/en/bills/xml?parlsession=all'
        elif period == 'recent':
            url = 'https://www.parl.ca/LegisInfo/en/overview/xml/recentlyintroduced'
        elif period == 'session':
            url = 'https://www.parl.ca/LegisInfo/en/bills/xml'
        else:
            # this result lacks detail
            dt = now_utc() - datetime.timedelta(days=10)
            dt_str = dt.strftime("%Y-%m-%d")
            url = f'https://www.parl.ca/LegisInfo/en/bills/xml?advancedview=true&fromdate={dt_str}&sortby=latestactivity-desc'
    

        r = requests.get(url)
        root = ET.fromstring(r.content)
        bills = root.findall('Bill')

        myObjs = root.findall('objs')

        links = []
        pub_dt = None
        latest_update = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Bill), Region_obj=country).order_by('-DateTime').values('id','DateTime').first()
        if latest_update:
            pub_dt = string_to_dt(latest_update['DateTime'])
            prnt('latest_update',latest_update['id'],'pub_dt',pub_dt)
        for b in bills:
            prnt('b:',b)
            i_pub_dt = None
            ShortTitle = b.find('LongTitleEn').text
            code = b.find('NumberCode').text
            parl = b.find('ParliamentNumber').text
            sess = b.find('SessionNumber').text
            if b.find('LatestBillEventDateTime') is not None:
                pubDate = b.find('LatestBillEventDateTime').text
                # i_pub_dt = string_to_dt(pubDate)
                i_pub_dt = timezonify('est', string_to_dt(pubDate))
            elif b.find('LatestActivityDateTime') is not None:
                pubDate = b.find('LatestActivityDateTime').text
                # i_pub_dt = string_to_dt(pubDate)
                i_pub_dt = timezonify('est', string_to_dt(pubDate))
            prnt('i_pub_dt',i_pub_dt)
            if not i_pub_dt or not pub_dt or i_pub_dt > pub_dt:
                xml = 'https://www.parl.ca/LegisInfo/en/bill/%s-%s/%s/xml' %(parl, sess, code)
                links.append(xml)
        if not pub_dt:
            pub_dt = now_utc()

        prnt('--links len:',len(links))
        max_links = 25
        while len(links) > 0:
            target_links = links[:max_links]
            prnt('target_links',target_links)
            task += 1
            if as_rq:
                queue = django_rq.get_queue('low')
                queue.enqueue(get_bills, special=special, target_links=target_links, target_dt=pub_dt, job_dt=job_dt, task=task, job_timeout=runTimes[func], result_ttl=7200)
            else:
                get_bills(special=special, dt=now_utc(), target_links=target_links, target_dt=pub_dt, job_dt=job_dt, task=task, as_rq=False)
            if len(links) > max_links:
                links = links[max_links:]
            else:
                links = []

        prntDebug('done get_bills')
        return finishScript(log, gov, special)

def add_bill(b, func, special=None, country=None, iden=None, log=None):
    prnt(f'--add_bill Canada', func, now_utc())
    dt_now = now_utc()
    today = dt_now - datetime.timedelta(hours=dt_now.hour, minutes=dt_now.minute, seconds=dt_now.second, microseconds=dt_now.microsecond)
    if not country:
        country = get_region('Canada')
    if not log:
        log = create_share_object(func, country, special=special, dt=now_utc(), iden=iden)

    ParliamentNumber = b.find('ParliamentNumber').text
    SessionNumber = b.find('SessionNumber').text
    
    gov = get_gov(country, Country_obj=country, gov_level='Federal', gov_type='Parliament', GovernmentNumber=int(ParliamentNumber), SessionNumber=int(SessionNumber), Region_obj=country)
    prnt('gov',gov)
    if not gov.StartDate:
        from utils.models import round_time
        gov.StartDate = timezonify('est', round_time(dt=now_utc(), dir='down', amount='day'))
        gov.migrate_data()
        gov.LogoLinks = gov_logo_links
    gov = modify_gov(gov, [{'Office_array':'Member of Parliament'},{'Chamber_array':'House'},{'menuItem_array':['Bills','Debates','Motions','Officials']}])
    log = add_gov_menu_item(gov, 'Bills', log)
    log.updateShare(gov)
    prntDebug('gov',gov)
    gov_iden = b.find('Id').text
    
    # <Id>13088301</Id>
    # <NumberCode>C-424</NumberCode>
    # <NumberPrefix>C</NumberPrefix>
    # <Number>424</Number>
    originChamber = b.find('OriginatingChamberName').text
    if originChamber == 'House of Commons':
        originChamber = 'House'
    prnt('originChamber',originChamber)
    numCode = b.find('NumberCode').text
    bill, billU, bill_is_new = get_model_and_update('Bill', Government_obj=gov, Country_obj=country, Region_obj=country, Chamber=originChamber, NumberCode=numCode, GovIden=gov_iden)

    prntDebug('got bill, bill_is_new:', bill_is_new)
    url = 'https://www.parl.ca/LegisInfo/en/bill/%s-%s/%s' %(b.find('ParliamentNumber').text, b.find('SessionNumber').text, b.find('NumberCode').text)
    prnt('url',url)
    if bill_is_new:
        from utils.models import round_time
        bill.DateTime = round_time(dt=now_utc())
        bill.LegisLink = url
        bill.NumberPrefix = b.find('NumberPrefix').text
        bill.Number = b.find('Number').text
        prntDebug('bill created')
        bill.Number = b.find('Number').text
        if re.search('[a-zA-Z]', b.find('ShortTitle').text):
            bill.ShortTitle = b.find('ShortTitle').text
        bill.Title = b.find('LongTitleEn').text
        bill.BillDocumentTypeName = b.find('BillDocumentTypeName').text
        bill.IsGovernmentBill = b.find('IsGovernmentBill').text
        prntDebug('bill.Chamber',bill.Chamber)
        if b.find('OriginatingChamberOrganizationId').text == '2':  #senate
            prntDebug('senate')
            person_govId = b.find('SponsorSenateSystemAffiliationId').text
        else:
            prntDebug('house')
            person_govId = b.find('SponsorPersonId').text
        person = Person.objects.filter(Region_obj=country, GovIden=person_govId, Validator_obj__is_valid=True).first()
        if not person:
            first_name = b.find('SponsorPersonOfficialFirstName').text
            last_name = b.find('SponsorPersonOfficialLastName').text
            full_name = f'{first_name} {last_name}'
            
            person, personU, person_is_new = get_model_and_update('Person', GovIden=person_govId, Country_obj=log.Region_obj, Region_obj=log.Region_obj)
            if person_is_new:
                personU.data['FirstName'] = first_name
                personU.data['LastName'] = last_name
                personU.data['FullName'] = full_name
                person, personU, person_is_new, log = save_and_return(person, personU, log)
        
        bill.Party_obj = Party.objects.filter(id=person.get_field('Party_id'), gov_level='Federal', Region_obj=country, Validator_obj__is_valid=True).first()
        bill.District_obj = District.objects.filter(id=person.get_field('District_id'), gov_level='Federal', Region_obj=country, Validator_obj__is_valid=True).first()
        bill.Person_obj = person
        bill.SponsorPersonName = b.find('SponsorPersonName').text
        bill.SponsorCode = person_govId
        bill.save()

    err = 2
    if 'billVersions' not in billU.data or not billU.data['billVersions']:
        versions = []
        def versionizer(version, completed_dt):
            try:
                completed_dt = dt_to_string(timezonify('est', parse(completed_dt)))
            except Exception as e:
                prnt('parse bill dt fail 2568', str(e), completed_dt)
            return {'version':version, 'current':None, 'status':None, 'started_dt':None, 'completed_dt':completed_dt}
        if originChamber == 'Senate':
            versions = [versionizer('Senate 1/3', b.find('PassedSenateFirstReadingDateTime').text), versionizer('Senate 2/3', b.find('PassedSenateSecondReadingDateTime').text), versionizer('Senate 3/3', b.find('PassedSenateThirdReadingDateTime').text), 
                        versionizer('House 1/3', b.find('PassedHouseFirstReadingDateTime').text), versionizer('House 2/3', b.find('PassedHouseSecondReadingDateTime').text), versionizer('House 3/3', b.find('PassedHouseThirdReadingDateTime').text), 
                        versionizer('Royal Assent', b.find('ReceivedRoyalAssentDateTime').text)]
            billU.data['Status'] = 'Senate 1/3'

        elif originChamber == 'House':
            versions = [versionizer('House 1/3', b.find('PassedHouseFirstReadingDateTime').text), versionizer('House 2/3', b.find('PassedHouseSecondReadingDateTime').text), versionizer('House 3/3', b.find('PassedHouseThirdReadingDateTime').text), 
                        versionizer('Senate 1/3', b.find('PassedSenateFirstReadingDateTime').text), versionizer('Senate 2/3', b.find('PassedSenateSecondReadingDateTime').text), versionizer('Senate 3/3', b.find('PassedSenateThirdReadingDateTime').text), 
                        versionizer('Royal Assent', b.find('ReceivedRoyalAssentDateTime').text)]
            billU.data['Status'] = 'House 1/3'
        billU.data['billVersions'] = versions
    billU.data['data_link'] = url + '/xml'

    prntDebug('0000')
    if 'Status' not in billU.data or billU.data['Status'] != b.find('StatusNameEn').text:
        updatedStatus = True
    else:
        updatedStatus = False
    date_time = None
    if b.find('LatestBillEventDateTime').text:
        date_time = datetime.datetime.strptime(b.find('LatestBillEventDateTime').text[:b.find('LatestBillEventDateTime').text.find('.')], '%Y-%m-%dT%H:%M:%S')
        date_time = timezonify('est', date_time)
        billU.data['LatestBillEventDateTime'] = dt_to_string(date_time)
        billU.DateTime = date_time
        if billU.DateTime < bill.DateTime:
            bill.DateTime = billU.DateTime
        prntDebug('Latest Time: %s' %(billU.data['LatestBillEventDateTime']))

    stage_dts = {'House 1/3':b.find('PassedHouseFirstReadingDateTime').text,
    'House 2/3':b.find('PassedHouseSecondReadingDateTime').text,
    'House 3/3':b.find('PassedHouseThirdReadingDateTime').text,
    'Senate 1/3':b.find('PassedSenateFirstReadingDateTime').text,
    'Senate 2/3':b.find('PassedSenateSecondReadingDateTime').text,
    'Senate 3/3':b.find('PassedSenateThirdReadingDateTime').text,
    'Royal Assent':b.find('ReceivedRoyalAssentDateTime').text,
    }
    prnt('updatedStatus',updatedStatus)
    if updatedStatus:
        billU.data['Status'] = b.find('StatusNameEn').text
        billU.data['LatestCompletedBillStageNameWithChamberSuffix'] = b.find('LatestCompletedMajorStageNameWithChamberSuffix').text
        billU.data['LatestCompletedBillStageName'] = b.find('LatestCompletedBillStageName').text
        billU.data['LatestCompletedBillStageChamberName'] = b.find('LatestCompletedBillStageChamberName').text
        billU.data['LatestCompletedBillStageDateTime'] = b.find('LatestCompletedBillStageDateTime').text
        billU.data['LatestBillEventChamberName'] = b.find('LatestBillEventChamberName').text
        billU.data['LatestBillEventNumberOfAmendments'] = b.find('LatestBillEventNumberOfAmendments').text
        if not date_time:
            date_time = datetime.datetime.strptime(b.find('LatestCompletedBillStageDateTime').text[:b.find('LatestCompletedBillStageDateTime').text.find('.')], '%Y-%m-%dT%H:%M:%S')
            date_time = timezonify('est', date_time)
            billU.data['LatestBillEventDateTime'] = dt_to_string(date_time)
            billU.DateTime = date_time

        prev_stage = b.find('LatestCompletedBillStageName').text
        current_stage_official = b.find('OngoingStageNameEn').text
        current_stage = current_stage_official
        current_chamber = billU.data['LatestCompletedBillStageChamberName']
        if 'House' in current_chamber:
            current_chamber = 'House'
        for i in stage_dts:
            if current_chamber in i:
                if 'First' in current_stage_official and '1/3' in i:
                    current_stage = i
                elif 'Second' in current_stage_official and '2/3' in i:
                    current_stage = i
                elif 'Third' in current_stage_official and '3/3' in i:
                    current_stage = i
            elif 'Royal' in current_stage_official and 'Royal' in i:
                current_stage = i
        prnt('current_stage',current_stage,'current_chamber',current_chamber,'prev_stage',prev_stage)
        passed_stage = False
        if current_stage in [i['version'] for i in billU.data['billVersions']]:
            passed_stage = True
        exists = False
        for v in billU.data['billVersions']:
            prnt('version',v['version'])
            exists = False
            if not v['completed_dt'] and v['version'] in stage_dts and stage_dts[v['version']]:
                prnt('a')
                try:
                    v['completed_dt'] = dt_to_string(timezonify('est', parse(stage_dts[v['version']])))
                except Exception as e:
                    prnt('parse bill dt fail 8632', str(e))
            if v['version'] == current_stage:
                prnt('b')
                passed_stage = False
                exists = True
                v['current'] = True
                v['status'] = 'current'
                if not v['started_dt']:
                    v['started_dt'] = dt_to_string(date_time)
            elif v['current'] == True or v['version'] == prev_stage or passed_stage:
                prnt('c')
                v['current'] = False
                v['status'] = 'passed'
                if not v['completed_dt']:
                    prev_dt = datetime.datetime.strptime(b.find('LatestCompletedBillStageDateTime').text[:b.find('LatestCompletedBillStageDateTime').text.find('.')], '%Y-%m-%dT%H:%M:%S')
                    prev_dt = timezonify('est', prev_dt)
                    v['completed_dt'] = dt_to_string(prev_dt)
            elif v['completed_dt'] and not v['status']:
                prnt('d')
                v['current'] = False
                v['status'] = 'passed'
            else:
                prnt('3')

        if not exists and not any(v['version'] == current_stage for v in billU.data['billVersions']):
            prnt('not exists')
            inserted = False
            versionHistory = billU.data['billVersions']
            billU.data['billVersions'] = []
            for v in versionHistory:
                if v['status'] == 'passed':
                    billU.data['billVersions'].append(v)
                else:
                    if not inserted:
                        billU.data['billVersions'].append({'version':current_stage, 'current':True, 'status':'current', 'started_dt':dt_to_string(date_time), 'completed_dt':None})
                        inserted = True
                    billU.data['billVersions'].append(v)

    def convert_reading_time(item):
        prntDebug('convert')
        try:
            prntDebug(b.find(item).text)
            return datetime.datetime.fromisoformat(b.find(item).text).astimezone(pytz.utc) 
        except:
            return None
    
    bill, billU, bill_is_new, log = save_and_return(bill, billU, log)
    def currentize_version(billData, version, dt, log):
        dt = datetime.datetime.fromisoformat(dt)
        prntDebug('currentize_version:', version)
        for v in billData['billVersions']:
            if v['version'] == version:
                v['status'] = 'Current'
                v['current'] = True
                v['started_dt'] = dt_to_string(today)
                billV, billVU, billVData, billV_is_new = get_model_and_update('BillVersion', Bill_obj=bill, Version=version, NumberCode=numCode, Government_obj=gov, Country_obj=country, Region_obj=country, Chamber=origin)

                if not billV.DateTime:
                    billV.DateTime = dt
                billV, billVU, billVData, billV_is_new, log = save_and_return(billV, billVU, billVData, billV_is_new, log, func)
            elif 'status' in v and v['status'] == 'current':
                v['status'] = 'Passed'
                v['current'] = False
                v['completed_dt'] = dt_to_string(today)
        return billData, log
        
    def get_text(billU, reading):
        prntDebug('getting text...', reading)
        url = 'https://www.parl.ca/DocumentViewer/en/%s-%s/bill/%s/%s' %(gov.GovernmentNumber, gov.SessionNumber, bill.NumberCode, reading)
        prntDebug(url)
        r = requests.get(url, verify=False)
        prntDebug('link received')
        soup = BeautifulSoup(r.content, 'html.parser')
        try:
            import hashlib
            def section_code(text, length=7):
                # return as 7 char unique string
                hash_object = hashlib.sha256(text.encode())
                hash_int = int(hash_object.hexdigest(), 16)
                return str(hash_int % 10**7).zfill(length)
            
            def case_insensitive_search(tag):
                return tag.name == 'h2' and re.search('summary', tag.string, re.IGNORECASE)
            try:
                sum = soup.find(case_insensitive_search)
            except:
                sum = soup.find("h2", string="SUMMARY")
            par = sum.parent
            text = str(par).replace(str(sum), '')
            def alter_rem(text, num, increase): #increase text size
                try:
                    match_list = []
                    for i in re.finditer('font-size:', str(text)):
                        match_list.insert(0,i)
                    for match in match_list:
                        q = str(text)[match.end():].find(';')
                        size = str(text)[match.end():match.end()+q]
                        if 'rem' in size:
                            x = size.replace('rem', '')
                            x = float(x)
                            if increase == 1:
                                newX = 1
                            else:
                                newX = x * increase
                            text = str(text)[:match.end()] + str(newX) + 'rem' + str(text)[match.end()+q:]
                        num += 1
                    return text
                except Exception as e:
                    # prntDebug('get_text fail',str(e))
                    return text
            text = alter_rem(text, 0, 1)
            text = text.replace('font-size:1rem;', '')
            text = text.replace('RECOMMENDATION', ' ')
            if not billU.extra:
                billU.extra = {}
            billU.data['Summary'] = text
            publication = soup.find('div', {'class':'publication-container-content'})
            sidebar = soup.find('div', {'class':'publication-container-explorer'})
            toc = soup.find('div', {'id':'TableofContent'})
            script = publication.find('script')
            final = str(publication).replace(str(sidebar), '').replace(str(toc), '').replace(str(script), '')
            finalText = alter_rem(final, 0, 1.30)
            prntDebug('next')
            toc_d = []
            for match in re.finditer('<h2', str(finalText)):
                q = str(finalText)[match.end():].find('>')
                w = str(finalText)[match.end():match.end()+q]
                e = str(finalText)[match.end()+q:].find('</h2>')
                full_section = str(finalText)[match.end()+q+1:match.end()+q+e]
                # full_section here is returning as section title
                html = str(finalText)[match.start():match.end()+q]
                string =  re.sub('<[^<]+?>', '', html)

                code = section_code(html+full_section)
                q = str(finalText)[match.end():].find('>')
                tag_full = str(finalText)[match.end():match.end()+q]
                if 'id=' not in tag_full:
                    replaced_tag = str(finalText)[:match.end()] + f' id="{code}" ' + str(finalText)[match.end():]
                    finalText = finalText.replace(tag_full, replaced_tag)
                    toc_d.append({full_section : {'code':code, 'html':replaced_tag}})
                else:
                    toc_d.append({full_section : {'code':code, 'html':tag_full}})
            from legis.models import BillText
            from utils.locked import hash_obj_id
            bt = BillText(pointerId=billU.pointerId)
            bt.text = bt.store_text(finalText)
            bt_id = hash_obj_id(bt)
            if not BillText.objects.filter(id=bt_id, Validator_obj__is_valid=True).exists():
                b = BillText.objects.filter(id=bt_id, Validator_obj__is_valid=True).defer('text').first()
                if b:
                    billText = b
                else:
                    billText = bt
                billText.data['TextNav'] = toc_d
                billText.data['url'] = url
            billU.data['has_text'] = True

            prntDebug('done get text')
            time.sleep(5)
            return billU, billText
        except Exception as e:
            prntDebug('old document type', str(e))
            time.sleep(5)
            a = soup.find("a", string="Complete Document")['href']
            section_list = []
            sections = soup.find_all('a', {'class':'DefaultTableOfContentsSectionLink'})
            sum_link = None
            for s in sections:
                if 'Summary' in s.text:
                    sum_link = s['href']
                section_list.append(s.text)
            sections = soup.find_all('a', {'class':'DefaultTableOfContentsFile Link'})
            for s in sections:
                section_list.append(s.text)
            prntDebug('section_list',section_list)
            def alter_pt(text, num):
                try:
                    match_list = []
                    for i in re.finditer('font-size:', str(text)):
                        match_list.insert(0,i)
                    for match in match_list:
                        q = str(text)[match.end():].find(';')
                        size = str(text)[match.end():match.end()+q]
                        if 'pt' in size:
                            n = size.replace('pt', '')
                            n = float(n)
                            text = str(text)[:match.end()] + ';' + str(text)[match.end()+q:]
                        num += 1
                    return text
                except Exception as e:
                    # prntDebug('alter_pt err',str(e))
                    return text
            def alter_line_height(text, num):
                try:
                    match_list = []
                    for i in re.finditer('font-size:', str(text)):
                        match_list.insert(0,i)
                    for match in match_list:
                        q = str(text)[match.end():].find(';')
                        size = str(text)[match.end():match.end()+q]
                        if 'pt' in size:
                            n = size.replace('pt', '')
                            n = float(n)
                            text = str(text)[:match.end()] + ';' + str(text)[match.end()+q:]
                        num += 1
                    return text
                except Exception as e:
                    # prntDebug('alter_line_height err',str(e))
                    return text
            if sum_link:
                try:
                    r = requests.get('https://www.parl.ca' + sum_link)
                    soup = BeautifulSoup(r.content, 'html.parser')
                    sum = soup.find("div", string="SUMMARY")
                    par = sum.parent
                    html = str(par).replace(str(sum), '')
                    html = alter_pt(html, 0)
                    html = alter_line_height(html, 0)
                    billU.data['Summary'] = html
                except Exception as e:
                    prnt('sum_link err',str(e))
                    pass
            r = requests.get('https://www.parl.ca' + a, verify=False)
            prntDebug('link received',a)
            soup = BeautifulSoup(r.content, 'html.parser')
            finalText = soup.find('div', {'class':'publication-container-content'})
            centers = soup.find_all('div',style=lambda value: value and 'text-align:Center' in value)
            toc_d = {}
            for c in centers:
                if c.text in section_list:
                    html = str(c).replace('\\"', "'")
                    toc_d[c.text] = str(c)
            billText = BillText.objects.filter(pointerId=billU.pointerId, data__TextHtml=str(finalText), Validator_obj__is_valid=True).first()
            if not billText:
                billText = BillText(pointerId=billU.pointerId)
                billText.data['TextHtml'] = str(finalText)
                billText.data['TextNav'] = toc_d
                billText.data['url'] = url
            billU.data['has_text'] = True
            prnt('done2 get text')
            time.sleep(5)
            return billU, billText
    

    bill, billU, bill_is_new, log = save_and_return(bill, billU, log)
    prntDebug('done save bill2')
    billText = None
    if 'LatestCompletedBillStageName' in billU.data and 'Second' in billU.data['LatestCompletedBillStageName']:
        text_version = 'second-reading'
        if not billU.extra or 'bill_text_version' not in billU.extra or billU.extra['bill_text_version'] != text_version:
            try:
                billU, billText = get_text(billU, 'second-reading')
            except Exception as e:
                prntDebug('get bill text fail 353',str(e))
    elif 'LatestCompletedBillStageName' in billU.data and 'Third' in billU.data['LatestCompletedBillStageName']:
        text_version = 'third-reading'
        if not billU.extra or 'bill_text_version' not in billU.extra or billU.extra['bill_text_version'] != text_version:
            try:
                billU, billText = get_text(billU, 'third-reading')
            except Exception as e:
                prntDebug('get bill text fail 3453',str(e))
    elif 'LatestCompletedBillStageName' in billU.data and 'Royal Assent' in billU.data['LatestCompletedBillStageName']:
        text_version = 'royal-assent'
        if not billU.extra or 'bill_text_version' not in billU.extra or billU.extra['bill_text_version'] != text_version:
            try:
                billU, billText = get_text(billU, 'royal-assent')
            except Exception as e:
                prntDebug('get bill text fail 2345',str(e))
    else:
        text_version = 'first-reading'
        if not billU.extra or 'bill_text_version' not in billU.extra or billU.extra['bill_text_version'] != text_version:
            try:
                billU, billText = get_text(billU, 'first-reading')
            except Exception as e:
                prntDebug('get bill text fail 5343',str(e))
    if billText: 
        do_save = False
        if billText.id == None or not billText.signed:
            do_save = True
            if date_time and 'date' not in billText.data or date_time and billText.data['date'] != dt_to_string(date_time):
                billText.data['date'] = dt_to_string(date_time)
                do_save = True
        if 'bill_text_version' not in billU.extra or billU.extra['bill_text_version'] != text_version:
            billText.data['bill_text_version'] = text_version
            if not billU.extra:
                billU.extra = {}
            billU.extra['bill_text_version'] = text_version
            do_save = True
        if do_save:
            billText.save(region=country)
            log.updateShare(billText)
        textFound = True
    if bill_is_new and bill.Person_obj:
        # prntDebug('send alerts')
        notification, notificationU, notification_is_new = get_model_and_update('Notification', Title=f'{bill.Person_obj.get_field("FullName")} has sponsored bill {bill.NumberCode}', Link=str(bill.get_absolute_url()), targetUsers={'follow_person' : bill.Person_obj.id}, pointerId=bill.id, Country_obj=country, Region_obj=country, Chamber=originChamber, networkChain=gov.id)
        notification, notificationU, notification_is_new, log = save_and_return(notification, notificationU, log)

    bill, billU, bill_is_new, log = save_and_return(bill, billU, log)
    if updatedStatus:
        if bill.Person_obj:
            person_id = bill.Person_obj.id
        else:
            person_id = bill.SponsorCode
        if billU.data['Status'] != 'Royal assent received':
            if UserData.objects.filter(Q(follow_topics__contains=bill.id)|Q(follow_topics__contains=person_id)).count() > 0:
            #     for u in User.objects.filter(follow_Bill_objs=bill):
            #         title = 'Bill %s updated' %(bill.NumberCode)
            #         u.alert(title, str(bill.get_absolute_url()), body + '\n' + billData['Status'], obj=bill, share=False)
                # notification, notificationU, notificationData, notification_is_new = get_model_and_update('Notification', title=f'Bill {bill.NumberCode} updated - {body}', link=str(bill.get_absolute_url()), targetUsers={'follow_bill' : bill.id}, pointerId=bill.id, pointerType=bill.objType, Country_obj=country, Region_obj=country, Chamber=originChamber)
                # notification, notificationU, notificationData, notification_is_new, log = save_and_return(notification, notificationU, notificationData, notification_is_new, log, func)
                notification, notificationU, notification_is_new = get_model_and_update('Notification', Title=f'Bill {bill.NumberCode} updated', Link=str(bill.get_absolute_url()), targetUsers={'follow_bill' : bill.id, 'follow_person' : person_id}, pointerId=bill.id, Country_obj=country, Region_obj=country, Chamber=bill.Chamber, networkChain=gov.id)
                notification, notificationU, notification_is_new, log = save_and_return(notification, notificationU, log)
        elif 'Royal assent received' in billU.data['Status']:
            notification, notificationU, notification_is_new = get_model_and_update('Notification', Title=f'Bill {bill.NumberCode} updated', Link=str(bill.get_absolute_url()), targetUsers={'follow_bill' : bill.id, 'follow_person' : person_id}, pointerId=bill.id, Country_obj=country, Region_obj=country, Chamber=bill.Chamber, networkChain=gov.id)
            notification, notificationU, notification_is_new, log = save_and_return(notification, notificationU, log)
    
    return log
    

def get_house_debates(special=None, dt=None, objType='hansard', value='latest', iden=None, job_dt=None, as_rq=True):
    func = 'get_house_debates'
    prnt(f'--{func} Canada', now_utc())
    dt = declare_var(dt, now_utc())
    country = get_region('Canada')

    meeting_count = 0
    meetings = Meeting.objects.filter(meeting_type='Debate', Chamber='House', DateTime__gte=now_utc() - datetime.timedelta(days=2), DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Validator_obj__is_valid=True).values('id', 'DateTime')
    if meetings:
        updates_count = Update.objects.filter(pointerId__in=[m['id'] for m in meetings], DateTime__gte=now_utc() - datetime.timedelta(days=2), DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Region_obj=country, Validator_obj__is_valid=True).exclude(data__contains='"has_transcript": true').count()
        if updates_count:
            meeting_count = updates_count

    # meeting_count = Post.objects.filter(Meeting_obj__meeting_type='Debate', Meeting_obj__Chamber='House', Meeting_obj__DateTime__gte=now_utc() - datetime.timedelta(days=2), Meeting_obj__DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Region_obj=country).exclude(Update_obj__data__contains='"has_transcript": true').count()
    prnt('meeting_count',meeting_count)
    if meeting_count <= 1:
        log = create_share_object(func, country, special=special, dt=dt, iden=iden, job_dt=job_dt)
        log, gov = get_house_hansard_or_committee(objType, value, country, log)
        prntDebug('done done')
        return finishScript(log, gov, special)

def get_house_hansard_or_committee(objType, value, country, log):
    prnt('-get_house_hansard_or_committee')
    xml = 'https://www.ourcommons.ca/PublicationSearch/en/?PubType=37&xml=1'
    is_hansard = False
    is_committee = False
    if objType == 'hansard' and value == 'latest':
        prntDebug('--housee hansard')
        is_hansard = True
        # xml = 'https://www.ourcommons.ca/PublicationSearch/en/?View=D&Item=&ParlSes=from2022-10-31to2022-10-31&oob=&Topic=&Proc=&Per=&Prov=&Cauc=&Text=&RPP=15&order=&targetLang=&SBS=0&MRR=150000&PubType=37&xml=1'
        xml = 'https://www.ourcommons.ca/PublicationSearch/en/?View=D&Item=&ParlSes=&oob=&Topic=&Proc=&Per=&Prov=&Cauc=&Text=&RPP=15&order=&targetLang=&SBS=0&MRR=150000&PubType=37&xml=1'
    elif objType == 'committee' and value == 'latest':
        # prntDebug('is committee')
        is_committee = True
        # xml = 'https://www.ourcommons.ca/PublicationSearch/en/?View=D&Item=&ParlSes=from2022-10-31to2022-10-31&oob=&Topic=&Proc=&Per=&Prov=&Cauc=&Text=&RPP=15&order=&targetLang=&SBS=0&MRR=150000&PubType=40017&xml=1'
        xml = 'https://www.ourcommons.ca/PublicationSearch/en/?View=D&Item=&ParlSes=&oob=&Topic=&Proc=&Per=&Prov=&Cauc=&Text=&RPP=15&order=&targetLang=&SBS=0&MRR=150000&PubType=40017&xml=1'
    elif objType == 'committee':
        xml = value
        # xml = 'https://www.ourcommons.ca/PublicationSearch/en/?PubType=40017&xml=1&parlses=from2023-03-01to2023-04-01'
        is_committee = True
    elif objType == 'hansard':
        xml = value
        # xml = 'https://www.ourcommons.ca/PublicationSearch/en/?View=D&Item=&ParlSes=from2002-05-02to2002-05-02&oob=&Topic=&Proc=&Per=&Prov=&Cauc=&Text=&RPP=15&order=&targetLang=&SBS=0&MRR=2000000&PubType=37&xml=1'
        is_hansard = True
    prntDebug('xml',xml)
    from utils.utils import proxy_request
    # r = proxy_request(xml, country='CA')
    r = proxy_request(xml)
    prntDebug('received')
    root = ET.fromstring(r.content)
    publications = root.find('Publications')
    pubs = publications.findall('Publication')
    for p in reversed(pubs[:2]):
        Title = p.attrib['Title']
        prntDebug('Title',Title)
        pub_iden = p.attrib['Id']
        date = p.attrib['Date']
        # '2022-10-28'
        xTime = p.attrib['Time']
        # Publication_date_time = None
        Parliament = p.attrib['Parliament']
        Session = p.attrib['Session']

        gov = get_gov(country, Country_obj=country, gov_level='Federal', gov_type='Parliament', GovernmentNumber=Parliament, SessionNumber=Session, Region_obj=country)
        prnt('gov',gov)
        if not gov.StartDate:
            from utils.models import round_time
            gov.StartDate = timezonify('est', round_time(dt=now_utc(), dir='down', amount='day'))
            gov.migrate_data()
            gov.LogoLinks = gov_logo_links
        log.updateShare(gov)
        
        if value == 'latest':
            new = False
        else:
            new = True
        if is_hansard:
            # date_A = datetime.datetime.strptime('%s' %(date), '%Y-%m-%d').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
            date_A = timezonify('est', datetime.datetime.strptime('%s' %(date), '%Y-%m-%d'))
            # date_time = datetime.datetime.strptime('%s/%s' %(date, xTime), '%Y-%m-%d/%H:%M').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
            date_time = timezonify('est', datetime.datetime.strptime('%s/%s' %(date, xTime), '%Y-%m-%d/%H:%M'))
            meeting = Meeting.objects.filter(meeting_type='Debate', DateTime__gte=date_A, DateTime__lt=date_A + datetime.timedelta(days=1), Title=Title, Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country, Validator_obj__is_valid=True).first()
            if meeting:
                meeting, meetingU, meeting_is_new = get_model_and_update('Meeting', obj=meeting)
            else:
                meeting, meetingU, meeting_is_new = get_model_and_update('Meeting', meeting_type='Debate', DateTime=date_time, Title=Title, Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country)
            
            if 'has_transcript' not in meetingU.data or meetingU.data['has_transcript'] == False:
                new = True
                meetingU.data['has_transcript'] = False
            if meeting_is_new:
                
                A = Agenda.objects.filter(DateTime__gte=date_time, DateTime__lt=date_time + datetime.timedelta(hours=12), Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country, Validator_obj__is_valid=True).first()
                if A:
                    A, Au, A_is_new = get_model_and_update('Agenda', obj=A)
                else:
                    A, Au, A_is_new = get_model_and_update('Agenda', DateTime=date_time, Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country)
                    A, Au, A_is_new, log = save_and_return(A, Au, log)
                meeting.Agenda_obj = A    
            
                prntDebug('hansard created')
            meeting.GovPage = 'https://www.ourcommons.ca/DocumentViewer/en/%s-%s/house/sitting-%s/hansard' %(Parliament, Session, meeting.Title.replace('Hansard - ',''))
        elif is_committee:
            a = Title.find(' - ')+len(' - ')
            b = Title[a:].find('-')
            code = Title[a:a+b]
            committee = Committee.objects.filter(code=code.upper(), ParliamentNumber=44, SessionNumber=1, Validator_obj__is_valid=True).first()
            if not committee:
                committee = Committee(code=code.upper(), Organization='House', Title=p.attrib['Organization'], ParliamentNumber=44, SessionNumber=1)
                committee.save()
                committee.create_post()
            try:
                date_time_start = datetime.datetime.strptime('%s' %(date), '%Y-%m-%d')
                dt_plus_one = date_time_start + datetime.timedelta(days=1)
                H = CommitteeMeeting.objects.filter(committee=committee, date_time_start__range=[datetime.datetime.strftime(date_time_start, '%Y-%m-%d'), datetime.datetime.strftime(dt_plus_one, '%Y-%m-%d')], ParliamentNumber=Parliament, SessionNumber=Session).first()
                prntDebug('committeeM found')
                # H.code = code
                if not H.Title:
                    H.Title = Title
            except:
                H = CommitteeMeeting(committee=committee, Title=Title, code=code, Organization='House', ParliamentNumber=Parliament, SessionNumber=Session)
                H.has_transcript = True
                prntDebug('committeeM created')
                new = True
        # meeting.DateTime = datetime.datetime.strptime('%s-%s' %(date, xTime), '%Y-%m-%d-%H:%M').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
        meeting.DateTime = timezonify('est', datetime.datetime.strptime('%s-%s' %(date, xTime), '%Y-%m-%d-%H:%M'))

        meeting.PublicationId = pub_iden
        meetingU.data['PdfURL'] = p.attrib['PdfURL']
        meetingU.data['IsAudioOnly'] = int(p.attrib['IsAudioOnly'])
        meetingU.data['IsTelevised'] = int(p.attrib['IsTelevised'])
        meetingU.data['TypeId'] = int(p.attrib['TypeId'])
        meetingU.data['HtmlURL'] = p.attrib['HtmlURL']
        meetingU.data['MeetingIsForSenateOrganization'] = p.attrib['MeetingIsForSenateOrganization']
        meeting, meetingU,  meeting_is_new, log = save_and_return(meeting, meetingU, log)
        items = p.findall('PublicationItems')
        if new or meetingU.data['has_transcript'] == False:
            for item in items:
                it = item.findall('PublicationItem')
                for i in it:
                    ItemId = i.attrib['Id']
                    EventId = i.attrib['EventId']
                    Date = i.attrib['Date']
                    Hour = i.attrib['Hour']
                    Minute = i.attrib['Minute']
                    Second = i.attrib['Second']
                    dt = '%s-%s:%s:%s' %(Date, Hour, Minute, Second)
                    prntDebug('item dt:',dt)
                    Item_date_time = datetime.datetime.strptime(dt, '%Y-%m-%d-%H:%M:%S').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
                    if is_hansard:
                        statement, statementU, statement_is_new = get_model_and_update('Statement', ItemId=ItemId, EventId=EventId, DateTime=Item_date_time, Meeting_obj=meeting, Chamber='House', Government_obj=gov, Country_obj=country, Region_obj=country)

                    elif is_committee:
                        try:
                            h = CommitteeItem.objects.filter(committeeMeeting=H, EventId=EventId, Item_date_time=Item_date_time).first()
                            # prntDebug('----handsard--found')
                        except:
                            h = CommitteeItem(committeeMeeting=H, ItemId=ItemId, EventId=EventId, Item_date_time=Item_date_time, meeting_title=H.Title)

                    statementU.data['VideoURL'] = i.attrib['VideoURL'] + '&vt=watch&autoplay=true'
                    try:
                        statementU.data['Page'] = i.attrib['Page']
                    except:
                        pass
                    try:
                        statement.PdfPage = i.attrib['PdfPage']
                    except:
                        pass
                    statementU.data['TypeId'] = i.attrib['TypeId']
                    statementU.data['PublicationId'] = int(p.attrib['Id'])
                    date = p.attrib['Date']
                    person = i.find('Person')
                    try:
                        Id = person.attrib['Id']
                    except: 
                        Id = None
                    try:
                        ProfileUrl = person.find('ProfileUrl').text
                    except:
                        ProfileUrl = None
                    FirstName = person.find('FirstName').text
                    LastName = person.find('LastName').text
                    try:
                        Image = person.find('Image').text
                    except:
                        Image = None

                    try:
                        if Id:
                            profile, profileU, profile_is_new = get_model_and_update('Person', GovIden=Id, Country_obj=country, Region_obj=country)

                        else:
                            profile, profileU, profile_is_new = get_model_and_update('Person', FirstName=FirstName, LastName=LastName, Country_obj=country, Region_obj=country)
                            
                            try:
                                if ProfileUrl:
                                    profileU.data['GovProfilePage'] = ProfileUrl
                                    log = get_MP(profile, profileU, profile_is_new, log, chamber='House')
                            except Exception as e:
                                prntDebug('get mp err 875', str(e))
                            prntDebug('----person--found')
                    except Exception as e:
                        prntDebug('hansard person err 3',str(e))
                        prntDebug('create person')
                        profile, profileU, profile_is_new = get_model_and_update('Person', FirstName=FirstName, LastName=LastName, Country_obj=country, Region_obj=country)
                        
                        if Id:
                            profile.GovProfilePage = ProfileUrl
                            profile.GovIden = Id
                            try:
                                log = get_MP(profile, profileU, profile_is_new, log, chamber='House')
                            except Exception as e:
                                prntDebug('get mp err 05912', str(e))
                        
                        if Image:
                            profile.PhotoLink = Image
                    profile, profileU, profile_is_new, log = save_and_return(profile, profileU, log)
                    statement.Person_obj = profile
                    statement.PersonName = profile.get_field("FullName")

                    try:
                        party = Party.objects.filter(id=profileU.data['Party_id'], Validator_obj__is_valid=True).first()
                        statement.Party_obj = party
                    except:
                        pass
                    try:
                        district = District.objects.filter(id=profileU.data['District_id'], Validator_obj__is_valid=True).first()
                        statement.District_obj = district
                    except:
                        pass
                    statement.OrderOfBusiness = i.find('OrderOfBusiness').text
                    statement.SubjectOfBusiness = i.find('SubjectOfBusiness').text
                    if statement.SubjectOfBusiness:
                        if 'subjects' in meetingU.data:
                            meetingU.data['subjects'].append(statement.SubjectOfBusiness)
                        else:
                            meetingU.data['subjects'] = [statement.SubjectOfBusiness]
                    statementU.data['EventType'] = i.find('EventType').text
                    statement.Terms_array = []
                    XmlContent = i.find('XmlContent')
                    try:
                        Intervention = XmlContent.find('Intervention')
                        try:
                            statementU.data['Type'] = Intervention.attrib['Type']
                        except:
                            pass
                        try:
                            ToCText = Intervention.attrib['ToCText']
                        except:
                            pass
                        try:
                            PersonSpeaking = Intervention.find('PersonSpeaking')
                        except:
                            pass
                        Content = Intervention.find('Content')
                        FloorLanguage = Content.find('FloorLanguage')
                        try:
                            statement.Language = FloorLanguage.attrib['language']
                        except:
                            pass

                        ParaText = Content.findall('ParaText')
                        statement.Content = ''

                        for pt in ParaText:
                            if statement.Content:
                                statement.Content += '\n'
                            statement.Content += ''.join(pt.itertext())

                        words = re.findall(r'\w+', statement.Content)
                        statement.word_count = len(words)

                        for pt in Content.findall('ParaText'):
                            for doc in pt.findall('Document'):
                                if doc and doc.text:
                                    if not statement.bill_dict:
                                        statement.bill_dict = {}
                                    statement.bill_dict[doc.text.strip()] = doc.text.strip()

                    except Exception as e:
                        prntDebug('except 642', str(e))
                        SubjectOfBusiness = XmlContent.find('SubjectOfBusiness')
                        SubjectOfBusinessContent = SubjectOfBusiness.find('SubjectOfBusinessContent')
                        FloorLanguage = SubjectOfBusinessContent.find('FloorLanguage')
                        try:
                            statement.Language = FloorLanguage.attrib['language']
                        except:
                            pass
                        WrittenQuestionResponse = SubjectOfBusinessContent.findall('WrittenQuestionResponse')
                        statement.word_count = 0
                        statementU.data['questions'] = []
                        for Quest in WrittenQuestionResponse:
                            question = {}
                            QuestionId = Quest.find('QuestionID')
                            QuestionNumber = ''.join(QuestionId.itertext())
                            question['QuestionId'] = QuestionId
                            question['QuestionNumber'] = QuestionNumber
                            try:
                                Questioner = Quest.find('Questioner')
                                QuestionerName = Questioner.find('Affiliation').text
                            except:
                                QuestionerName = None
                            if '. ' in QuestionerName:
                                a = QuestionerName.find('. ')
                            else:
                                a = 0
                            if '(' in QuestionerName:
                                b = QuestionerName[a:].find('(')
                            else:
                                b = len(QuestionerName[a:])
                            name = QuestionerName[a:a+b].split()
                            question['QuestionerName'] = '%s %s' %(name[1], name[2])
                            QuestionContent = Quest.find('QuestionContent')
                            ParaText = QuestionContent.findall('ParaText')
                            question['QuestionContent'] = ''
                            for pt in ParaText:
                                if question['QuestionContent']:
                                    question['QuestionContent'] += '\n'
                                question['QuestionContent'] += str(pt.itertext())
                            string =  re.sub('<[^<]+?>', '', question['QuestionContent'])
                            words = re.findall(r'\w+', string)
                            try:
                                statement.word_count = statement.word_count + len(words)
                            except:
                                statement.word_count = len(words)
                            response = {}
                            try:
                                Responder = Quest.find('Responder')
                                ResponderName = Responder.find('Affiliation').text
                                if '. ' in ResponderName:
                                    a = ResponderName.find('. ')
                                else:
                                    a = 0
                                if '(' in ResponderName:
                                    b = QuestionerName[a:].find('(')
                                else:
                                    b = len(ResponderName[a:])
                                name = ResponderName[a:a+b].split()
                                response['ResponderName'] = '%s %s' %(name[1], name[2])
                            except:
                                pass
                            try:
                                ResponseContent = Quest.find('ResponseContent')
                                ParaText = ResponseContent.findall('ParaText')
                                response['ResponseContent'] = ''
                                for pt in ParaText:
                                    Content = ET.tostring(pt).decode()
                                    response['ResponseContent'] = response['ResponseContent'] + '\n' + str(Content)
                                string =  re.sub('<[^<]+?>', '', response['ResponseContent'])
                                words = re.findall(r'\w+', string)
                                try:
                                    statement.word_count = statement.word_count + len(words)
                                except:
                                    statement.word_count = len(words)
                            except:
                                try:
                                    ProceduralText = SubjectOfBusinessContent.find('ProceduralText').text
                                    question['QuestionContent'] = question['QuestionContent'] + '\n' + str(ProceduralText)
                                except:
                                    pass
                            question['response'] = response
                            statementU.data['questions'].append(question)
                    try:
                        IndexEntries = i.find('IndexEntries')
                        Terms = IndexEntries.findall('Term')                        
                        s_terms = []
                        for t in Terms:
                            text = t.text
                            s_terms.append(text)
                            try:
                                x = None
                                a = text.find(', ')
                                b = text[:a]
                                bill = Bill.objects.filter(NumberCode=b, Country_obj=country, Government_obj=gov).filter(Q(Chamber='Senate')|Q(Chamber='House'), Validator_obj__is_valid=True).first()
                                if bill:
                                    bill, billU, bill_is_new = get_model_and_update('Bill', obj=bill)
                                    prntDebug('bill',bill)
                                    LatestBillEventDateTime = string_to_dt(billU.data['LatestBillEventDateTime'])
                                    if meeting.DateTime > LatestBillEventDateTime:
                                        billU.data['LatestBillEventDateTime'] = dt_to_string(meeting.DateTime)
                                        bill, billU, bill_is_new, log = save_and_return(bill, billU, log)
                                
                            except Exception as e:
                                prnt('hansard bill err 934', str(e))
                            statement = statement.add_term(text, x)

                    except Exception as e:
                        prntDebug('terms fail 062', str(e))
                        if 'findall' not in str(e):
                            raise Exception('not found findall')
                    statement, statementU, statement_is_new, log = save_and_return(statement, statementU, log)
            meetingU.data['has_transcript'] = True
            meeting, meetingU, meeting_is_new = meeting.apply_terms(meeting, meetingU, meeting_is_new)
            if is_hansard:
                last_statement = Statement.objects.filter(Meeting_obj=meeting, Validator_obj__is_valid=True).last()
                if last_statement:
                    last_updated = Update.valid_objects.filter(pointerId=last_statement.id).first()
                    if last_updated and 'VideoURL' in last_updated.data:
                        meetingU.data['VideoURL'] = last_updated.data['VideoURL']
            meetingU.data['completed_model'] = True
            meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)

    return log, gov


def get_house_motions(special=None, dt=None):
    func = 'get_house_motions'
    prnt(f'--{func} Canada', now_utc())
    dt = declare_var(dt, now_utc())
    country = get_region('Canada')
    proceed = True

    meeting = Meeting.objects.filter(meeting_type='Debate', Chamber='House', DateTime__gte=now_utc() - datetime.timedelta(days=2), DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time())).values('id', 'DateTime').first()
    if meeting:
        update = Update.objects.filter(pointerId=meeting['id'], DateTime__gte=now_utc() - datetime.timedelta(days=2), DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Region_obj=country, data__contains='"has_transcript": true').first()
        if update:
            if Motion.objects.filter(Chamber='House', Country_obj=country, Region_obj=country, DateTime__gte=meeting['DateTime'], Validator_obj__is_valid=True).exists():
                proceed = False

    # meeting = Post.objects.filter(Meeting_obj__meeting_type='Debate', Meeting_obj__Chamber='House', Meeting_obj__DateTime__gte=now_utc() - datetime.timedelta(days=2), Meeting_obj__DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Region_obj=country, Update_obj__data__contains='"has_transcript": true').first()
    # if meeting:
    #     recent_motion = Motion.objects.filter(Chamber='House', Country_obj=country, Region_obj=country, DateTime__gte=meeting.Meeting_obj.DateTime, Validator_obj__is_valid=True).first()
    #     if recent_motion:
    #         proceed = False
    if proceed:
        log = create_share_object(func, country, special=special, dt=dt, iden=None, job_dt=None)
        vote1 = 'https://www.ourcommons.ca/members/en/votes/xml'
        r = requests.get(vote1)
        root = ET.fromstring(r.content)
        motions = root.findall('Vote')
        motion_list = []
        for motion in reversed(motions[:2]):
            m, gov, log = add_house_motion(motion, country, log)
            motion_list.append(m)
            
        return finishScript(log, gov, special)
    
def add_house_motion(motion, country, log):
    func = 'add_house_motion'
    prnt(f'--{func} Canada', now_utc())
    ParliamentNumber = motion.find('ParliamentNumber').text
    SessionNumber = motion.find('SessionNumber').text
    
    gov = get_gov(country, Country_obj=country, gov_level='Federal', gov_type='Parliament', GovernmentNumber=ParliamentNumber, SessionNumber=SessionNumber, Region_obj=country)
    prnt('gov',gov)
    if not gov.StartDate:
        from utils.models import round_time
        gov.StartDate = timezonify('est', round_time(dt=now_utc(), dir='down', amount='day'))
        gov.migrate_data()
        gov.LogoLinks = gov_logo_links
    log.updateShare(gov)

    DecisionEventDateTime = motion.find('DecisionEventDateTime').text
    # date_time = datetime.datetime.strptime(motion.find('DecisionEventDateTime').text, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
    date_time = datetime.datetime.fromisoformat(DecisionEventDateTime).replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
    DecisionDivisionNumber = motion.find('DecisionDivisionNumber').text
    DecisionDivisionSubject = motion.find('DecisionDivisionSubject').text
    DecisionResultName = motion.find('DecisionResultName').text
    DecisionDivisionNumberOfYeas = motion.find('DecisionDivisionNumberOfYeas').text
    DecisionDivisionNumberOfNays = motion.find('DecisionDivisionNumberOfNays').text
    DecisionDivisionNumberOfPaired = motion.find('DecisionDivisionNumberOfPaired').text
    DecisionDivisionDocumentTypeName = motion.find('DecisionDivisionDocumentTypeName').text
    DecisionDivisionDocumentTypeId = motion.find('DecisionDivisionDocumentTypeId').text
    BillNumberCode = motion.find('BillNumberCode').text
    prntDebug('BillNumberCode', BillNumberCode)
    prntDebug('date_time', date_time)
    prntDebug('DecisionDivisionNumber',DecisionDivisionNumber)
    proceed = True
    motion, motionU, motion_is_new = get_model_and_update('Motion', VoteNumber=DecisionDivisionNumber, Country_obj=country, Government_obj=gov, Region_obj=country)
    if motion:
        proceed = False
        prntDebug('motion found')
        if motion_is_new or motion.TotalVotes == 0:
            proceed = True
    if proceed:
        time.sleep(2)
        motion.DateTime = date_time
        motion.Yeas = DecisionDivisionNumberOfYeas
        motion.Nays = DecisionDivisionNumberOfNays
        motion.Present = DecisionDivisionNumberOfPaired
        motion.DecisionType = DecisionDivisionDocumentTypeName
        motion.Result = DecisionResultName
        motion.Subject = DecisionDivisionSubject
        motion.billCode = BillNumberCode
        motion.Chamber = 'House'
        motion.is_official = True
        bill = Bill.objects.filter(NumberCode=BillNumberCode, Government_obj=gov, Country_obj=country, Region_obj=country, Validator_obj__is_valid=True).first()
        if bill:
            motion.Bill_obj = bill
            prntDebug('bill',bill)
        vote_url = 'https://www.ourcommons.ca/members/en/votes/%s/%s/%s' %(ParliamentNumber, SessionNumber, DecisionDivisionNumber)
        prntDebug('vote_url',vote_url)
        motion.GovUrl = vote_url
        r = requests.get(vote_url)
        soup = BeautifulSoup(r.content, 'html.parser')
        sponsor_link = soup.find('a', {'class':'ce-mip-mp-tile-link'})['href']
        sponsor_obj = Person.objects.filter(GovProfilePage__icontains=sponsor_link, Validator_obj__is_valid=True).first()
        sponsorPerson, sponsorPersonU, sponsorPerson_is_new = get_model_and_update('Person', obj=sponsor_obj)
        if sponsorPerson_is_new:
            sponsorPerson, sponsorPersonU, sponsorPerson_is_new, log = save_and_return(sponsorPerson, sponsorPersonU, log)
        
        if sponsorPerson:
            motion.Sponsor_obj = sponsorPerson
        text = str(soup.find('div', {'id':'mip-vote-text-collapsible-text'}))
        motion.MotionText = text
        motion, motionU, motion_is_new, log = save_and_return(motion, motionU, log)

        vote_xml = 'https://www.ourcommons.ca/members/en/votes/%s/%s/%s/xml' %(ParliamentNumber, SessionNumber, DecisionDivisionNumber)
        prntDebug('vote_xml',vote_xml)
        r = requests.get(vote_xml)
        root = ET.fromstring(r.content)
        votes = root.findall('VoteParticipant')
        vote_count = 0
        result_data = {'Parties':[], 'Votes':[], 'PartyData':{}}
        prntDebug('run votes')
        for vote in votes:
            vote_count += 1
            ParliamentNumber = vote.find('ParliamentNumber').text
            SessionNumber = vote.find('SessionNumber').text
            DecisionEventDateTime = vote.find('DecisionEventDateTime').text
            '2022-11-03T15:30:00'
            DecisionDivisionNumber = vote.find('DecisionDivisionNumber').text
            PersonShortSalutation = vote.find('PersonShortSalutation').text
            ConstituencyName = vote.find('ConstituencyName').text
            VoteValueName = vote.find('VoteValueName').text
            PersonOfficialFirstName = vote.find('PersonOfficialFirstName').text
            PersonOfficialLastName = vote.find('PersonOfficialLastName').text
            ConstituencyProvinceTerritoryName = vote.find('ConstituencyProvinceTerritoryName').text
            CaucusShortName = vote.find('CaucusShortName').text
            IsVoteYea = vote.find('IsVoteYea').text
            IsVoteNay = vote.find('IsVoteNay').text
            IsVotePaired = vote.find('IsVotePaired').text
            DecisionResultName = vote.find('DecisionResultName').text
            PersonId = vote.find('PersonId').text
            vote, voteU, vote_is_new = get_model_and_update('RepVote', Motion_obj=motion, PersonId=PersonId, Country_obj=country, Government_obj=gov, Region_obj=country)

            person, personU, person_is_new = get_model_and_update('Person', GovIden=PersonId, Country_obj=country)
            if person_is_new:
                person, personU, person_is_new, log = save_and_return(person, personU, log)
            if person:
                vote.Person_obj = person
            prntDebug('p,bill', person, bill)
            
            vote.ConstituencyName = ConstituencyName
            vote.VoteValue = VoteValueName
            vote.PersonFullName = PersonOfficialFirstName + ' ' + PersonOfficialLastName
            vote.ConstituencyProvStateName = ConstituencyProvinceTerritoryName
            vote.CaucusName = CaucusShortName
            vote.Party_obj = Party.objects.filter(Name=CaucusShortName, Region_obj=country, gov_level='Federal', Validator_obj__is_valid=True).first()
            vote.IsVoteYea = IsVoteYea
            vote.IsVoteNay = IsVoteNay
            vote.Present = IsVotePaired
            vote.DateTime = date_time
            vote, voteU, vote_is_new, log = save_and_return(vote, voteU, log)
            found = False
            for i in result_data['Votes']:
                if i['Vote'] == VoteValueName:
                    i['Count'] += 1
                    found = True
                    break
            if not found:
                result_data['Votes'].append({'Vote':VoteValueName, 'Count':1})
            found = False
            for i in result_data['Parties']:
                if i['Name'] == CaucusShortName:
                    i['Count'] += 1
                    found = True
                    break
            if not found:
                result_data['Parties'].append({'Name':CaucusShortName, 'Count':1})
        for i in result_data['Parties']:
            party = Party.objects.filter(Country_obj=country, Region_obj=country, gov_level='Federal', Validator_obj__is_valid=True).filter(Name=i['Name']).first()
            if party:
                i['short'] = party.ShortName
                i['Color'] = party.Color
                i['obj_id'] = party.id
        sorted_votes = sorted(result_data['Votes'], key=lambda item: item['Count'], reverse=True)
        result_data['Votes'] = sorted_votes
        sorted_parties = sorted(result_data['Parties'], key=lambda item: item['Count'], reverse=True)
        result_data['Parties'] = sorted_parties
        motion.result_data = result_data
        motion.TotalVotes = vote_count
        motion, motionU, motion_is_new, log = save_and_return(motion, motionU, log)
        prntDebug('done motion', vote_count)
    return motion, gov, log


    # if count >= 5:
    #     break


def get_senate_debates(special=None, dt=None, period='latest'):
    func = 'get_senate_debates'
    prnt(f'--{func} Canada', now_utc())
    dt = declare_var(dt, now_utc())
    country = get_region('Canada')
    gov = None
    meeting_count = 0
    meetings = Meeting.objects.filter(meeting_type='Debate', Chamber='Senate', DateTime__gte=now_utc() - datetime.timedelta(days=2), DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Validator_obj__is_valid=True).values('id', 'DateTime')
    if meetings:
        updates_count = Update.objects.filter(pointerId__in=[m['id'] for m in meetings], DateTime__gte=now_utc() - datetime.timedelta(days=2), DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Region_obj=country, Validator_obj__is_valid=True).exclude(data__contains='"has_transcript": true').count()
        if updates_count:
            meeting_count = updates_count
    # meeting_count = Post.objects.filter(Meeting_obj__meeting_type='Debate', Meeting_obj__Chamber='Senate', Meeting_obj__DateTime__gte=now_utc() - datetime.timedelta(days=2), Meeting_obj__DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Region_obj=country).exclude(Update_obj__data__contains='"has_transcript": true').count()
    prnt('meeting_count',meeting_count)
    if meeting_count <= 1:
        
        log = create_share_object(func, country, special=special, dt=dt, iden=None, job_dt=None)
        if period == 'latest':
            prntDebug('--senate hansards')
            debate = 'https://sencanada.ca/en/in-the-chamber/debates/'
            r = requests.get(debate)
            soup = BeautifulSoup(r.content, 'html.parser')
            links = soup.find_all('a')
            found = 0
            for a in links:
                if '\content' in a['href'] and '\debates' in a['href']:
                    link = 'https://sencanada.ca' + a['href'].replace('\\','/')
                    prnt('link',link)
                    try:
                        log, gov, is_new = add_senate_hansard(link, False, country, log)
                        if not is_new or found >= 9:
                            break
                        else:
                            found += 1
                            time.sleep(2)
                    except Exception as e:
                        prntDebug('senate hansard err 2266', str(e))
                        continue
        elif period == 'alltime':
            sessions = ['44-1', '43-2', '43-1', '42-1', '41-2', '41-1', '40-3', '40-2', '40-1', '39-2','39-1','38-1', '37-3','37-2','37-1','36-2','36-1','35-2']
            for s in sessions:
                debate = 'https://sencanada.ca/en/in-the-chamber/debates/%s' %(s)
                r = requests.get(debate)
                soup = BeautifulSoup(r.content, 'html.parser')
                links = soup.find_all('a')
                for a in reversed(links):
                    if '\content' in a['href'] and '\debates' in a['href']:
                        link = 'https://sencanada.ca' + a['href'].replace('\\','/')
                        prntDebug('link',link)
                        try:
                            log, gov, is_new = add_senate_hansard(link, False, country, log)
                            time.sleep(2)
                        except Exception as e:
                            prntDebug('senate hansard err 2267', str(e))
                            continue
        return finishScript(log, gov, special)

def add_senate_hansard(link, reprocess, country, log):
    func = 'add_senate_hansard'
    prnt(f'--{func} Canada', now_utc())
    prntDebug('link',link)
    gov = get_gov(country)

    proceed = True
    if not reprocess:

        meeting = Meeting.objects.filter(Country_obj=country, Chamber='Senate', meeting_type='Debate', GovPage=link, Validator_obj__is_valid=True).first()
        if meeting:
            meetingU = Update.valid_objects.filter(pointerId=meeting.id, validated=True, data__contains={'completed_model': True}).first()
            if meetingU:
                if 'has_transcript' in meetingU.data and meetingU.data['has_transcript'] == True:
                    proceed = False
    if proceed:
        prntDebug('adding')
        r = requests.get(link)
        soup = BeautifulSoup(r.content, 'html.parser')
        prnt('soup',soup.prettify())
        portal = soup.find('div', {'id':'portal-middle'})
        hs = portal.find_all('h2')
        for h in hs:
            nums = re.findall(r'\d+', h.text)
            Title = 'Volume %s, Issue %s' %(nums[2], nums[3])
            prntDebug('Title',Title)
            break
        content = soup.find('div', {'id':'content-viewer-document'})
        center = content.find('center')
        h3 = center.find('h3')
        dtime = center.find_next_sibling().find_next_sibling().text
        # 'The Senate met at 2 p.m., the Speaker in the chair.'
        dt = h3.text + dtime.replace('.','')
        prntDebug('dt',dt)
        try:
            date_time = timezonify('est', datetime.datetime.strptime(dt, '%A, %B %d, %YThe Senate met at %I %p, the Speaker in the chair'))
            # date_time = datetime.datetime.strptime(dt, '%A, %B %d, %YThe Senate met at %I %p, the Speaker in the chair').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
            date = date_time.replace(hour=0)
        except Exception as e:
            prntDebug('sen hansard err 73-5',str(e))
            div = soup.find('div', {'id':'portal-middle'})
            h2 = div.find_all('h2')[1]
            span = h2.find('span')
            prntDebug(h2.text.replace(span.text,''))
            # date = datetime.datetime.strptime(h2.text.replace(span.text,''), '%A, %B %d, %Y').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
            date = timezonify('est', datetime.datetime.strptime(h2.text.replace(span.text,''), '%A, %B %d, %Y'))
            date_time = date.replace(hour=14)
        prntDebug('date_time', date_time)
        
        meeting = Meeting.objects.filter(meeting_type='Debate', GovPage=link, DateTime__gte=date, DateTime__lt=date+datetime.timedelta(days=1), Chamber='Senate', Government_obj=gov, Country_obj=country, Region_obj=country, Validator_obj__is_valid=True).first()
        if meeting:
            meeting, meetingU, meeting_is_new = get_model_and_update('Meeting', obj=meeting)
        else:
            meeting, meetingU, meeting_is_new = get_model_and_update('Meeting', meeting_type='Debate', GovPage=link, DateTime=date_time, Title=Title, Chamber='Senate', Government_obj=gov, Country_obj=country, Region_obj=country)
            meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)
        
        
        def get_text(nexth1, title_text, date_time, num, log):
            prntDebug('-get text')
            try:
                while nexth1.name == "h2" or nexth1.name == "p" or nexth1.name == 'blockquote' or nexth1.name == 'center' or nexth1.name == 'div':  
                    if nexth1.name == 'h2':
                        prntDebug()
                        prntDebug('nexth1.text',nexth1.text)
                        subtext = f"{nexth1.text.strip()}"
                        next_div = nexth1.find_next_sibling()
                        statement = None
                        s_terms = []
                        senators = {}
                        blockquote = None
                        while next_div.name == "p" or next_div.name == 'blockquote':
                            try:
                                date_time = timezonify('est', datetime.datetime.strptime(date_time.strftime('%Y-%m-%d') + '-' + next_div.text, '%Y-%m-%d-(%H%M)'))
                                # date_time = datetime.datetime.strptime(date_time.strftime('%Y-%m-%d') + '-' + next_div.text, '%Y-%m-%d-(%H%M)').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
                                prntDebug('date_time',date_time)
                            except Exception as e:
                                # prntDebug(str(e))
                                person = None
                                if next_div.name == 'p':
                                    try:
                                        bold = next_div.find('b')
                                        prntDebug('bold',bold)
                                        if 'Hon' in bold.text:
                                            num += 1
                                            prnt('num',num)
                                            if statement:
                                                statement, statementU, statement_is_new, log = save_and_return(statement, statementU, log)
                                                for term in s_terms:
                                                    statement = statement.add_term(term[0], term[1])
                                                s_terms = []
                                            a = len(bold.text)
                                            if '(' in bold.text:
                                                a = bold.text.find('(')
                                            name = bold.text[:a].replace('Hon. ', '').replace(':', '').replace('The', '').replace('the','')
                                            prntDebug('name',name)
                                            if 'Speaker pro tempore' in name:
                                                name = 'Speaker pro tempore'
                                                last_name = name
                                                get_name_by = 'title'
                                            elif 'Speaker' in name:
                                                name = 'Speaker'
                                                last_name = name
                                                get_name_by = 'title'
                                            elif 'Senators' in name:
                                                name = name
                                                last_name = name
                                                get_name_by = 'None'
                                            else:
                                                name_split = name.split()
                                                prnt('name_split',name_split)
                                                first_name = name_split[0]
                                                last_name = name_split[-1]
                                                get_name_by = 'name'
                                            person = None
                                            if get_name_by == 'name':
                                                personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__FirstName__icontains=first_name, data__LastName__icontains=last_name).first()
                                                if personU:
                                                    person = personU.Pointer_obj
                                            elif get_name_by == 'title':
                                                personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__Position__icontains="Senator", data__FirstName__icontains=first_name, data__LastName__icontains=last_name, extra__roles__contains=[{'current':True,'gov_level':'Federal'}]).first()
                                                if personU:
                                                    person = personU.Pointer_obj
                                            
                                            statement, statementU, statement_is_new = get_model_and_update('Statement', new_model=True, Meeting_obj=meeting, DateTime=date_time, order=num, Chamber='Senate', Government_obj=gov, Country_obj=country, Region_obj=country)
                                            
                                            if person:
                                                statement.Person_obj = person
                                                statement.PersonName = 'Hon. %s' %(person.get_field("FullName"))
                                                prnt('statement.PersonName1,',statement.PersonName)
                                            else:
                                                statement.PersonName = name
                                                prnt('statement.PersonName2,',statement.PersonName)
                                            senators[last_name] = person
                                            if next_div.text not in statement.Content:
                                                if statement.Content:
                                                    statement.Content += '\n\n'
                                                statement.Content += str(next_div.text)
                                            string =  re.sub('<[^<]+?>', '', statement.Content)
                                            words = re.findall(r'\w+', string)
                                            statement.word_count = len(words)
                                            if subtext and subtext != '':
                                                if subtext[-4:] == 'Bill' or subtext[:7] == 'Bill to':
                                                    try:
                                                        b = subtext.replace(' Bill','').replace('Bill to ','').replace("’", "'")
                                                        bill = Bill.objects.filter(Government_obj=gov, Country_obj=country, Validator_obj__is_valid=True).filter(Q(ShortTitle__icontains=b)|Q(Title__icontains=b)).filter(Q(Chamber='Senate')|Q(Chamber='House')).first()
                                                        if bill:
                                                            prntDebug('bill',bill)
                                                            bill, billU, bill_is_new = get_model_and_update('Bill', obj=bill)
                                                            LatestBillEventDateTime = string_to_dt(billU.data['LatestBillEventDateTime'])
                                                            if meeting.DateTime > LatestBillEventDateTime:
                                                                billU.data['LatestBillEventDateTime'] = dt_to_string(meeting.DateTime)
                                                                bill, billU, bill_is_new, log = save_and_return(bill, billU, log)
                                                            s_terms.append([subtext, bill])
                                                        else:
                                                            s_terms.append([subtext, None])
                                                        
                                                    except Exception as e:
                                                        prntDebug('sen hansard bill err 79', str(e))
                                                        s_terms.append([subtext, None])

                                                else:
                                                    s_terms.append([subtext, None])
                                            statement.OrderOfBusiness = title_text
                                            if blockquote:
                                                statement.SubjectOfBusiness = blockquote
                                            else:
                                                statement.SubjectOfBusiness = subtext
                                            prnt('statement.Terms_array',statement.Terms_array)
                                            prnt('s_terms',s_terms)
                                            if not statement.Terms_array:
                                                statement.Terms_array = []
                                            if title_text and title_text != '' and title_text not in statement.Terms_array:
                                                s_terms.append([title_text, None])
                                            if subtext and subtext != '' and subtext not in statement.Terms_array:
                                                pass
                                            if blockquote and blockquote not in statement.Terms_array:
                                                s_terms.append([blockquote, None])
                                        elif 'Senator' in bold.text:
                                            prntDebug('senator',bold.text)
                                            num += 1
                                            prnt('num',num)
                                            if statement:
                                                statement, statementU, statement_is_new, log = save_and_return(statement, statementU, log)
                                                for term in s_terms:
                                                    statement = statement.add_term(term[0], term[1])
                                                s_terms = []
                                            name = bold.text.replace('Senator ', '').replace(':','').strip()
                                            prntDebug('name',name)
                                            name_split = name.split()
                                            prnt('name_split',name_split)
                                            first_name = name_split[0]
                                            last_name = name_split[-1]
                                            if last_name in senators:
                                                person = senators[last_name]
                                            else:
                                                person = None

                                            statement, statementU, statement_is_new = get_model_and_update('Statement', new_model=True, Meeting_obj=meeting, DateTime=date_time, order=num, Chamber='Senate', Government_obj=gov, Country_obj=country, Region_obj=country)
                                            if person:
                                                statement.Person_obj = person
                                                statement.PersonName = 'Hon. %s' %(person.get_field("FullName"))
                                            else:
                                                statement.PersonName = 'Senator %s' %(last_name)

                                            if next_div.text not in statement.Content:
                                                if statement.Content:
                                                    statement.Content += '\n\n'
                                                statement.Content += str(next_div.text)
                                            string =  re.sub('<[^<]+?>', '', statement.Content)
                                            words = re.findall(r'\w+', string)
                                            statement.word_count = len(words)
                                            statement.OrderOfBusiness = title_text
                                            if blockquote:
                                                statement.SubjectOfBusiness = blockquote
                                            else:
                                                statement.SubjectOfBusiness = subtext
                                            if not statement.Terms_array: 
                                                statement.Terms_array = []
                                            if title_text and title_text != '' and title_text not in statement.Terms_array:
                                                s_terms.append([title_text, None])
                                            if subtext and subtext != '' and subtext not in statement.Terms_array:
                                                s_terms.append([subtext, None])
                                            if blockquote and blockquote not in statement.Terms_array:
                                                s_terms.append([blockquote, None])
                                    except Exception as e:
                                        prntDebug('sen statement err 849', str(e))
                                        try:
                                            if statement:
                                                if next_div.text not in statement.Content:
                                                    if statement.Content:
                                                        statement.Content += '\n\n'
                                                    statement.Content += str(next_div.text)
                                                string =  re.sub('<[^<]+?>', '', statement.Content)
                                                words = re.findall(r'\w+', string)
                                                statement.word_count = len(words)
                                        except Exception as e:
                                            prntDebug('sen statement err 54',str(e))
                                            if not statement:
                                                statement, statementU, statement_is_new = get_model_and_update('Statement', new_model=True, Meeting_obj=meeting, DateTime=date_time, order=num, Chamber='Senate', Government_obj=gov, Country_obj=country, Region_obj=country)
                                                prntDebug('item created')
                                            statement.PersonName = None
                                            if next_div.text not in statement.Content:
                                                if statement.Content:
                                                    statement.Content += '\n\n'
                                                statement.Content += str(next_div.text)
                                            string =  re.sub('<[^<]+?>', '', statement.Content)
                                            words = re.findall(r'\w+', string)
                                            statement.word_count = len(words)
                                else:
                                    blockquote = next_div.text.strip()
                            next_div = next_div.find_next_sibling()
                        if statement:
                            statement, statementU, statement_is_new, log = save_and_return(statement, statementU, log)
                            for term in s_terms:
                                statement = statement.add_term(term[0], term[1])
                            s_terms = []
                            statement = None
                    nexth1 = nexth1.find_next_sibling()
            except Exception as e:
                prntDebug('statement fail 5694', str(e))
            return date_time, log, num
        precursors = h3.find_all_next('h2')
        num = 0
        for precursor in precursors:
            if not precursor.find_previous_sibling() or precursor.find_previous_sibling().name == 'h1':
                prntDebug('break')
                break
            else:
                nexth1 = precursor.find_next_sibling()
                title_text = precursor.text.strip()
                date_time, log, num = get_text(nexth1, title_text, date_time, num, log)
        h1s = content.find_all('h1')
        if h1s:
            for h1 in h1s:
                prntDebug('h1.text',h1.text, '----num', num,'date', date_time)
                nexth1 = h1.find_next_sibling()
                title_text = h1.text.strip()
                date_time, log, num = get_text(nexth1, title_text, date_time, num, log)
        else:
            h2s = content.find_all('h2')
            for h2 in h2s:
                try:
                    prntDebug('h2.text',h2.text)
                    title_text = h2.text.strip()
                    date_time, log, num = get_text(h2, title_text, date_time, num, log)
                    prntDebug('break')
                    break
                except Exception as e:
                    prntDebug('get text err 12', str(e))
        meetingU.data['has_transcript'] = True
        meeting, meetingU, meeting_is_new = meeting.apply_terms(meeting, meetingU, meeting_is_new)

        meetingU.data['completed_model'] = True
        meeting, meetingU, meeting_is_new, log = save_and_return(meeting, meetingU, log)
    return log, gov, proceed


def get_senate_motions(special=None, dt=None, time='latest'):   
    func = 'get_senate_motions' 
    prnt(f'--{func} Canada', now_utc())
    dt = declare_var(dt, now_utc())
    country = get_region('Canada')
    proceed = True
    meeting = Meeting.objects.filter(meeting_type='Debate', Chamber='Senate', DateTime__gte=now_utc() - datetime.timedelta(days=2), DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time())).values('id', 'DateTime').first()
    if meeting:
        update = Update.objects.filter(pointerId=meeting['id'], DateTime__gte=now_utc() - datetime.timedelta(days=2), DateTime__lte=datetime.datetime.combine(now_utc().date(), datetime.datetime.min.time()), Region_obj=country, data__contains='"has_transcript": true').first()
        if update:
            if Motion.objects.filter(Chamber='Senate', Country_obj=country, Region_obj=country, DateTime__gte=meeting['DateTime'], Validator_obj__is_valid=True).exists():
                proceed = False
    if proceed:
        log = create_share_object(func, country, special=special, dt=dt, iden=None, job_dt=None)
        if time == 'latest':
            url = 'https://sencanada.ca/en/in-the-chamber/votes/'
            r = requests.get(url)
            soup = BeautifulSoup(r.content, 'html.parser')
            section = soup.find('section', {'class':'votes-page'})
            tbody = section.find('tbody')
            trs = tbody.find_all('tr')
            m_num = 0
            for tr in reversed(trs):
                gov, log = add_senate_motion(tr, country, log)
                break
        elif time == 'alltime':
            sessions = ['43-2', '43-1', '42-1']
            for s in reversed(sessions):
                url = 'https://sencanada.ca/en/in-the-chamber/votes/%s' %(s)
                prntDebug('url',url)
                r = requests.get(url)
                soup = BeautifulSoup(r.content, 'html.parser')
                section = soup.find('section', {'class':'votes-page'})
                tbody = section.find('tbody')
                trs = tbody.find_all('tr')
                m_num = 0
                for tr in reversed(trs):
                    gov, log = add_senate_motion(tr, country, log)

        prnt('finish senate motions',log)
        return finishScript(log, gov, special)

def add_senate_motion(tr, country, log):
    func = 'add_senate_motion'
    prnt(f'--{func} Canada', now_utc())
    gov = get_gov(country)
    td = tr.find_all('td')
    dt = td[0]['data-order']
    date_time = datetime.datetime.strptime(dt[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern'))
    link = 'https://sencanada.ca' + td[1].find('a')['href']
    a = link.find('/details/')+len('/details/')
    b = link[a:].find('/')
    motion_iden = link[a:a+b]
    text = td[1]['data-order']
    prntDebug('text',text)
    try:
        bill_link = td[2].find('a')['href']
        prntDebug('bill_link',bill_link)
    except Exception as e:
        pass
    proceed = True
    motion, motionU, motion_is_new = get_model_and_update('Motion', GovUrl=link, Country_obj=country, Government_obj=gov, Region_obj=country)
    prntDebug('motion found',motion, motionU, motion_is_new)
    if not motion_is_new:
        if 'TotalVotes' in motionU.data:
            if motion.TotalVotes != 0:
                prnt('motion done')
                return None, log
    if proceed:
        prnt('proceed')
        try:
            billId = bill_link[bill_link.find('billId=')+len('billId='):]
            bill = Bill.objects.filter(GovIden=billId, Government_obj=gov, Country_obj=country, Region_obj=country, Validator_obj__is_valid=True).first()
        except Exception as e:
            prntDebug('err 121', str(e))
            bill = None
        prnt('bill',bill)
        motion.DateTime = date_time
        if bill:
            motion.Bill_obj = bill
            motion.billCode = bill.NumberCode
        motion.Chamber = 'Senate'
        motion.VoteNumber = motion_iden
        motion.Subject = text
        prnt('requesting',motion.GovUrl)
        r = requests.get(motion.GovUrl)
        soup = BeautifulSoup(r.content, 'html.parser')
        div = soup.find('div', {'class':'sc-vote-details-summary-table'})
        col = div.find_all('div', {'class':'sc-vote-details-summary-table-col'})
        yeas = col[0].find_all('div', {'class':'sc-vote-details-summary-table-col-cell'})[1].text
        motion.Yeas = int(yeas)
        nays = col[1].find_all('div', {'class':'sc-vote-details-summary-table-col-cell'})[1].text
        motion.Nays = int(nays)
        abs = col[2].find_all('div', {'class':'sc-vote-details-summary-table-col-cell'})[1].text
        motion.Absentations = int(abs)
        totals = col[3].find_all('div', {'class':'sc-vote-details-summary-table-col-cell'})[1].text
        motion.TotalVotes = int(totals)
        result = col[4].find_all('div', {'class':'sc-vote-details-summary-table-col-cell-tall'})[0].text
        motion.Result = result
        motion, motionU, motion_is_new, log = save_and_return(motion, motionU, log)
        prnt('motion',motion,'motionU',motionU)

        table = soup.find('div',{'class':'table-responsive'})
        tbody = table.find('tbody')
        trs = tbody.find_all('tr')
        vote_count = 0
        result_data = {'Parties':[], 'Votes':[], 'PartyData':{}}
        for tr in trs:
            vote_count += 1
            td = tr.find_all('td')
            a = td[0].find('a')
            person_link = a['href']
            person_name = a.text.strip()
            prntDebug('person_name',person_name)
            a = person_name.find(', ')
            last_name = person_name[:a]
            first_name = person_name[a+2:]
            a = person_link.find('/senator/')+len('/senator/')
            b = person_link[a:].find('/')
            iden = person_link[a:a+b]
            person = Person.objects.filter(GovIden=iden, Validator_obj__is_valid=True).first()
            prnt('person',person)
            if not person:
                personU = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person), Region_obj=country, data__Position__icontains="Senator", data__FirstName__icontains=first_name, data__LastName__icontains=last_name, extra__roles__contains=[{'current':True,'gov_level':'Federal'}])
                if personU:
                    person = personU.Pointer_obj
                    if not person.GovIden:
                        person.GovIden = iden
                        personU.data['GovIden'] = iden
                        person, personU, person_is_new, log = save_and_return(person, personU, log)

            vote, voteU, vote_is_new = get_model_and_update('RepVote', Motion_obj=motion, Person_obj=person, Country_obj=country, Government_obj=gov, Region_obj=country)
            if person:
                vote.Person_obj = person
            
            vote.VoteValue = None
            if td[3]['data-order'] == 'aaa':
                vote.IsVoteYea = 'True'
                vote.VoteValue = 'Yea'
            if td[4]['data-order'] == 'aaa':
                vote.IsVoteNay = 'True'
                vote.VoteValue = 'Nay'
            if td[5]['data-order'] == 'aaa':
                vote.IsVoteAbsent = 'True'
                vote.VoteValue = 'Absentation'
            vote.DateTime = date_time
            vote, voteU, vote_is_new, log = save_and_return(vote, voteU, log)
            if vote.VoteValue:
                found = False
                for i in result_data['Votes']:
                    if i['Vote'] == vote.VoteValue:
                        i['Count'] += 1
                        found = True
                        break
                if not found:
                    result_data['Votes'].append({'Vote':vote.VoteValue, 'Count':1})
        
        sorted_votes = sorted(result_data['Votes'], key=lambda item: item['Count'], reverse=True)
        result_data['Votes'] = sorted_votes
        sorted_parties = sorted(result_data['Parties'], key=lambda item: item['Count'], reverse=True)
        result_data['Parties'] = sorted_parties
        motion.result_data = result_data
            
        time.sleep(2)
    motion.TotalVotes = vote_count
    motion, motionU, motion_is_new, log = save_and_return(motion, motionU, log)
    prntDebug('done add senate motion')
    return gov, log



def get_todays_xml_agenda():
    func = 'get_todays_xml_agenda'
    prnt(f'--{func} Canada', now_utc())
    log = []
    url = 'https://www.parl.ca/LegisInfo/en/overview/xml/onagenda'
    r = requests.get(url, verify=False)
    root = ET.fromstring(r.content)
    bills = root.findall('Bill')
    for b in bills:
        ShortTitle = b.find('ShortTitle').text
        prntDebug(ShortTitle)
        data, gov = get_bill(b, func)
        for d in data:
            log.append(d)
    send_for_validation(log, gov, func)
        # break

def get_user_region(u, url):
    func = 'get_user_region'
    prnt(f'--{func} Canada', now_utc())
    log = []

    result = {}
    result['greaterMunicipality_name'] = ''
    result['greaterMunicipality_id'] = ''
    result['greaterMunicipalityDistrict_name'] = ''
    result['greaterMunicipalityDistrict_id'] = ''

    country = Region.objects.filter(Name='Canada', nameType='Country').first()
    result['country_name'] = country.Name
    result['country_id'] = country.id
    # should not use verify=False but opennorth is giving ssl error
    r = requests.get(url, verify=False)
    data = json.loads(r.content)
    # prntDebug(data)
    try:
        prov = data['province']
        city = data['city']
        root = data['boundaries_centroid']
    except:
        root = data['objects']
    second_list = []
    try:
        for d in root:
            iden = d['external_id']
            name = d['name']
            type = d['boundary_set_name']
            prntDebug(type)
            if d['related']['boundary_set_url'] == '/boundary-sets/federal-electoral-districts/':
                prntDebug('riding,,,')
                try:
                    prntDebug('aa')
                    riding = District.objects.filter(Q(Name=name)&Q(Country_obj=country)&Q(nameType='riding')).first()
                except Exception as e:
                    prntDebug('err 32',str(e))
                    riding = District(Name=name, Country_obj=country, Region_obj=country, AltName=name.replace('—', ''), gov_level='Federal', nameType='riding')
                    riding.save()
                    log.append(riding)
                prntDebug(riding)
                prntDebug('done riding')
                result['federalDistrict_name'] = riding.Name
                result['federalDistrict_id'] = riding.id
            elif 'electoral district' in type and '2005' not in d['url'] and 'Federal' not in type:
                provState_name = type.replace(' electoral district', '')
                prntDebug(provState_name)
                try:
                    provState = Region.objects.filter(Name=provState_name, ParentRegion_obj=country, nameType='Province').first()
                except:
                    provState = Region(Name=provState_name, ParentRegion_obj=country, nameType='Province')
                    provState.save()
                    log.append(provState)
                result['provState_id'] = provState.id
                result['provState_name'] = provState.Name
                if not provState.AbbrName:
                    provState.AbbrName = prov
                    provState.save()
                try:
                    district = District.objects.filter(Name=name, Region_obj=provState, gov_level='Provincial', nameType='District')[0]
                except:
                    district = District(Name=name, Country_obj=country, Region_obj=provState, gov_level='Provincial', nameType='District')
                    district.save()
                    log.append(district)
                result['provStateDistrict_name'] = district.Name
                result['provStateDistrict_id'] = district.id
            elif 'ward' in type:
                second_list.append(d)
            elif 'School' in type:
                second_list.append(d)
        for m in second_list:
            iden = m['external_id']
            name = m['name']
            type = m['boundary_set_name']
            if 'ward' in type:
                # prntDebug('WARD')
                mun_name = type.replace(' ward', '')
                try:
                    municipality = Region.objects.filter(Name=mun_name, nameType='municipality').first()
                    # municipality, municipalityU, municipalityData, municipality_is_new = get_model_and_update('Region', obj=municipality)
                except:
                    municipality = Region(Name=mun_name, ParentRegion_obj=provState, nameType='municipality')
                    municipality.save()
                    log.append(municipality)

                result['municipality_name'] = municipality.Name
                result['municipality_id'] = municipality.id
                try:
                    ward = District.objects.filter(Name=name, Country_obj=country, Region_obj=municipality, gov_level='Municipal', nameType='ward').first()
                except:
                    ward = District(Name=name, Country_obj=country, Region_obj=municipality, gov_level='Municipal', nameType='ward')
                    ward.save()
                    log.append(ward)
                result['ward_name'] = ward.Name
                result['ward_id'] = ward.id
            elif 'School' in type:
                # prntDebug('school')
                pass
    except Exception as e:
        prntDebug('err 897', str(e))
        pass
    try:
        prntDebug('--representatives')
        try:
            root = data['representatives_centroid']
        except:
            root = data['objects']
        region = None
        for d in root:
            prntDebug('provstate',provState)
            url = d['url']
            last_name = d['last_name']
            first_name = d['first_name']
            name = d['name']
            type = d['representative_set_name']
            personal_url = d['personal_url']
            elected_office = d['elected_office']
            gender = d['gender']
            district_name = d['district_name']
            email = ['email']
            for i in d['offices']:
                try:
                    postal = i['postal']
                except:
                    postal = None
                try:
                    fax = i['fax']
                except:
                    fax = None
                try:
                    tel = i['tel']
                except:
                    tel = None
            photo_url = d['photo_url']
            try:
                twitter = d['extra']['twitter']
            except:
                twitter = None
            party_name = d['party_name']
            if 'Assembly' in type:
                try:
                    role = Role.objects.filter(Position=elected_office, District_obj=district, Region_obj=provState, Person_obj__LastName__icontains=last_name, Person_obj__FirstName__icontains=first_name)[0]
                    role, roleU, roleData, role_is_new = get_model_and_update('Role', obj=role)
                except:
                    party, partyU, partyData, party_is_new = get_model_and_update('Party', Name=party_name, gov_level='Provincial', Region_obj=provState)
                    party, partyU, partyData, party_is_new, log = save_and_return(party, partyU, partyData, party_is_new, log, func)
            
                    person, personU, personData, person_is_new = get_model_and_update('Person', Region_obj=provState, FirstName=first_name, LastName=last_name)
                    if photo_url and not person.PhotoLink:
                        person.PhotoLink = photo_url
                        personData['PhotoLink'] = photo_url
                        # p.save()
                    person, personU, personData, person_is_new, log = save_and_return(person, personU, personData, person_is_new, log, func)
            
                    role, roleU, roleData, role_is_new = get_model_and_update('Role', Position=elected_office, Person_obj=p, District_obj=district, Region_obj=provState, Party_obj=party)
            
                roleData['Current'] = True
                role.Telephone = tel
                role.Fax = fax
                role.Address = postal
                role.Email = email
                role.PhotoLink = photo_url
                role.Website = personal_url
                
                roleData['Telephone'] = tel
                roleData['Fax'] = fax
                roleData['Address'] = postal
                roleData['Email'] = email
                roleData['PhotoLink'] = photo_url
                roleData['Website'] = personal_url
                if twitter:
                    role.XTwitter = twitter
                    roleData['XTwitter'] = twitter
                role, roleU, roleData, role_is_new, log = save_and_return(role, roleU, roleData, role_is_new, log, func)
                
            elif 'Commons' in type:
            
                try:
                    role = Role.objects.filter(Position='Member of Parliament', District_obj=riding, Region_obj=country, Person_obj__LastName__icontains=last_name, Person_obj__FirstName__icontains=first_name)[0]
                    role, roleU, roleData, role_is_new = get_model_and_update('Role', obj=role)
                except:
                    party, partyU, partyData, party_is_new = get_model_and_update('Party', Name=party_name, gov_level='Federal', Region_obj=country)
                    party, partyU, partyData, party_is_new, log = save_and_return(party, partyU, partyData, party_is_new, log, func)
                    person, personU, personData, person_is_new = get_model_and_update('Person', Region_obj=country, FirstName=first_name, LastName=last_name)
                    if photo_url and not person.PhotoLink:
                        person.PhotoLink = photo_url
                        personData['PhotoLink'] = photo_url
                    person, personU, personData, person_is_new, log = save_and_return(person, personU, personData, person_is_new, log, func)
                    role, roleU, roleData, role_is_new = get_model_and_update('Role', Position='Member of Parliament', Person_obj=person, District_obj=riding, Region_obj=country, Party_obj=party)
            
                roleData['Current'] = True
                role.Telephone = tel
                role.Fax = fax
                role.Address = postal
                role.Email = email
                role.PhotoLink = photo_url
                role.Website = personal_url
                
                roleData['Telephone'] = tel
                roleData['Fax'] = fax
                roleData['Address'] = postal
                roleData['Email'] = email
                roleData['PhotoLink'] = photo_url
                roleData['Website'] = personal_url
                if twitter:
                    role.XTwitter = twitter
                    roleData['XTwitter'] = twitter
                role, roleU, roleData, role_is_new, log = save_and_return(role, roleU, roleData, role_is_new, log, func)
                
            elif 'City Council' in type:
                if 'Ward' in district_name:
                    # prntDebug("WARD")
                    try:
                        role = Role.objects.filter(Position=elected_office, District_obj=ward, Region_obj=municipality, Person_obj__LastName__icontains=last_name, Person_obj__FirstName__icontains=first_name)[0]
                        role, roleU, roleData, role_is_new = get_model_and_update('Role', obj=role)
                    except:
                        person, personU, personData, person_is_new = get_model_and_update('Person', Region_obj=municipality, FirstName=first_name, LastName=last_name)
                        if photo_url and not person.PhotoLink:
                            person.PhotoLink = photo_url
                            personData['PhotoLink'] = photo_url
                        person, personU, personData, person_is_new, log = save_and_return(person, personU, personData, person_is_new, log, func)
                        role, roleU, roleData, role_is_new = get_model_and_update('Role', Position=elected_office, Person_obj=person, District_obj=ward, Region_obj=municipality)
                
                else:
                    # prntDebug('NOT WARD')
                    try:
                        role = Role.objects.filter(Position=elected_office, Region_obj=municipality, Person_obj__last_name__icontains=last_name, Person_obj__first_name__icontains=first_name)[0]
                        role, roleU, roleData, role_is_new = get_model_and_update('Role', obj=role)
                    except:
                        person, personU, personData, person_is_new = get_model_and_update('Person', Region_obj=municipality, FirstName=first_name, LastName=last_name)
                        if photo_url and not person.PhotoLink:
                            person.PhotoLink = photo_url
                            personData['PhotoLink'] = photo_url
                        person, personU, personData, person_is_new, log = save_and_return(person, personU, personData, person_is_new, log, func)
                        role, roleU, roleData, role_is_new = get_model_and_update('Role', Position=elected_office, Person_obj=person, Region_obj=municipality)
                
                # u.follow_person.add(r.person)
                roleData['Current'] = True
                role.Telephone = tel
                role.Fax = fax
                role.Address = postal
                role.Email = email
                role.PhotoLink = photo_url
                role.Website = personal_url
                
                roleData['Telephone'] = tel
                roleData['Fax'] = fax
                roleData['Address'] = postal
                roleData['Email'] = email
                roleData['PhotoLink'] = photo_url
                roleData['Website'] = personal_url
                if twitter:
                    role.XTwitter = twitter
                    roleData['XTwitter'] = twitter
                role, roleU, roleData, role_is_new, log = save_and_return(role, roleU, roleData, role_is_new, log, func)
                
            elif 'School Board' in type:
                pass
                # prntDebug('PASS')
                
            elif 'Regional Council' in type:
                region_name = type.replace(' Regional Council', '')
                try:
                    greater_municipality = Region.objects.filter(Name=region_name, ParentRegion_obj=provState, nameType='Regional Municipality').first()
                except:
                    greater_municipality = Region(Name=region_name, ParentRegion_obj=provState, nameType='Regional Municipality')
                    greater_municipality.save()
                    log.append(greater_municipality)

                    municipality.ParentRegion_obj = greater_municipality
                    municipality.save()
                    log.append(municipality)

                result['greaterMunicipality_name'] = greater_municipality.Name
                result['greaterMunicipality_id'] = greater_municipality.id
                try:
                    greater_municipality_district = District.objects.filter(Name=district_name, Region_obj=greater_municipality, nameType='Regional District').first()
                except:
                    greater_municipality_district = District(Name=district_name, Country_obj=country, Region_obj=greater_municipality, nameType='Regional District')
                    greater_municipality_district.save()
                    log.append(greater_municipality_district)

                if municipality.Name.lower() == district_name.lower():
                    result['greaterMunicipalityDistrict_name'] = greater_municipality_district.Name
                    result['greaterMunicipalityDistrict_id'] = greater_municipality_district.id

                try:
                    role = Role.objects.filter(Position=elected_office, District_obj=greater_municipality_district, Region_obj=greater_municipality, Person_obj__LastName__icontains=last_name, Person_obj__FirstName__icontains=first_name).first()
                    role, roleU, roleData, role_is_new = get_model_and_update('Role', obj=role)
                except:
                    try:
                        person = Person.objects.filter(FirstName=first_name, LastName=last_name).filter(Q(Region_obj=greater_municipality)|Q(Region_obj=municipality)).first()
                        person, personU, personData, person_is_new = get_model_and_update('Person', obj=person)

                    except:
                        person, personU, personData, person_is_new = get_model_and_update('Person', Region_obj=greater_municipality, FirstName=first_name, LastName=last_name)
                    if photo_url and not person.PhotoLink:
                        person.PhotoLink = photo_url
                        personData['PhotoLink'] = photo_url
                    person, personU, personData, person_is_new, log = save_and_return(person, personU, personData, person_is_new, log, func)
                    role, roleU, roleData, role_is_new = get_model_and_update('Role', Position=elected_office, Person_obj=person, Region_obj=municipality)
                
                # u.follow_person.add(r.person)
                roleData['Current'] = True
                role.Telephone = tel
                role.Fax = fax
                role.Address = postal
                role.Email = email
                role.PhotoLink = photo_url
                role.Website = personal_url
                
                roleData['Telephone'] = tel
                roleData['Fax'] = fax
                roleData['Address'] = postal
                roleData['Email'] = email
                roleData['PhotoLink'] = photo_url
                roleData['Website'] = personal_url
                if twitter:
                    role.XTwitter = twitter
                    roleData['XTwitter'] = twitter
                role, roleU, roleData, role_is_new, log = save_and_return(role, roleU, roleData, role_is_new, log, func)
                

    except Exception as e:
        prntDebug('get_user_region fail',str(e))
    
    send_for_validation(log, None, func)
    return result

def get_federal_candidates(num):
    prntDebug('-get federal candidates', num)
    url = 'https://lop.parl.ca/sites/ParlInfo/default/en_CA/ElectionsRidings/Elections'
    try:
        prntDebug("opening browser")
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        # chrome_options.add_experimental_option( "prefs",{'profile.managed_default_content_settings.javascript': 2})
        # chrome_options.add_argument("--headless")
        driver = webdriver.Chrome(options=chrome_options)
        caps = DesiredCapabilities().CHROME
        # caps["pageLoadStrategy"] = "normal"  #  Waits for full page load
        caps["pageLoadStrategy"] = "eager"   # Do not wait for full page load
        driver = webdriver.Chrome(desired_capabilities=caps, options=chrome_options)
    except Exception as e:
        prntDebug('err',str(e))
    prntDebug('getting link')
    driver.get(url)
    # prntDebug('link retreived')
    toFillList = []
    timeout = 30
    element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="gridContainer"]/div/div[6]/div/div/div[1]/div/table/tbody/tr[1]/td[2]'))
    WebDriverWait(driver, timeout).until(element_present)
    # num = 1
    xpath = '//*[@id="gridContainer"]/div/div[6]/div/div/div[1]/div/table/tbody/tr'
    one = xpath + '[%s]' %(num)
    tr = driver.find_element(By.XPATH, one)
    parliamentNum = tr.text.replace('Parliament: ', '')
    prntDebug('parliament', parliamentNum)
    td = tr.find_element(By.CLASS_NAME, "dx-datagrid-group-closed")
    td.click()
    prntDebug('clicked')
    time.sleep(1)
    num += 1
    two = xpath + '[%s]' %(num)
    tr = driver.find_element(By.XPATH, two)
    title = tr.text.replace('Type of Election: ', '')
    td = tr.find_element(By.CLASS_NAME, "dx-datagrid-group-closed")
    td.click()
    prntDebug('clicked')
    time.sleep(1)
    num += 1
    three = xpath + '[%s]' %(num)
    tr = driver.find_element(By.XPATH, three)
    try:
        date = tr.text.replace('Date of Election: ', '').replace(' Profile', '')
        date_time = datetime.datetime.strptime(date, '%Y-%m-%d')
    except:
        date_time = None
    e = Election.objects.filter(level='Federal', type=title, end_date=date_time).first()
    if not e:
        e = Election(level='Federal', type=title, end_date=date_time)
        e.save()
    e.Parliament = int(parliamentNum)
    td = tr.find_element(By.CLASS_NAME, "dx-datagrid-group-closed")
    td.click()
    prntDebug('clicked')
    time.sleep(2)
    def get_list(driver):
        data = driver.find_elements(By.CLASS_NAME, "dx-data-row")
        for d in data:
            # time.sleep(1)
            tds = d.find_elements(By.CSS_SELECTOR, "td")
            for t in tds:
                if t.get_attribute('aria-colindex') == '4':
                    try:
                        img = t.find_element(By.CSS_SELECTOR, "img").get_attribute('src')
                    except:
                        img = None
                elif t.get_attribute('aria-colindex') == '5':
                    province = t.text
                elif t.get_attribute('aria-colindex') == '6':
                    a = t.find_element(By.CSS_SELECTOR, "a")
                    con_link = a.get_attribute('href')
                    constituency = a.text
                elif t.get_attribute('aria-colindex') == '7':
                    try:
                        a = t.find_element(By.CSS_SELECTOR, "a")
                        person_link = a.get_attribute('href')
                        name = a.text
                    except:
                        person_link = None
                        name = t.text
                elif t.get_attribute('aria-colindex') == '9':
                    occupation = t.text
                elif t.get_attribute('aria-colindex') == '10':
                    try:
                        a = t.find_element(By.CSS_SELECTOR, "a")
                        party_link = a.get_attribute('href')
                        alt_caucus = a.text
                    except:
                        party_link = None
                        alt_caucus = t.text
                    caucus = alt_caucus.replace(' Party of Canada', '').replace(' of Canada', '')
                elif t.get_attribute('aria-colindex') == '11':
                    result = t.text
                    # cant print text on headless for unknown reason
                    z = str(t.get_attribute('outerHTML'))
                    x = z.find('>')
                    c = z[x+1:].find('<')
                    result = z[x+1:x+1+c]
                elif t.get_attribute('aria-colindex') == '12':
                    vote_count = t.text
                    # cant print text on headless for unknown reason
                    z = str(t.get_attribute('outerHTML'))
                    x = z.find('>')
                    c = z[x+1:].find('<')
                    vote_count = z[x+1:x+1+c]
            a = name.find(', ')
            last_name = name[:a]
            first_name = name[a+2:]
            prntDebug(first_name, last_name)
            p = Person.objects.filter(first_name=first_name, last_name=last_name).first()
                # break
            if p:
                p = Person()
                # p.Region_obj = 
                p.first_name = first_name
                p.last_name = last_name
                p.save()
                p.create_post()
            if p.parl_ca_small_img != img:
                p.parl_ca_small_img = img
                p.save()
            con = Riding.objects.filter(Q(name=constituency)|Q(alt_name=constituency.replace('-', ''))).first()
            if not con:
                prov = Province.objects.filter(name=province).first()
                if prov:
                    prov = Province()
                    prov.name = province
                    prov.save()
                con = Riding()
                con.name = constituency
                con.alt_name = constituency.replace('-', '')
                con.province = prov
                con.province_name = prov.name
                con.parlinfo_link = con_link
                con.save()
                con.create_post()
                # con.fillout()
                toFillList.append(con)
            if con.parlinfo_link != con_link:
                con.parlinfo_link = con_link
                con.save()
            party = Party.objects.filter(Q(name=caucus)|Q(alt_name=alt_caucus), level='Federal').first9
            if not party:
                party = Party()
                party.name = caucus
                party.alt_name = alt_caucus
                party.level = 'Federal'
                party.parlinfo_link = party_link
                party.save()
                party.create_post()
                # party.fillout()
                toFillList.append(party)
            if party.parlinfo_link != party_link:
                party.parlinfo_link = party_link
                party.save()
            r = Role.objects.filter(person=p, position='Election Candidate', group='General Election', end_date=date_time).first()
            if not r:
                r = Role()
                # r.Region_obj = 
                r.person = p
                r.person_name = '%s %s' %(p.first_name, p.last_name)
                r.position = 'Election Candidate'
                r.group = 'General Election'
            r.end_date = date_time
            r.party_name = caucus
            r.province_name = province
            r.constituency_name = constituency
            r.riding = con
            r.party = party
            r.election = e
            r.occupation = occupation
            r.result = result
            # prntDebug(vote_count)
            # prntDebug(int(vote_count.replace(',','')))
            r.vote_count = int(vote_count.replace(',',''))
            r.parlinfo_link = person_link
            r.save()
    # prntDebug('get_list')        
    get_list(driver)
    n = 2
    # completed = 'notCompleted'
    while driver.find_element(By.CLASS_NAME, "dx-next-button") and 'disable' not in driver.find_element(By.CLASS_NAME, "dx-next-button").get_attribute('class'):
        prntDebug('page ', n)
        next = driver.find_element(By.CLASS_NAME, "dx-next-button")
        next.click()
        time.sleep(2)
        get_list(driver)
        n += 1
    prntDebug('done1')
    driver.quit()
    prntDebug('--toFillList---')
    for i in toFillList:
        if i.parlinfo_link or not i.wikipedia:
            i.fillout()
    driver.quit()
    
def get_all_federal_candidates():
    num = 44
    for n in range(num):
        n+=1
        get_federal_candidates(n)

def get_house_committees(objType='committee', value='latest'):
    get_house_hansard_or_committee(objType, value)
    get_house_committee_list('latest')
    get_house_committee_work('latest')

def get_house_expenses():
    def run(url):
        r = requests.get(url, verify=False)
        soup = BeautifulSoup(r.content, 'html.parser')
        container = soup.find('div', {'class':'data-table-container'})
        trs = container.find_all('tr')
        for tr in trs:
            if tr != trs[0]:
                tds = tr.find_all('td')
                name = tds[0].text.strip()
                a = name.find(', ')
                last_name = name[:a]
                first_name = name[a+2:].replace('Hon. ', '').replace('Right ', '')
                prntDebug(first_name, last_name)
                con = tds[1].text.strip()
                # prntDebug(con)
                try:
                    riding = Riding.objects.filter(Q(name=con)|Q(alt_name=con.replace('—',''))).first()
                    r = Role.objects.filter(person__last_name=last_name, person__first_name=first_name, position='Member of Parliament', current=True, riding=riding)[0]
                    total = float(tds[3].text.strip().replace('$', '').replace(',','').replace('(','').replace(')','')) + float(tds[4].text.strip().replace('$', '').replace(',','').replace('(','').replace(')','')) + float(tds[5].text.strip().replace('$', '').replace(',','').replace('(','').replace(')','')) + float(tds[6].text.strip().replace('$', '').replace(',','').replace('(','').replace(')','')) 
                    prntDebug(total)
                    r.quarterlyExpenseReport = total
                    r.save()
                except Exception as e:
                    prntDebug(str(e))
                prntDebug('')
    try:
        url = 'https://www.ourcommons.ca/ProactiveDisclosure/en/members/%s/4' %(datetime.datetime.now().year)
        run(url)
    except Exception as e:
        prntDebug(str(e))
        try:
            url = 'https://www.ourcommons.ca/ProactiveDisclosure/en/members/%s/3' %(datetime.datetime.now().year)
            run(url)
        except Exception as e:
            prntDebug(str(e))
            try:
                url = 'https://www.ourcommons.ca/ProactiveDisclosure/en/members/%s/2' %(datetime.datetime.now().year)
                run(url)
            except Exception as e:
                prntDebug(str(e))
                try:
                    url = 'https://www.ourcommons.ca/ProactiveDisclosure/en/members/%s/1' %(datetime.datetime.now().year)
                    run(url)
                except Exception as e:
                    prntDebug(str(e))
                    prntDebug('fail fail')
    
def get_house_committee_list(day):
    # url = 'https://www.ourcommons.ca/Committees/en/Meetings?meetingDate=2022-10-31'
    # r = requests.get(url)
    # soup = BeautifulSoup(r.content, 'html.parser')
    # container = soup.find('div', {'id':'meeting-accordion'})
    # date = container.find('div', {'class':'grouping-header'})
    # prntDebug(date.text)
    # items = container.find_all('div', {'class':'accordion-item'})
    # for item in items:
    #     acron = item.find('span', {'class':'meeting-acronym'})
    #     timerange = item.find('div', {'class':'the-time'})
    #     title = item.find('div', {'class':'studies-activities-item'})
    #     h4 = item.find('h4', {'class':'meeting-card-committee-details-name'})
    #     title_link = h4.find('a')
    #     studies = item.find('div', {'class':'meeting-card-studiesactivities-title'})
    #     study = item.find('a', {'class':'current-study'})
    #     evidence = item.find('a', {'class':'btn-meeting-evidence'})
    #     minutes = item.find('a', {'class':'btn-meeting-minutes'})
    #     preview = item.find('div', {'class':'meeting-card-media-preview'})
    #     preview_src = preview.find('img')['src']
    #     try:
    #         embed = preview.find('button', {'class':'video-play-button'})['data-player-url']
    #     except:
    #         embed = None
    #     prntDebug(acron.text)
    #     prntDebug(timerange.text)
    #     prntDebug(title.text)
    #     prntDebug(h4.text.strip())
    #     prntDebug(title_link['href'])
    #     prntDebug(studies.text)
    #     prntDebug(study['href'])
    #     try:
    #         prntDebug(evidence['href'])
    #     except:
    #         prntDebug('no evidence')
    #     try:
    #         prntDebug(minutes['href'])
    #     except:
    #         prntDebug('no mins')
    #     prntDebug(preview_src)
    #     prntDebug(embed)
    #     com_title = h4.text.strip()
    #     a = com_title.find(' (')
    #     com_title = com_title[:a]

    prntDebug('--------------------house committees')
    parl = Parliament.objects.filter(country='Canada', organization='Federal')[0]
    try:
        if day == 'latest':
            url = 'https://www.ourcommons.ca/Committees/en/Meetings'
        else:
            url = day
        # prntDebug(url)
        r = requests.get(url, verify=False)
        soup = BeautifulSoup(r.content, 'html.parser')
        container = soup.find('div', {'id':'meeting-accordion'})
        date = container.find('div', {'class':'grouping-header'})
        prntDebug(date.text)
        items = container.find_all('div', {'class':'accordion-item'})
        for item in items:
            # prntDebug('-----------------------------')
            iden = item['id'].replace('meeting-item-', '')
            date = item['class'][1].replace('meeting-item-', '')
            acron = item.find('span', {'class':'meeting-acronym'})
            timerange = item.find('div', {'class':'the-time'})
            dt = timerange.text
            a = dt.find(' - ')
            start = dt[:a].replace('.','')
            prntDebug('start', start)
            b = dt[a:].find(' (')
            end = dt[a+3:a+b].replace('.', '')
            date_time_start = datetime.datetime.strptime(date + ' - ' + start, '%Y-%m-%d - %I:%M %p')
            date_time_end = datetime.datetime.strptime(date + ' - ' + end, '%Y-%m-%d - %I:%M %p')
            dt_plus_one = date_time_start + datetime.timedelta(days=1)

            titles = item.find_all('div', {'class':'studies-activities-item'})
            title = ''
            for t in titles:
                if not title:
                    title = t.text
                elif t.text not in title:
                    title = title + '\n' + t.text

            h4 = item.find('h4', {'class':'meeting-card-committee-details-name'})
            title_link = h4.find('a')
            location = item.find('div', {'class':'meeting-location'})
            webcast = item.find('i', {'class':'icon-web-video-cast'})
            television = item.find('i', {'class':'icon-television'})
            speaker = item.find('i', {'class':'icon-speaker'})
            studies = item.find('div', {'class':'meeting-card-studiesactivities-title'})
            study = item.find('a', {'class':'current-study'})
            evidence = item.find('a', {'class':'btn-meeting-evidence'})
            minutes = item.find('a', {'class':'btn-meeting-minutes'})
            preview = item.find('div', {'class':'meeting-card-media-preview'})
            preview_src = preview.find('img')['src']
            try:
                embed = preview.find('button', {'class':'video-play-button'})['data-player-url']
            except:
                embed = None
            # prntDebug(date)
            # prntDebug(date)
            # prntDebug(iden)
            # prntDebug(acron.text)
            # prntDebug(timerange.text)
            prntDebug(title)
            # prntDebug(h4.text.strip())
            # prntDebug(title_link['href'])
            # prntDebug(location.text.strip())
            # if webcast:
            #     prntDebug(webcast)
            # else:
            #     prntDebug('no webcast')
            # if television:
            #     prntDebug(television)
            # else:
            #     prntDebug('no television')
            # if speaker:
            #     prntDebug(speaker)
            # else:
            #     prntDebug('no speaker')
            # prntDebug(studies.text)
            # prntDebug(study['href'])
            # try:
            #     prntDebug(evidence['href'])
            # except:
            #     prntDebug('no evidence')
            # try:
            #     prntDebug(minutes['href'])
            # except:
            #     prntDebug('no mins')
            # prntDebug(preview_src)
            # prntDebug(embed)
            com_title = h4.text.strip()
            a = com_title.find(' (')
            com_title = com_title[:a]
            # prntDebug(com_title) 

            try:
                committee = Committee.objects.filter(code=acron.text, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber)[0]
            except:
                committee = Committee(code=acron.text, Title=com_title, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber)
                committee.save()
                committee.create_post()
            try:
                com = CommitteeMeeting.objects.filter(committee=committee, code=acron.text, date_time_start__range=[datetime.datetime.strftime(date_time_start, '%Y-%m-%d'), datetime.datetime.strftime(dt_plus_one, '%Y-%m-%d')])[0]
                prntDebug('com found')
                # prntDebug(com)
            except Exception as e:
                com = CommitteeMeeting(code=acron.text, committee=committee, date_time_start=date_time_start, Organization='House', ParliamentNumber=committee.ParliamentNumber, SessionNumber=committee.SessionNumber)
                # com.Publication_date_time = datetime.datetime.strptime('2022-10-31', '%Y-%m-%d')
                com.save()
                com.create_post()
                prntDebug('com created')
                # prntDebug(str(e))
            # dt = timerange.text
            # a = dt.find(' - ')
            # start = dt[:a].replace('.','')
            # prntDebug('start', start)
            # b = dt[a:].find(' (')
            # end = dt[a+3:a+b].replace('.', '')
            if 'Bill' in title:
                a = title.find('Bill')+len('Bill ')
                if ', ' in title:
                    b = title[a:].find(',')
                    code = title[a:a+b]
                else:
                    code = title[a:]
                try:
                    bill = Bill.objects.filter(NumberCode=code)[0]
                    com.bill = bill
                    prntDebug('BIll', bill)
                except Exception as e:
                    prntDebug(str(e))
            com.date_time_start = date_time_start
            com.date_time_end = date_time_end
            prntDebug(com.date_time_start)
            prntDebug(com.date_time_end)
            com.ItemId = iden
            com.Title = title
            # com.Organization = h4.text.strip()
            com.timeRange = timerange.text
            com.location = location.text.strip()
            # prntDebug('https://www.ourcommons.ca' + title_link['href'])
            com.govURL = 'https://www.ourcommons.ca' + title_link['href']
            com.studies = 'https://www.ourcommons.ca' + study['href']
            if evidence:
                com.evidence = evidence['href']
            if minutes:
                com.minutes = minutes['href']
            com.previewURL = 'https://www.ourcommons.ca' + preview_src
            if webcast or television or speaker:
                x = 'http://www.ourcommons.ca/embed/en/m/%s?ml=en&vt=watch&autoplay=true' %(com.ItemId)
                time.sleep(1)
                r = requests.get(x, verify=False)
                com.embedURL = r.url
            com.save()
            prntDebug('saved')
            # r = requests.get('https://www.ourcommons.ca' + title_link['href'])
            # soup = BeautifulSoup(r.content, 'html.parser')
            # chair = soup.find('span', {'class':'committee-member-card'})
            # a = chair.find('a')['href']
            # # prntDebug('chaired by')
            # prntDebug(a)
            # if a.startswith('//'):
            #     a = a[2:]
            # prntDebug(a)
            # prntDebug('should be:')
            # prntDebug('https://www.ourcommons.ca/Members/en/marc-garneau(10524)')
            # span = chair.find('span', {'class':'member-info'})
            # first_name = span.find('span', {'class':'first-name'}).text
            # last_name = span.find('span', {'class':'last-name'}).text
            # prntDebug(first_name, last_name)
            # try:
            #     p = Person.objects.filter(gov_profile_page=a)
                
            #     # p = r.person
            # except Exception as e:
            #     prntDebug(str(e))
            #     try:
            #         p = Person.objects.filter(first_name=first_name, last_name=last_name)[0]
            #     except Exception as e:
            #         prntDebug(str(e))
            #         p = None
            # prntDebug(p)
            # prntDebug(p.gov_profile_page)
            # prntDebug(p.gov_iden)
            # com_title = com.Organization
            # a = com_title.find(' (')
            # com_title = com_title[:a]
            # prntDebug('--%s--' %(com_title))
            try:
                if not committee.chair:
                    r = Role.objects.filter(group=com_title, current=True, affiliation='Chair')[0]
                    if r.person:
                        committee.chair = r
                    committee.save()
            except Exception as e:
                prntDebug(str(e))
                # try:
                #     r = Role.objects.filter(group=com_title)
                #     for i in r:
                #         prntDebug(i.affiliation)
                # except Exception as e:
                #     prntDebug(str(e))
            prntDebug('-------------------')
            # break
    except Exception as e:
        prntDebug(str(e))
    # sys.modules[__name__].__dict__.clear()
    # gc.collect()

def get_house_committee_work(value):   
    prntDebug('--------------------house committee work')
    def runFunc(url):
        r = requests.get(url, verify=False)
        soup = BeautifulSoup(r.content, 'html.parser')
        table = soup.find('table', {'class':'allcommittees-studiestable'})
        tbody = table.find('tbody')
        trs = tbody.find_all('tr')
        for tr in trs:
            tds = tr.find_all('td')
            code = tds[0].find('a').text.strip()
            prntDebug('---',code,'----')
            activity = tds[1].text.strip()
            prntDebug(activity)
            event = tds[2]
            try:
                a = 'https:' + event.find('a')['href']
            except:
                a = None
            event = re.sub(' +', ' ', event.text.strip())
            # prntDebug(event)
            # prntDebug(a)
            date = tds[3].text.strip()
            prntDebug(date)
            dt = datetime.datetime.strptime(date, '%A, %B %d, %Y')
            try:
                agendaItem = AgendaItem.objects.filter(date_time=dt, text='Government Orders')[0]
                # now = datetime.datetime.now()
                dt = dt.replace(hour=agendaItem.hour, minute=agendaItem.minute)
            except:
                pass
            # com = Committee.objects.filter(code=com)[0]
            prntDebug(dt)
            parl = Parliament.objects.filter(start_date__lte=dt, country='Canada', organization='Federal')[0]
            # prntDebug(parl)
            try:
                comMeeting = CommitteeMeeting.objects.filter(code=code, Title=activity, event=event)[0]
                # comItem = CommitteeItem.objects.filter(committeeCode=com, eventTitle=event, Item_date_time__year=dt.year, Item_date_time__month=dt.month, Item_date_time__day=dt.day)[0]
                prntDebug('meeting found')
            except:
                prntDebug('creating meeting')
                if code != 'SSRS':
                    prntDebug(code)
                    com = Committee.objects.filter(code=code, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber)[0]
                    comMeeting = CommitteeMeeting(Organization='House', committee=com, code=code, Title=activity, event=event, date_time_start=dt, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber)
                    if 'Bill' in activity:
                        prntDebug('bill:')
                        x = activity.find('Bill')+len('Bill ')
                        # prntDebug(x)
                        if ',' in activity[x:]:
                            y = activity[x:].find(',')
                            z = activity[x:x+y]   
                        elif '-' in activity[x:]:
                            y = activity[x:].find('-')
                            if ' ' in activity[x+y:]:
                                w = activity[x+y:].find(' ')
                                z = activity[x+y-1:x+y+w]   
                            else:
                                z = activity[x+y-1:]   
                        prntDebug(z)
                        bill = Bill.objects.filter(NumberCode=z, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber)[0]
                        comMeeting.bill = bill
                        prntDebug(bill)
                    if a:
                        # url = 'https://www.ourcommons.ca/DocumentViewer/en/44-1/HUMA/report-7/'
                        prntDebug(a)
                        time.sleep(1)
                        r = requests.get(a, verify=False)
                        soup = BeautifulSoup(r.content, 'html.parser')
                        try:
                            btn_toc = soup.find('a', {'class':'btn-toc'})['href']
                            prntDebug('TOC found')
                            r = requests.get('https://www.ourcommons.ca' + btn_toc, verify=False)
                            soup = BeautifulSoup(r.content, 'html.parser')
                            try:
                                sum_link = soup.find("a", string="LIST OF RECOMMENDATIONS")['href']
                            except:
                                sum_link = soup.find("a", string="SUMMARY")['href']
                            # prntDebug(sum_link)
                            comMeeting.reportLink = 'https://www.ourcommons.ca' + sum_link
                            r = requests.get(comMeeting.reportLink, verify=False)
                            soup = BeautifulSoup(r.content, 'html.parser')
                            div = soup.find('div', {'class':'WordSection1'})
                            paras = div.find_all('p')
                            content = ''
                            for p in paras:
                                if str(p) != '<p> </p>':
                                    # content = content + re.sub(' +', ' ', p.text.strip()) + '\n\n'
                                    content = content + str(p)
                            # # prntDebug('-----')
                            # # prntDebug(content.strip())
                            # # prntDebug('------')
                            comMeeting.report = content.strip()
                        except Exception as e:
                            prntDebug(str(e))
                            comMeeting.reportLink = a
                            # body = soup.find('div', {'class':'report-body'})
                            tables = soup.find_all('table')
                            content = ''
                            paragraph = ''
                            paragraph2 = ''
                            # td = tables[0].find('td')
                            for table in tables:
                                content = content + str(table)
                            #     if re.sub(' +', ' ', table.text.strip()) not in content:
                            #         content = content + re.sub(' +', ' ', table.text.strip()) + '\n\n'
                            #         paras = table.find_all('p')
                            #         for p in paras:
                            #             paragraph = paragraph + p.text
                            #             paragraph2 = paragraph2 + re.sub(' +', ' ', p.text.strip()) + '\n\n'
                            # content = content.replace(paragraph, '')
                            # report = content + '\n\n' + paragraph2
                            # # prntDebug('------')
                            # # prntDebug(report)
                            # # prntDebug('------')
                            if '<' in content and '>' in content:
                                x = content.find('>')
                                content = content[:x] + 'style="font-size:100%;"' + content[x:]
                            comMeeting.report = content
                    comMeeting.save()
                    comMeeting.create_post()
                    prntDebug('saved')
                time.sleep(3)
            prntDebug('-----------')
    if value == 'latest':
        # url = 'https://www.ourcommons.ca/Committees/en/Work?refineByEvents=&pageNumber=1&refineByCommittees='
        url = 'https://www.ourcommons.ca/Committees/en/Work?show=allwork&parl=44&ses=1&refineByEvents=Creation,ReportPresented,ReportGovernmentResponse,ReportConcurred,ReportNegatived,ReportWithdrawn&pageNumber=1&pageSize=20'
        runFunc(url)
    elif value == 'session':
        url = 'https://www.ourcommons.ca/Committees/en/Work?parl=44&ses=1&refineByCommittees=&refineByCategories=&refineByEvents=Creation,ReportPresented,ReportGovernmentResponse,ReportConcurred,ReportNegatived&sortBySelected=LatestEvents&show=allwork&pageNumber=1&pageSize=0'
        # url = 'https://www.ourcommons.ca/Committees/en/Work?show=allwork&parl=44&ses=1&refineByEvents=ReportGovernmentResponse&pageNumber=1'
        runFunc(url)
    elif value == 'all':
        parls = ['44', '43', '42', '41', '40', '39', '38', '37']
        for parl in parls:
            prntDebug('---------------------------------')
            prntDebug(parl)
            prntDebug('--------------------------------')
            time.slee(3)
            url = 'https://www.ourcommons.ca/Committees/en/Work?parl=%s&ses=0&refineByCommittees=&refineByCategories=&refineByEvents=Creation,ReportPresented,ReportGovernmentResponse,ReportConcurred,ReportNegatived&sortBySelected=LatestEvents&show=allwork&pageNumber=1&pageSize=0' %(parl)
            runFunc(url)
    # sys.modules[__name__].__dict__.clear()
    # gc.collect()

def get_all_house_motions():
    prntDebug('--get all house motions')
    sessions = ['44-1', '43-2', '43-1', '42-1', '41-2', '41-1', '40-3', '40-2', '40-1', '39-2','39-1','38-1']
    sessions = ['39-1','38-1']
    # sessions = ['44-1']
    for s in sessions:
        prntDebug(s)
        url = 'https://www.ourcommons.ca/members/en/votes/xml?parlSession=%s' %(s)
        r = requests.get(url, verify=False)
        root = ET.fromstring(r.content)
        motions = root.findall('Vote')
        # count = 0
        for motion in motions:
            m = add_house_motion(motion)
            prntDebug('-----------')
        time.sleep(2)

def get_senate_committee_transcript(committeeMeeting):
    prntDebug('--getting transcript--')
    prntDebug(committeeMeeting.transcriptURL)
    time.sleep(3)
    r = requests.get(committeeMeeting.transcriptURL)
    soup = BeautifulSoup(r.content, 'html.parser')
    ps = soup.find_all('p')
    speakers = {}
    # currentChair = None
    for p in ps:
        samePerson = False
        try:
            if 'center' in p['class']:
                prntDebug('has center class')
        except:
            # prntDebug('log')
            bold = p.find('b')
            if bold:
                div = bold
                title = bold.text
                if ', ' in bold.text and bold.text[-1] == ':' and not '(' in bold.text and not '"' in bold.text or ', ' in bold.text and bold.text[-2] == ':'  and not '(' in bold.text and not '"' in bold.text:
                    text = bold.text.replace('Hon. ', '').replace('The Hon. ', '').replace('Mr. ', '').replace('Mrs. ', '').replace('Ms. ', '').replace('Hon.\xa0', '').replace('The Hon.\xa0', '').replace('Mr.\xa0', '').replace('Mrs.\xa0', '').replace('Ms.\xa0', '').replace(': ', '').strip()
                    a = text.find(',')
                    name = text[:a]
                    name = name.split()
                    prntDebug(name)
                    last_name = name[-1]
                    first_name = text[:a].replace(last_name, '').strip()
                    try:
                        person = Person.objects.filter(first_name__icontains=first_name, last_name=last_name).first()
                    except:
                        prntDebug('creating person')
                        person = Person(first_name=first_name, last_name=last_name)
                        person.save()
                        person.create_post()
                elif 'Deputy Chair' in bold.text:
                    prntDebug('dep')
                    name = bold.text.replace('Deputy Chair ', '').replace(':', '')
                    name = name.split()
                    prntDebug(name)
                    last_name = name[-1]
                    if last_name in str(p.text).replace(str(bold.text), ''):
                        x = str(p.text).replace(str(bold.text), '').replace('Senator ','')
                        y = x.find(last_name)
                        z = x[:y].find('. ')+len('. ')
                        first_name = x[z:y].strip()
                    else:
                        first_name = name[0]
                    if '(Deputy Chair) in the chair' in p.text:
                        # prntDebug('tmp chair')
                        try:
                            r = Role.objects.filter(position='Senator', person__last_name__icontains=last_name).first()
                            person = r.person
                            committeeMeeting.currentChair = person
                            committeeMeeting.save()
                        except:
                            try:
                                person = Person.objects.filter(first_name__icontains=first_name, last_name=last_name).first()
                            except:
                                prntDebug('creating person')
                                person = Person(first_name=first_name, last_name=last_name)
                                person.save()
                                person.create_post()            
                        # prntDebug('temp chair found')
                    else:
                        try:
                            r = Role.objects.filter(committee_key=committeeMeeting.committee, title='Deputy Chair').first()
                            person = r.person
                            last_name = person.last_name
                        except:
                            try:
                                person = Person.objects.filter(first_name__icontains=first_name, last_name=last_name).first()
                            except:
                                prntDebug('creating person')
                                person = Person(first_name=first_name, last_name=last_name)
                                person.save()
                                person.create_post()
                            try:
                                r = Role.objects.filter(position='Senator', person=person).first()
                            except:
                                r = Role(position='Senator', person=person, current=False)
                                r.save()

                elif 'The Chair' in bold.text:
                    prntDebug('chair')
                    # prntDebug(committeeMeeting.committee)
                    if committeeMeeting.currentChair:
                        person = committeeMeeting.currentChair
                    else:
                        try:
                            r = Role.objects.filter(committee_key=committeeMeeting.committee, title='Chair').first()
                            person = r.person
                        except:
                            try:
                                person = Person.objects.filter(first_name__icontains=first_name, last_name=last_name).first()
                            except:
                                prntDebug('creating person')
                                person = Person(first_name=first_name, last_name=last_name)
                                person.save()
                                person.create_post()
                            try:
                                r = Role.objects.filter(position='Senator', person=person).first()
                            except:
                                r = Role(position='Senator', person=person, current=False)
                                r.save()
                    last_name = person.last_name
                    # prntDebug(person)
                elif 'Hon. Senators' in bold.text or 'An Hon. Senator' in bold.text:
                    # prntDebug('some senators')
                    samePerson = True
                    div = ''
                elif 'Senator' in bold.text:
                    # prntDebug('senator')
                    try:
                        name = bold.text.replace('Senator ', '').replace(':', '')
                        name = name.split()
                        last_name = name[-1]
                    except: #for errors in print
                        a = p.text.find(':')
                        name = p.text[:a].replace('Senator ', '')
                        name = name.split()
                        last_name = name[-1]
                    if last_name in str(p.text).replace(str(bold.text),''):
                        x = str(p.text).replace(str(bold.text), '').replace('Senator ','')
                        y = x.find(last_name)
                        z = x[:y].find('. ')+len('. ')
                        first_name = x[z:y].strip()
                    else:
                        first_name = name[0]
                    try:
                        r = Role.objects.filter(position='Senator', person__last_name__icontains=last_name).first()
                        person = r.person
                        prntDebug(person)
                        if '(Chair) in the chair' in p.text:
                            # prntDebug('tmp chair')
                            committeeMeeting.currentChair = person
                            committeeMeeting.save()
                    except Exception as e:
                        try:
                            person = Person.objects.filter(first_name__icontains=first_name, last_name=last_name).first()
                        except:
                            prntDebug('creating person')
                            prntDebug(first_name)
                            person = Person(first_name=first_name, last_name=last_name)
                            person.save()
                            person.create_post()
                        try:
                            r = Role.objects.filter(position='Senator', person=person).first()
                        except:
                            r = Role(position='Senator', person=person, current=False)
                            r.save()
                    if '(Chair) in the chair' in p.text:
                        # prntDebug('tmp chair')
                        committeeMeeting.currentChair = person
                        committeeMeeting.save()
                elif 'Mr.' in bold.text or 'Mrs.' in bold.text or 'Ms.' in bold.text:
                    prntDebug('Mr')
                    last_name = bold.text.replace('Mr. ', '').replace('Mrs. ', '').replace('Ms. ', '').replace('Mr.\xa0', '').replace('Mrs.\xa0', '').replace('Ms.\xa0', '').replace(': ', '').strip()
                    # prntDebug(last_name)
                    # prntDebug(speakers)
                    try:
                        person = speakers[last_name]
                    except Exception as e:
                        prntDebug(str(e))
                        name = last_name.split()
                        last_name = name[-1]
                        # prntDebug(last_name)
                        a = bold.text.find(last_name)
                        first_name = bold.text[:a].strip()
                        try:
                            person = Person.objects.filter(first_name__icontains=first_name, last_name=last_name).first()
                        except:
                            prntDebug('creating person')
                            person = Person(first_name=first_name, last_name=last_name)
                            person.save()
                            person.create_post()
                else:
                    samePerson = True
                    div = ''
                speakers[last_name] = person
                # prntDebug(speakers)
                if not samePerson:
                    try:
                        content = str(p).replace(str(div), '')
                        c = CommitteeItem.objects.filter(committeeMeeting=committeeMeeting, person=person, Content__icontains=content).first()
                        # prntDebug('cItem found')
                    except Exception as e:
                        # prntDebug('creating committeeItem')
                        if person:
                            c = CommitteeItem(committeeMeeting=committeeMeeting, person=person)
                        else:
                            c = CommitteeItem(committeeMeeting=committeeMeeting)
                        c.person_name = title.replace(': ','')
                        c.Content = ''
                        c.save()
            try: 
                # skip preamble with try/except
                if str(p).replace(str(div), '') not in c.Content:
                    try:
                        c.Content = c.Content + '\n' + str(p).replace(str(div), '')
                    except:
                        c.Content = str(p).replace(str(div), '')
                    committeeMeeting.people.add(person)
                    string =  re.sub('<[^<]+?>', '', c.Content)
                    words = re.findall(r'\w+', string)
                    c.wordCount = len(words)
                    c.meeting_title = committeeMeeting.Title
                    c.save() 
                    c.create_post()
            except Exception as e:
                prntDebug(str(e))
    committeeMeeting.has_transcript = True
    prntDebug('has_transcript', committeeMeeting.has_transcript)
    people = CommitteeItem.objects.filter(committeeMeeting=committeeMeeting)
    C_people = {}
    for p in people:
        try:
            if not p.person.id in C_people:
                C_people[p.person.id] = 1
            else:
                C_people[p.person.id] += 1
        except Exception as e:
            prntDebug(str(e))
    C_people = sorted(C_people.items(), key=operator.itemgetter(1),reverse=True)
    C_people = dict(C_people)
    committeeMeeting.peopleText = json.dumps(C_people)
    committeeMeeting.save()
    prntDebug('comMeeting saved')
    prntDebug('done')
    
def scrape_senate_committee_list(driver, session):
    element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="table-print"]/div[1]'))
    WebDriverWait(driver, 10).until(element_present)

    table = driver.find_element(By.XPATH, '//*[@id="table-print"]/div[1]')
    tbody = table.find_element(By.CSS_SELECTOR, 'tbody')
    trs = tbody.find_elements(By.CSS_SELECTOR, 'tr')
    committees = {}
    com_transcript = {}
    # videos = {}
    x = session.find('-')
    parl = session[:x]
    sess = session[x+len('-'):]
    prntDebug(parl)
    prntDebug(sess)
    time.sleep(3)
    for tr in trs:
        bill = None
        # prntDebug(tr.get_attribute('innerHTML'))
        tds = tr.find_elements(By.CSS_SELECTOR, 'td')
        dt = tds[0].find_element(By.CSS_SELECTOR, 'a')
        prntDebug(dt.text)
        # prntDebug(dt.get_attribute('href'))
        try:
            
            date_time = datetime.datetime.strptime(dt.text, '%b %d, %Y\n%I:%M %p %Z')
        except:
            date_time = datetime.datetime.strptime(dt.text, '%b %d, %Y\n%I:%M %p local time')
        com = tds[1].find_element(By.CSS_SELECTOR, 'a')
        prntDebug(com.text)
        prntDebug(com.get_attribute('href'))
        com_link = com.get_attribute('href')
        a = com_link.find('committees/') + len('committees/')
        b = com_link[a:].find('/')
        code = com_link[a:a+b]
        prntDebug(code.upper())
        try:
            studies_a = tds[2].find_element(By.CSS_SELECTOR, 'ul')
            studies_b = studies_a.find_element(By.CSS_SELECTOR, 'li')
            text = studies_b.text
            if 'Bill' in text:
                a = text.find(', ')
                b = text[:a].replace('Bill ', '')
                try:
                    bill = Bill.objects.filter(NumberCode=b).filter(ParliamentNumber=parl, SessionNumber=sess).filter(Q(OriginatingChamberName='Senate')|Q(OriginatingChamberName__icontains='House')).first()
                    prntDebug(bill)
                except:
                    pass
            studies_c = studies_b.find_elements(By.CSS_SELECTOR, 'ul')
            for c in studies_c:
                text = text.replace(c.text, '').strip()
        except:
            text = None
        if '(Special Joint)' in com.text:
            org = '(Special Joint)'
        else:
            org = 'Senate'
        try:
            committee = Committee.objects.filter(code=code.upper(), Organization=org, ParliamentNumber=parl, SessionNumber=sess).first()
        except:
            committee = Committee(code=code.upper(), Organization=org, Title=com.text, govURL=com.get_attribute('href'), ParliamentNumber=parl, SessionNumber=sess)
            committee.save()
            committee.create_post()
        try:
            comMeeting = CommitteeMeeting.objects.filter(committee=committee, govURL=dt.get_attribute('href')).first()
            prntDebug('meeting found')
            if bill and not comMeeting.bill:
                comMeeting.bill = bill
                comMeeting.save()
            if not comMeeting.Title:
                comMeeting.Title = text
                comMeeting.save()
        except Exception as e:
            prntDebug(str(e))
            comMeeting = CommitteeMeeting(committee=committee, Organization=org, date_time_start=date_time, Title=text, govURL=dt.get_attribute('href'), ParliamentNumber=committee.ParliamentNumber, SessionNumber=committee.SessionNumber)
            if bill:
                comMeeting.bill = bill
            comMeeting.save()
            comMeeting.create_post()
        links = tds[4].find_elements(By.CSS_SELECTOR, 'a')
        for l in links:
            if 'Video' in l.get_attribute('title'):
                comMeeting.embedURL = l.get_attribute('href') + '&viewMode=3'
                comMeeting.embedURL = comMeeting.embedURL.replace('http', 'https').replace('XRender', 'Harmony')
                if not comMeeting.timeRange:
                    try:
                        time.sleep(2)
                        r = requests.get(l.get_attribute('href'))
                        soup = BeautifulSoup(r.content, 'html.parser')
                        dt = soup.find('div', {'id':'scheduledtime'})
                        comMeeting.timeRange = dt.text
                    except:
                        pass
            if 'Transcripts' in l.get_attribute('title'):
                # prntDebug('transcripts')
                com_transcript[comMeeting] = l.get_attribute('href')
            if 'Interim' in l.get_attribute('title'):
                # prntDebug('interim')
                # prntDebug(l.get_attribute('href'))
                com_transcript[comMeeting] = l.get_attribute('href')
            if 'Audio' in l.get_attribute('title'):
                # prntDebug('audio')
                comMeeting.embedURL = l.get_attribute('href') + '&viewMode=3'
                try:
                    if not comMeeting.timeRange:
                        time.sleep(1)
                        r = requests.get(l.get_attribute('href'))
                        soup = BeautifulSoup(r.content, 'html.parser')
                        dt = soup.find('div', {'id':'scheduledtime'})
                        comMeeting.timeRange = dt.text
                except Exception as e:
                    prntDebug(str(e))
        comMeeting.save()
        committees[committee] = com.get_attribute('href')
    
    prntDebug('getting members')
    starting_url = driver.current_url
    for key, value in committees.items():
        try:
            if not key.chair and key.Organization != '(Special Joint)':
                prntDebug(key)
                prntDebug(value)
                driver.get(value)
                
                element_present = EC.presence_of_element_located((By.CLASS_NAME, 'sc-committee-members-dynamic-content-list'))
                WebDriverWait(driver, 4).until(element_present)
                content = driver.find_element(By.CLASS_NAME, 'sc-committee-members-dynamic-content-list')
                people = content.find_elements(By.CLASS_NAME, 'col-md-8')
                for p in people:
                    try:
                        h = p.find_element(By.CSS_SELECTOR, 'h3')
                        title = h.text
                    except:
                        title = 'Member'
                    a = p.find_element(By.CSS_SELECTOR, 'a')
                    try:
                        senator = Role.objects.filter(gov_page=a.get_attribute('href')).first()
                        try:
                            r = Role.objects.filter(person=senator.person, committee_key=key).first()
                            r.current = True
                            r.group = key.Title
                            r.save()
                        except:
                            r = Role(person=senator.person, committee_key=key, position='Committee Member', title=title, group=key.Title, current=True)
                            r.save()
                        key.members.add(r)
                        if title == 'Chair':
                            key.chair = r
                        key.save()
                    except Exception as e:
                        prntDebug(str(e))

                time.sleep(3)
            else:
                # prntDebug(key.chair.person)
                prntDebug('--')
        except Exception as e:
            prntDebug(str(e))
    if driver.current_url != starting_url:
        driver.get(starting_url)
    prntDebug('getting transcripts')
    for key, value in com_transcript.items():
        if key.has_transcript == False:
            prntDebug(key)
            prntDebug(key.date_time_start)
            key.transcriptURL = value
            # key.save()
            try:
                get_senate_committee_transcript(key)
            except Exception as e:
                prntDebug(str(e))
            time.sleep(2)
    driver.quit()
    prntDebug('done senate committee scrape')

def get_senate_committees(upcoming='past'):
    prntDebug('---------------------senate committees ', upcoming)
    parl = Parliament.objects.filter(country='Canada', organization='Federal').first()
    session = '%s-%s' %(parl.ParliamentNumber, parl.SessionNumber)
    url = 'https://sencanada.ca/en/committees/allmeetings/#?TabSelected=%s&filterSession=%s&PageSize=50' %(upcoming, session)
    prntDebug("opening browser")
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36")
    driver = webdriver.Chrome(options=chrome_options)
    caps = DesiredCapabilities().CHROME
    caps["pageLoadStrategy"] = "normal"  #  Waits for full page load
    driver = webdriver.Chrome(desired_capabilities=caps, options=chrome_options)
    driver.get(url)

    scrape_senate_committee_list(driver, session)
    prntDebug('done senate committee list')
    driver.quit()
    
    get_senate_committees(upcoming='upcoming')

def get_all_senate_committees():
    sessions = ['44-1', '43-2', '43-1', '42-1', '41-2', '41-1', '40-3', '40-2', '40-1', '39-2','39-1','38-1', '37-3','37-2','37-1','36-2','36-1','35-2','35-1']

    prntDebug("opening browser")
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36")
    driver = webdriver.Chrome(options=chrome_options)
    caps = DesiredCapabilities().CHROME
    caps["pageLoadStrategy"] = "normal"  #  Waits for full page load
    driver = webdriver.Chrome(desired_capabilities=caps, options=chrome_options)
    for s in sessions:
        url = 'https://sencanada.ca/en/committees/allmeetings/#?filterSession=%s&PageSize=50&SortOrder=DATEDESC&p=1' %(s)
        prntDebug(url, '------------------------------------------------------')
        driver.get(url)
        element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="table-print"]/div[1]'))
        WebDriverWait(driver, 10).until(element_present)
        run = True
        while run:
            prntDebug('waiting 10...')
            time.sleep(10)
            next = None
            arrows = driver.find_elements(By.CLASS_NAME, 'sen-pagination-buttons-arrow')
            if arrows:
                for arrow in arrows:
                    a = arrow.find_element(By.CSS_SELECTOR, 'a')
                    if a.get_attribute('aria-label') == 'Next':
                        next = a.get_attribute('href')
            prntDebug('start scrape')
            scrape_senate_committee_list(driver, s)
            if next:
                prntDebug(next, '--------next-----------------')
                driver.get(next)
                element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="table-print"]/div[1]'))
                WebDriverWait(driver, 10).until(element_present)
                prntDebug(driver.current_url)
            else:
                run = False

        prntDebug('----------next session')
    driver.quit()

def get_senate_committee_work(value='latest'):
    prntDebug('----------------------senate work')
    if value == 'alltime':
        pass
    else:
        url = 'https://sencanada.ca/en/committees/reports/'
    prntDebug("opening browser")
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36")
    driver = webdriver.Chrome(options=chrome_options)
    caps = DesiredCapabilities().CHROME
    caps["pageLoadStrategy"] = "normal"  #  Waits for full page load
    driver = webdriver.Chrome(desired_capabilities=caps, options=chrome_options)
    driver.get(url)
    element_present = EC.presence_of_element_located((By.CLASS_NAME, 'widget-committees-reports'))
    WebDriverWait(driver, 10).until(element_present)
    reports = driver.find_element(By.CLASS_NAME, 'widget-committees-reports')
    lis = reports.find_elements(By.CSS_SELECTOR, 'li')
    if value == 'latest':
        lis = lis[:20]
    for li in lis:
        a = li.find_element(By.CSS_SELECTOR, 'a').get_attribute('href')
        prntDebug(a)
        b = li.text.find('\n')
        c = li.text[b+len('\n'):].find('\n')
        activity = li.text[:b]
        com = li.text[b+len('\n'):b+len('\n')+c].replace('The Standing Senate Committee on ', '').replace('The Standing Committee on ', '').replace('The Standing Joint Committee for ', '')
        prntDebug('-------', com)
        event = li.text[b+len('\n')+c+len('\n'):]
        d = event.find(' - ')
        eventTitle = event[:d]
        prntDebug(event)
        date = event[d+len(' - '):]
        # prntDebug(date)
        dt = datetime.datetime.strptime(date, '%B %Y')
        parl = Parliament.objects.filter(country='Canada', organization='Federal', start_date__lte=dt).first()
        try:
            comMeeting = CommitteeMeeting.objects.filter(reportLink=a).first()
            prntDebug('meeting found')
        except:
            try:
                prntDebug('creating meeting')
                com = Committee.objects.filter(Title__icontains=com, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber).first()
                comMeeting = CommitteeMeeting(Organization='Senate', committee=com, reportLink=a, Title=activity, event=eventTitle, date_time_start=dt, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber)
                if 'Bill' in activity:
                    prntDebug('bill:')
                    x = activity.find('Bill')+len('Bill ')
                    if ',' in activity[x:]:
                        y = activity[x:].find(',')
                        z = activity[x:x+y]   
                    elif '-' in activity[x:]:
                        y = activity[x:].find('-')
                        if ' ' in activity[x+y:]:
                            w = activity[x+y:].find(' ')
                            z = activity[x+y-1:x+y+w]   
                        else:
                            z = activity[x+y-1:]   
                    # prntDebug(z)
                    bill = Bill.objects.filter(NumberCode=z, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber).first()
                    comMeeting.bill = bill
                    prntDebug(bill)
                time.sleep(2)
                r = requests.get(a)
                soup = BeautifulSoup(r.content, 'html.parser')
                containers = soup.find_all('div', {'class':'container'})
                for container in containers:
                    if 'Report of the committee' in container.text:
                        div = container.find('div')
                        first_p = div.find('p')
                        try:
                            dt = datetime.datetime.strptime(first_p.text, '%A, %B %d, %Y')
                        except:
                            dt = datetime.datetime.strptime(first_p.text, '%B %d, %Y')
                        comMeeting.date_time_start = dt
                        prntDebug(dt)
                        content = str(div).replace(str(first_p), '')
                        comMeeting.report = content
                comMeeting.save()
                comMeeting.create_post()
            except Exception as e:
                prntDebug(str(e))
    driver.quit()

def get_senate_agendas(value='latest'):
    prntDebug('-------------------senate agenda')
    parl = Parliament.objects.filter(country='Canada', organization='Federal').first()
    dt = datetime.datetime.now()
    l = 'https://senparlvu.parl.gc.ca/Harmony/en/View/EventListView/%s%s%s/307' %(dt.year, dt.month, dt.day)
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    caps = DesiredCapabilities().CHROME
    caps["pageLoadStrategy"] = "normal"  #  Waits for full page load
    # caps["pageLoadStrategy"] = "eager"   # Do not wait for full page load
    driver = webdriver.Chrome(desired_capabilities=caps, options=chrome_options)
    # prntDebug(self.parlinfo_link)
    driver.get(l)
    def action(driver):
        element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="divEventList"]/div[2]/div[1]'))
        WebDriverWait(driver, 10).until(element_present)
        # signIn = driver.find_element(By.XPATH, '//*[@id="right-content"]/a')
        # r = requests.get(l)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # prntDebug(soup)
        divs = soup.find_all('div', {'class':'divEvent'})
        for div in divs:
            a = div.find('a')
            prntDebug(a['href'])
            x = a['href'].rfind('/')+len('/')
            code = a['href'][x:]
            date = a.find('div', {'class':'eventDate'}).text
            prntDebug(date)
            '--Thu, Feb 9, 2023 --'
            time = a.find('div', {'class':'eventTime'}).text
            prntDebug(time)
            x = time.find('-')
            st = time[:x]
            et = time[x+len('-'):]
            start_time = datetime.datetime.strptime(date + '--' + st, '%a, %b %d, %Y --%I:%M %p')
            prntDebug(start_time)
            end_time = datetime.datetime.strptime(date + '--' + et, '%a, %b %d, %Y --%I:%M %p')
            prntDebug(end_time)
            vid = 'https://senparlvu.parl.gc.ca/Harmony/en/PowerBrowser/PowerBrowserV2/%s%s%s/-1/%s?viewMode=3&globalStreamId=16' %(start_time.year, start_time.month, start_time.day, code)
            # parl = Parliament.objects.filter(start_time__lte=start_time)[0]
            try:
                agenda = Agenda.objects.filter(organization='Senate', date_time=start_time).first()
            except:
                agenda = Agenda(organization='Senate', gov_level='Federal', date_time=start_time)
                agenda.end_date_time = end_time
                agenda.VideoURL = vid
                agenda.videoCode = code
                agenda.save()
                agenda.create_post()
            try:
                H = Hansard.objects.filter(agenda=agenda).first()
            except:
                H = Hansard(agenda=agenda, Publication_date_time=start_time, Organization='Senate')
                H.ParliamentNumber=parl.ParliamentNumber
                H.SessionNumber=parl.SessionNumber
                H.save()
                H.create_post() 

            prntDebug('')
        prntDebug('done page')
    run = True
    while run:
        action(driver)
        if value == 'session':
            try:
                time.sleep(3)
                next = driver.find_element(By.XPATH, '//*[@id="btnNext"]').click()
            except:
                run = False
        else:
            run = False
    driver.quit()

def get_all_agendas():
    'https://www.ourcommons.ca/en/parliamentary-business/2001-01-29'
    # today = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d')
    start_date = '%s-%s-%s' %(2001, 1, 29)
    #rerun committee hansards from here
    # start_date = '%s-%s-%s' %(2020, 10, 15)
    start_date = '%s-%s-%s' %(2023, 3, 1)
    # start_date = '%s-%s-%s' %(2021, 7, 20)
    #run rest from here
    # start_date = '%s-%s-%s' %(2022, 4, 5)
    prntDebug(start_date)
    day = datetime.datetime.strptime(start_date, '%Y-%m-%d')
    # prntDebug(isinstance(day, str))
    # prntDebug(day)
    plus_day = 1
    while day <= datetime.datetime.now():
        day = datetime.datetime.strftime(day, '%Y-%m-%d')
        prntDebug(day)
        
        han_url = 'https://www.ourcommons.ca/PublicationSearch/en/?PubType=40017&xml=1&parlses=from%sto%s' %(day, day)
        prntDebug('-----------getting committee hansard')
        prntDebug(han_url)
        try:
            get_house_hansard_or_committee('committee', han_url)
        except Exception as e:
            prntDebug('not found')
            prntDebug(str(e))
        # prntDebug('')
        prntDebug('-------------------------------------------------------------------')
        day = datetime.datetime.strptime(day, '%Y-%m-%d')
        day = datetime.datetime.strftime(day + datetime.timedelta(days=plus_day), '%Y-%m-%d')
        prntDebug('next', day)
        day = datetime.datetime.strptime(day, '%Y-%m-%d')
        
def get_federal_match(request, person):
    parl = Government.objects.filter(country='Canada', organization='Federal').first()
    reactions = UserAction.objects.filter(user=request.user, post__post_type='bill').filter(post__bill__province=None).order_by('-post__date_time')
    votes = {}
    my_votes = {}
    return_votes = []
    vote_matches = 0
    total_matches = 0
    match_percentage = None
    for r in reactions:
        try:
            bill = r.post.bill
            if r.isYea:
                votes[bill] = 'Yea'
            elif r.isNay:
                votes[bill] = 'Nay'
            # prntDebug(r.isYea, r.isNay)
        except:
            pass
    matched = []
    def match_vote(m, person, votes, bill, vote_matches, total_matches, return_votes):
        try:
            v = RepVote.objects.filter(motion=m, person=person).order_by('-motion__date_time').first()
            total_matches += 1
            return_votes.append(v)
            if v.VoteValueName == votes[bill]:
                vote_matches += 1
                # prntDebug('match')
            return 'match', vote_matches, total_matches, return_votes
        except Exception as e:
            pass
        return 'nomatch', vote_matches, total_matches, return_votes
    for bill in votes:
        try:
            motions = Motion.objects.filter(bill=bill, ParliamentNumber=parl.ParliamentNumber, SessionNumber=parl.SessionNumber).order_by('-date_time')
            for m in motions:
                my_votes[m.id] = votes[bill]
                result, vote_matches, total_matches, return_votes = match_vote(m, person, votes, bill, vote_matches, total_matches, return_votes)
                if result == 'match':
                    matched.append(m)
                    break
        except Exception as e:
            prntDebug('err 55',str(e))
    # prntDebug(vote_matches, '/', total_matches)
    try:
        match_percentage = int((vote_matches / total_matches) * 100)
    except Exception as e:
        match_percentage = None
    # prntDebug(match_percentage)
    return match_percentage, total_matches, vote_matches, my_votes, return_votes
