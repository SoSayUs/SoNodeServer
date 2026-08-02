from django.contrib import admin

from legis.models import *


from django.db.models import ForeignKey
from accounts.admin import AutoForeignKeyAdmin


def full_utc(field_name, label=None):
    def _func(obj):
        value = getattr(obj, field_name, None)
        if value is None:
            return "-"
        elif not isinstance(value, datetime.datetime):
            return value
        return value.strftime('%b %d, %Y, %H:%M:%S')
    _func.short_description = label or f"{field_name.replace('_', ' ').title()}"
    _func.admin_order_field = field_name
    return _func

class AutoForeignKeyAdmin2(admin.ModelAdmin):
    search_fields = ['id']

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        # Automatically set autocomplete fields for ForeignKeys
        self.autocomplete_fields = [
            field.name for field in model._meta.get_fields()
            if isinstance(field, ForeignKey)
        ]

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        # Automatically find all DateTimeFields and format them
        datetime_fields = [
            field.name for field in self.model._meta.fields
            if field.get_internal_type() == 'DateTimeField'
        ]
        formatted_fields = [f'formatted_{field}' for field in datetime_fields]
        return fields + tuple(formatted_fields)

    def __getattr__(self, name):
        if name.startswith('formatted_'):
            field_name = name.replace('formatted_', '')

            def formatted_field(obj):
                value = getattr(obj, field_name)
                return self.format_datetime(value)

            # Set the short description for the formatted field
            formatted_field.short_description = field_name.replace('_', ' ').title()
            return formatted_field

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def format_datetime(self, value):
        if value:
            return value.strftime('%Y-%m-%d %H:%M:%S UTC')
        return '-'
    
    def has_delete_permission(self, request, obj=None):
        # Prevent all deletions by returning False
        return False

class PersonAdmin(AutoForeignKeyAdmin):
    list_display = ["GovIden", "GovProfilePage", full_utc('created'), 'id',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['GovProfilePage', 'GovIden','id']
    class Meta:
        model = Person

class PartyAdmin(AutoForeignKeyAdmin):
    list_display = ["id", "Name", 'AltName', 'gov_level', 'Region_obj',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id']
    class Meta:
        model = Party

class DistrictAdmin(AutoForeignKeyAdmin):
    list_display = ["Name", 'ProvState_obj','Region_obj', 'gov_level', 'id', full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id',"Name", 'ProvState_obj__id']
    class Meta:
        model = District


class BillAdmin(AutoForeignKeyAdmin):
    list_display = ["NumberCode", "Title", "Chamber", full_utc('created'), full_utc('DateTime'), 'Government_obj', 'Region_obj', 'id']
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['NumberCode', 'id']
    class Meta:
        model = Bill

class BillTextAdmin(AutoForeignKeyAdmin):
    list_display = ["id", "pointerId", full_utc('added_to_node'), full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id','pointerId']
    class Meta:
        model = BillText

class MotionAdmin(AutoForeignKeyAdmin):
    list_display = ['VoteNumber', full_utc("DateTime"), 'Chamber',  full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id']
    class Meta:
        model = Motion


class VoteAdmin(AutoForeignKeyAdmin):
    list_display = [full_utc('created'), "PersonFullName", 'Motion_obj',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id','Motion_obj__id']
    class Meta:
        model = Vote


class ActionAdmin(AutoForeignKeyAdmin):
    list_display = ['type', 'func', full_utc('created'), full_utc('DateTime'),'id','pointerId',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['type', 'id', 'func']
    class Meta:
        model = Action

class MeetingAdmin(AutoForeignKeyAdmin):
    list_display = ['Chamber', 'Title', 'meeting_type', full_utc('DateTime'), full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['Title', 'id']
    class Meta:
        model = Meeting

class CommitteeAdmin(AutoForeignKeyAdmin):
    list_display = ['Chamber', 'Title', 'Code']
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['Title','id']
    class Meta:
        model = Committee

class StatementAdmin(AutoForeignKeyAdmin):
    list_display = ["id", "PersonName", 'Chamber', 'Region_obj', full_utc('created'), full_utc('DateTime'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['PersonName', 'Chamber','id','Meeting_obj__id']
    class Meta:
        model = Statement

class AgendaAdmin(AutoForeignKeyAdmin):
    list_display = [full_utc('DateTime'), full_utc('created'), 'Chamber', 'id',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id']
    class Meta:
        model = Agenda

class GovernmentAdmin(AutoForeignKeyAdmin):
    list_display = ['id','gov_level', 'GovernmentNumber', 'SessionNumber','proposed_modification',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id']
    class Meta:
        model = Government

class ElectionAdmin(AutoForeignKeyAdmin):
    list_display = ['type', full_utc('DateTime'), 'Chamber', 'Country_obj',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id']
    class Meta:
        model = Election


admin.site.register(Person, PersonAdmin)
admin.site.register(Party, PartyAdmin)
admin.site.register(District, DistrictAdmin)
admin.site.register(Bill, BillAdmin)
admin.site.register(BillText, BillTextAdmin)
admin.site.register(Motion, MotionAdmin)
admin.site.register(Vote, VoteAdmin)
admin.site.register(Action, ActionAdmin)
admin.site.register(Meeting, MeetingAdmin)
admin.site.register(Statement, StatementAdmin)
admin.site.register(Committee, CommitteeAdmin)
admin.site.register(Agenda, AgendaAdmin)
admin.site.register(Government, GovernmentAdmin)
admin.site.register(Election, ElectionAdmin)