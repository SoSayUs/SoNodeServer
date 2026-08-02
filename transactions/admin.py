from django.contrib import admin


from accounts.admin import full_utc, AutoForeignKeyAdmin
from transactions.models import *



class WalletAdmin(AutoForeignKeyAdmin):
    list_display = ["id", full_utc('created'),'User_obj','Name',full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + []
    class Meta:
        model = Wallet

class TransactionAdmin(AutoForeignKeyAdmin):
    list_display = ["id",'token_value','ReceiverWallet_obj','SenderWallet_obj',full_utc('enact_dt'),'enacted','validated',full_utc('created'),full_utc('updated_on_node')]
    list_display_links = []
    list_editable = []
    list_filter = []
    search_fields = AutoForeignKeyAdmin.search_fields + ['id','ReceiverWallet_obj__id','SenderWallet_obj__id']
    class Meta:
        model = Transaction


admin.site.register(Wallet, WalletAdmin)
admin.site.register(Transaction, TransactionAdmin)