from django.contrib import admin


from accounts.models import *
# from transactions.models import *
from posts.models import *
from network.models import *

from django.contrib import admin
from django.db.models import ForeignKey



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

class AutoForeignKeyAdmin(admin.ModelAdmin):
    search_fields = ['id']
    # search_fields = list(dict.fromkeys(AutoForeignKeyAdmin.search_fields + ['pointerId', 'id']))
    # # results in ['id', 'pointerId'] — no duplicates

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        # Automatically set autocomplete fields for ForeignKeys
        self.autocomplete_fields = [
            field.name for field in model._meta.get_fields()
            if isinstance(field, ForeignKey)
            and field.remote_field.model._meta.model_name != "contenttype"
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
    

    def get_search_results(self, request, queryset, search_term):
        safe_search_fields = []
        custom_search_fields = []

        for field_path in self.search_fields:
            base = field_path.lstrip('=^@').split('__')[0]
            try:
                base_field = self.model._meta.get_field(base)
            except Exception:
                safe_search_fields.append(field_path)
                continue

            is_binary = base_field.__class__.__name__ in ('BinaryBase62Field', 'BinaryBase64urlField')
            is_fk_to_binary = (
                hasattr(base_field, 'remote_field')
                and base_field.remote_field
                and base_field.remote_field.model._meta.pk.__class__.__name__
                    in ('BinaryBase62Field', 'BinaryBase64urlField')
            )

            if is_binary or is_fk_to_binary:
                custom_search_fields.append(field_path)
            else:
                safe_search_fields.append(field_path)

        # Only call super() if there are safe fields — empty search_fields returns everything
        original_search_fields = self.search_fields
        self.search_fields = safe_search_fields
        try:
            if safe_search_fields:
                queryset, use_distinct = super().get_search_results(request, queryset, search_term)
            else:
                use_distinct = False
        finally:
            self.search_fields = original_search_fields

        if search_term and custom_search_fields:
            from django.db.models import Q
            q = Q()

            for field_path in custom_search_fields:
                parts = field_path.lstrip('=^@').split('__')
                base_field_name = parts[0]

                try:
                    base_field = self.model._meta.get_field(base_field_name)
                except Exception:
                    continue

                # Direct binary field on this model (id, hash, etc.)
                if base_field.__class__.__name__ in ('BinaryBase62Field', 'BinaryBase64urlField'):
                    try:
                        q |= Q(**{base_field_name: search_term})
                    except Exception as e:
                        prnt(f"[search debug] direct binary lookup failed: {e}")

                # FK field
                elif hasattr(base_field, 'remote_field') and base_field.remote_field:
                    related_model = base_field.remote_field.model
                    lookup_field = parts[1] if len(parts) > 1 else related_model._meta.pk.name

                    try:
                        related_field = related_model._meta.get_field(lookup_field)
                    except Exception as e:
                        prnt(f"[search debug] could not get related field {lookup_field}: {e}")
                        continue

                    if related_field.__class__.__name__ in ('BinaryBase62Field', 'BinaryBase64urlField'):
                        try:
                            related_objs = related_model.objects.filter(**{lookup_field: search_term})
                            if related_objs.exists():
                                q |= Q(**{f"{base_field_name}__in": related_objs})
                        except Exception as e:
                            prnt(f"[search debug] FK binary field lookup error: {e}")

            if q:
                if safe_search_fields:
                    # Merge with super() results
                    queryset = (queryset | self.model.objects.filter(q)).distinct()
                else:
                    # All fields are custom — replace entirely
                    queryset = self.model.objects.filter(q).distinct()
                use_distinct = True
            elif not safe_search_fields:
                # No safe fields and nothing matched — return empty
                queryset = self.model.objects.none()

        return queryset, use_distinct


    def get_search_results2(self, request, queryset, search_term):
        binary_field_names = {
            field.name for field in self.model._meta.get_fields()
            if field.__class__.__name__ in ('BinaryBase62Field', 'BinaryBase64urlField')
        }

        safe_search_fields = []
        custom_search_fields = []


        for field_path in self.search_fields:
            base = field_path.lstrip('=^@').split('__')[0]
            try:
                base_field = self.model._meta.get_field(base)
            except Exception:
                safe_search_fields.append(field_path)
                continue

            is_binary = base_field.__class__.__name__ in ('BinaryBase62Field', 'BinaryBase64urlField')
            is_fk_to_binary = (
                hasattr(base_field, 'remote_field')
                and base_field.remote_field
                and base_field.remote_field.model._meta.pk.__class__.__name__
                    in ('BinaryBase62Field', 'BinaryBase64urlField')
            )

            if is_binary or is_fk_to_binary:
                custom_search_fields.append(field_path)
            else:
                safe_search_fields.append(field_path)

        original_search_fields = self.search_fields
        self.search_fields = safe_search_fields
        try:
            queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        finally:
            self.search_fields = original_search_fields

        if search_term and custom_search_fields:
            from django.db.models import Q
            q = Q()

            for field_path in custom_search_fields:
                parts = field_path.lstrip('=^@').split('__')
                base_field_name = parts[0]

                try:
                    base_field = self.model._meta.get_field(base_field_name)
                except Exception:
                    continue

                # Direct binary field (id, hash, etc.)
                if base_field.__class__.__name__ in ('BinaryBase62Field', 'BinaryBase64urlField'):
                    try:
                        q |= Q(**{base_field_name: search_term})
                        prnt(f"[search debug] tried direct binary lookup on {base_field_name}")
                    except Exception as e:
                        prnt(f"[search debug] direct binary lookup failed: {e}")

                # Direct binary field (id, hash, etc.)
                if base_field.__class__.__name__ in ('BinaryBase62Field', 'BinaryBase64urlField'):
                    try:
                        # Validate it can actually be decoded before querying
                        test = self.model.objects.filter(**{base_field_name: search_term})
                        test_count = test.count()  # force evaluation to catch DB errors here
                        if test_count > 0:
                            q |= Q(**{base_field_name: search_term})
                    except Exception as e:
                        prnt(f"[search debug] direct binary lookup failed: {e}")
                        # Do NOT add to q — skip this field

                elif hasattr(base_field, 'remote_field') and base_field.remote_field:
                    related_model = base_field.remote_field.model
                    
                    if len(parts) == 1:
                        # e.g. 'Blockchain_obj' — fall back to pk
                        lookup_field = related_model._meta.pk.name
                    else:
                        # e.g. 'Blockchain_obj__someBinaryField' — use specified field
                        lookup_field = parts[1]

                    try:
                        related_field = related_model._meta.get_field(lookup_field)
                        related_field_class = related_field.__class__.__name__
                    except Exception as e:
                        prnt(f"[search debug] could not get related field {lookup_field}: {e}")
                        continue

                    if related_field_class in ('BinaryBase62Field', 'BinaryBase64urlField'):
                        try:
                            # Query the related model by that binary field
                            related_objs = related_model.objects.filter(**{lookup_field: search_term})
                            if related_objs.exists():
                                q |= Q(**{f"{base_field_name}__in": related_objs})
                                prnt(f"[search debug] found {related_objs.count()} related objs via {lookup_field}")
                            else:
                                prnt(f"[search debug] no related objs found via {lookup_field}={repr(search_term)}")
                        except Exception as e:
                            prnt(f"[search debug] FK binary field lookup error: {e}")

            prnt(f"[search debug] final Q: {q}")
            if q:
                extra = self.model.objects.filter(q)
                prnt(f"[search debug] extra qs count: {extra.count()}")
                queryset = (queryset | extra).distinct()
                use_distinct = True

            prnt(f"[search debug] safe_fields={safe_search_fields}")
            prnt(f"[search debug] super() qs count after={queryset.count()}")
            for field_path in self.search_fields:
                base = field_path.lstrip('=^@').split('__')[0]
                try:
                    base_field = self.model._meta.get_field(base)
                    prnt(f"[search debug] {field_path} -> {base_field.__class__.__name__}")
                except Exception as e:
                    prnt(f"[search debug] {field_path} -> NOT FOUND: {e}")


            prnt(f"[search debug] Q(id=...) result count: {self.model.objects.filter(id=search_term).count()}")
            
        return queryset, use_distinct

    def format_datetime(self, value):
        if value:
            return value.strftime('%Y-%m-%d %H:%M:%S UTC')
        return '-'
    
    def has_delete_permission(self, request, obj=None):
        # Prevent all deletions by returning False
        return False

class SonetAdmin(AutoForeignKeyAdmin):
    list_display = ["Title"]
    list_display_links = []
    list_editable = []
    list_filter = []
    # readonly_fields = (full_utc('updated_on_node'),)
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = Sonet


class UserAdmin(AutoForeignKeyAdmin):
    list_display = [full_utc("username"), full_utc('last_login'), 'is_active', full_utc('date_joined'),'id',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    # readonly_fields = ('update_on_node',)

    # def update_on_node(self, obj):
    #     if obj.updated_on_node:
    #         return obj.updated_on_node.strftime('%Y-%m-%d %H:%M:%S')
    #     return '-'
    # update_on_node.short_description = 'updated_on_node (UTC)'

    search_fields = AutoForeignKeyAdmin.search_fields + ['username','id']
    class Meta:
        model = User

class UserDataAdmin(AutoForeignKeyAdmin):
    list_display = ['id',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = UserData

class UserPubKeyAdmin(AutoForeignKeyAdmin):
    list_display = ["id", 'User_obj', full_utc('created'),'keyType','end_life_dt',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id']
    class Meta:
        model = UserPubKey

class UserActionAdmin(AutoForeignKeyAdmin):
    list_display = ['id',full_utc('lastUpdate'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = UserAction

class UserVerificationAdmin(AutoForeignKeyAdmin):
    list_display = ['id',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = UserVerification

class SuperSignAdmin(AutoForeignKeyAdmin):
    list_display = ["pointerId", full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = SuperSign

class UserNotificationAdmin(AutoForeignKeyAdmin):
    list_display = ['User_obj',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = UserNotification

class NotificationAdmin(AutoForeignKeyAdmin):
    list_display = ["Title", 'id', full_utc('created'), 'pointerId', 'validated',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id','pointerId', 'Link', 'Title']
    class Meta:
        model = Notification


class RegionAdmin(AutoForeignKeyAdmin):
    list_display = ["Name", 'AbbrName','nameType',full_utc('created'),'id',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['Name','id']
    class Meta:
        model = Region

class KeyphraseAdmin(AutoForeignKeyAdmin):
    list_display = ['id', "key", full_utc('last_occured'), full_utc('first_occured')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['key']
    class Meta:
        model = Keyphrase

class KeyphraseTrendAdmin(AutoForeignKeyAdmin):
    list_display = ["key", 'trend_score','recent_occurences','total_occurences', full_utc('lastUpdate'), 'Chamber']
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['key']
    class Meta:
        model = KeyphraseTrend

class GenericModelAdmin(AutoForeignKeyAdmin):
    list_display = ['type', 'func', full_utc('created'), full_utc('DateTime'),'id','pointerId',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['type', 'id', 'func']
    class Meta:
        model = GenericModel


class SprenAdmin(AutoForeignKeyAdmin):
    list_display = [full_utc('created'), 'type', 're', 'pointerId', full_utc("DateTime"), full_utc('updated_on_node')]
    # list_display = ['type']
    list_display_links = []
    list_editable = []
    list_filter = []
    # readonly_fields = ('update_on_node','added_to_node')
    # def update_on_node(self, obj):
    #     if obj.updated_on_node:
    #         return obj.updated_on_node.strftime('%Y-%m-%d %H:%M:%S')
    #     return '-'
    # update_on_node.short_description = 'updated_on_node (UTC)'
    # def added_to_node(self, obj):
    #     if obj.added_to_node:
    #         return obj.added_to_node.strftime('%Y-%m-%d %H:%M:%S')
    #     return '-'
    # added_to_node.short_description = 'added_to_node (UTC)'

    search_fields = ['pointerId', 'id', 're', 'type']
    autocomplete_fields = AutoForeignKeyAdmin.search_fields + ['Region_obj']
    class Meta:
        model = Spren

class ImageFileAdmin(AutoForeignKeyAdmin):
    list_display = ['id', 'pointerId', 'source_url', full_utc("created"), full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    ordering = ['-created']
    search_fields = AutoForeignKeyAdmin.search_fields + ['source_url', 'pointerId', 'id']

    class Meta:
        model = ImageFile

class PostAdmin(AutoForeignKeyAdmin):
    list_display = [full_utc('DateTime'), 'pointerType', 'pointerId', 'validated', 'blockId', full_utc('created'), full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['pointerType', 'pointerId','id']
    class Meta:
        model = Post

    
    # list_display = (
    #     full_utc('my_time_field', 'Start Time'),
    #     full_utc('end_time'),  # Uses default label
    #     'other_field',
    # )

class UpdateAdmin(AutoForeignKeyAdmin):
    list_display = ['id', 'pointerId', 'networkChain', full_utc('DateTime'), 'Block_obj', 'validated', full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['pointerId', 'id']
    autocomplete_fields = AutoForeignKeyAdmin.search_fields + ['Region_obj']
    class Meta:
        model = Update


class PluginAdmin(AutoForeignKeyAdmin):
    list_display = ['id', 'Title','User_obj',full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = Plugin

class SignatureAdmin(AutoForeignKeyAdmin):
    list_display = ['id', 'pointerId','DateTime']
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id','pointerId']
    class Meta:
        model = Signature

class DataPacketAdmin(AutoForeignKeyAdmin):
    list_display = ['id', 'Node_obj','chainName', 'func', 'jobId', full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['chainName','func','jobId']
    class Meta:
        model = DataPacket

class NodeAdmin(AutoForeignKeyAdmin):
    list_display = ['id','node_name','User_obj',full_utc('activated_dt'),full_utc('suspended_dt'),full_utc('lastUpdate'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id','node_name','User_obj']
    class Meta:
        model = Node

class NodeRecordAdmin(AutoForeignKeyAdmin):
    list_display = ['id','pointerId','pointerType','networkChain',full_utc('DateTime'),'is_valid']
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id','networkChain']
    class Meta:
        model = NodeRecord

class NodeReviewAdmin(AutoForeignKeyAdmin):
    list_display = ['id', 'CreatorNode_obj', 'TargetNode_obj', 'lastUpdate']
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = NodeReview

class ValidatorAdmin(AutoForeignKeyAdmin):
    list_display = ['id', full_utc('created'),'networkChain','validatorType','func','is_valid','CreatorNode_obj','jobId',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['validatorType','func','id','jobId']
    class Meta:
        model = Validator

class BlockAdmin(AutoForeignKeyAdmin):
    list_display = ['id','index','validated',full_utc('DateTime'),'Blockchain_obj','CreatorNode_obj',full_utc('updated_on_node'),'Transaction_obj','hash']
    list_display_links = []
    list_editable = []
    list_filter = []
    ordering = ['-DateTime', '-created', '-index']
    search_fields = AutoForeignKeyAdmin.search_fields + ['networkChain','id','hash','Blockchain_obj','Blockchain_obj__genesisId','Transaction_obj']
    class Meta:
        model = Block

class BlockchainAdmin(AutoForeignKeyAdmin):
    list_display = ['id', 'genesisType', 'genesisName', 'chain_length','genesisId', full_utc('data_added_datetime'),full_utc('last_block_datetime'),full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = ['genesisName']
    list_filter = []
    ordering = ['-updated_on_node', 'chain_length']
    search_fields = AutoForeignKeyAdmin.search_fields + ['genesisName', 'genesisId','id']
    class Meta:
        model = Blockchain

class EventLogAdmin(AutoForeignKeyAdmin):
    list_display = ['id','func','jobId','type',full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['type', 'id']
    class Meta:
        model = EventLog

admin.site.register(User, UserAdmin)
admin.site.register(UserPubKey, UserPubKeyAdmin)
admin.site.register(SuperSign, SuperSignAdmin)
admin.site.register(UserNotification, UserNotificationAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(UserAction, UserActionAdmin)
admin.site.register(UserData, UserDataAdmin)
admin.site.register(UserVerification, UserVerificationAdmin)

admin.site.register(Region, RegionAdmin)
admin.site.register(Keyphrase, KeyphraseAdmin)
admin.site.register(KeyphraseTrend, KeyphraseTrendAdmin)
admin.site.register(GenericModel, GenericModelAdmin)
admin.site.register(Spren, SprenAdmin)
admin.site.register(ImageFile, ImageFileAdmin)
admin.site.register(Update, UpdateAdmin)
admin.site.register(Post, PostAdmin)

admin.site.register(Sonet, SonetAdmin)
admin.site.register(Signature, SignatureAdmin)
admin.site.register(Plugin, PluginAdmin)
admin.site.register(DataPacket, DataPacketAdmin)
admin.site.register(Node, NodeAdmin)
admin.site.register(NodeRecord, NodeRecordAdmin)
admin.site.register(NodeReview, NodeReviewAdmin)
admin.site.register(Validator, ValidatorAdmin)
admin.site.register(Block, BlockAdmin)
admin.site.register(Blockchain, BlockchainAdmin)
admin.site.register(EventLog, EventLogAdmin)


