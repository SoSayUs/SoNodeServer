from utils.models import get_self_node
from django.db import models
from django.db.models import Q

from network.models import Blockchain, Block
from utils.models import BinaryBase62Field, prnt, is_locked, now_utc, string_to_dt, get_latest_dataPacket
from utils.locked import hash_obj_id
import re
import datetime
import django_rq
from decimal import Decimal

model_prefixes = {'Wallet':'wal','Transaction':'tra'}

class Wallet(models.Model):
    networkChain = models.CharField(max_length=50, default="User", blank=True)
    commitChain = models.CharField(max_length=50, default="Plugin", blank=True)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    User_obj = models.ForeignKey('accounts.User', blank=True, null=True, on_delete=models.CASCADE)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT) # User_obj chain
    Name = models.CharField(max_length=50, default="Main", blank=True, null=True)
    value = models.TextField(default="0") # modifiable_field
    signed = models.JSONField(default=dict)
    
    def __str__(self):
        try:
            if self.User_obj is not None:
                return f'WALLET:{self.User_obj}-{self.Name}'
        except Exception as e:
            prnt('wallet err 253',self.id, str(e))
            pass
        return f'WALLET:User_obj_err-{self.Name}'
        
    class Meta:
        ordering = ['-created', 'id']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Wallet', 'networkChain': 'User', 'commitChain': 'Plugin', 'id': None, 'modlVer': 1, 'created': None, 'lastUpdate': None, 'User_obj': None, 'Block_obj': None, 'Name': 'Main', 'value': '0', 'signed': {}}
        
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['created', 'User_obj', 'Name']

    def get_chain(self):
        return Blockchain.objects.filter(id=self.networkChain).defer('queuedData').first()
    
    def tally_tokens(self, full_recount=False, exclude=None):
        prnt('-tally_tokens wallet')
        if not full_recount:
            latest_block = Block.objects.filter(Blockchain_obj=self.get_chain(), validated=True).order_by('-index').first()
            prnt('latest_block',latest_block)
            if latest_block and 'wallet_total' in latest_block.notes:
                latest_dt = string_to_dt(latest_block.notes['wallet_total']['dt'])
                latest_value = float(latest_block.notes['wallet_total']['value'])
                latest_transactions = Transaction.objects.filter(Q(ReceiverWallet_obj=self)|Q(SenderWallet_obj=self), validated=True, enacted=True, enact_dt__gt=latest_dt).order_by('enact_dt')
                for transaction in latest_transactions:
                    if exclude and transaction == exclude:
                        pass
                    elif transaction.ReceiverWallet_obj == self:
                        latest_value += Decimal(transaction.token_value)
                    elif transaction.SenderWallet_obj == self:
                        latest_value -= Decimal(transaction.token_value)
                if self.value != str(latest_value):
                    self.value = str(latest_value)
                    self.save(update_fields=['value'])
                prnt('latest_value',latest_value)
                return str(latest_value)
                
        target_value = 0
        utrIdens = []
        
        utrs = Transaction.objects.filter(Q(ReceiverWallet_obj=self)|Q(SenderWallet_obj=self), validated=True, enacted=True, enact_dt__lte=now_utc()).order_by('-enact_dt')
        for utr in utrs:
            if exclude and utr == exclude:
                pass
            elif utr.ReceiverWallet_obj == self and utr.ReceiverBlock_obj and utr.ReceiverBlock_obj.validated:
                # prnt('a')
                target_value = Decimal(target_value) + Decimal(utr.token_value)
            elif utr.SenderWallet_obj == self and utr.SenderBlock_obj and utr.SenderBlock_obj.validated:
                # prnt('b')
                target_value = Decimal(target_value) - Decimal(utr.token_value)
        
        prnt('target_value',target_value)
        self.value = str(target_value)
        self.save()
        return self.value

    def boot(self, blockchain=None, datapacket=None):
        prnt('-boot wallet',self)
        chain = Blockchain.objects.filter(genesisId=self.id).first()
        if not chain:
            chain = Blockchain(genesisName=self.Name, genesisType=self._meta.object_name, genesisId=self.id, created=self.created)
            chain.save()
        if not self.Block_obj:
            chain.add_item_to_queue(self)
        if not datapacket:
            datapacket = get_latest_dataPacket()
        if datapacket:
            datapacket.add_item_to_share(self) 
        super(Wallet, self).save() 
        return self          

    def save(self, share=False, sig=None, *args, **kwargs):
        if string_to_dt(self.created) >= now_utc()-datetime.timedelta(seconds=30):
            prnt('-save wallet 1')
            from utils.locked import verify_data, get_signing_data
            if verify_data(get_signing_data(self), self.signed, signature=sig):
                prnt('saving1...', self)
                super(Wallet, self).save(*args, **kwargs)
                self.boot()
        else:
            update_fields = kwargs.get('update_fields', None)
            if update_fields and 'value' in update_fields and len(update_fields) == 1:
                update_fields.append('updated_on_node')
                kwargs['update_fields'] = update_fields
                self.updated_on_node = now_utc()
                prnt('-save wallet 2')
                super(Wallet, self).save(*args, **kwargs)
            elif not is_locked(self):
                from utils.locked import verify_data, get_signing_data
                if verify_data(get_signing_data(self), self.signed, signature=sig):
                    prnt('-save wallet 3')
                    super(Wallet, self).save(*args, **kwargs)

    def delete(self):
        if string_to_dt(self.created) >= now_utc()-datetime.timedelta(seconds=60):
            super(Wallet, self).delete()

class Transaction(models.Model):
    networkChain = models.CharField(max_length=50, default="Wallet", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    validations = models.JSONField(default=dict, blank=True, null=True)
    senderChainGenId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    senderBlockId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    SenderBlock_obj = models.ForeignKey('network.Block', related_name='receiver_block', blank=True, null=True, on_delete=models.PROTECT)
    ReceiverBlock_obj = models.ForeignKey('network.Block', related_name='sender_block', blank=True, null=True, on_delete=models.PROTECT)
    ReceiverWallet_obj = models.ForeignKey('transactions.Wallet', related_name='receiver', blank=True, null=True, on_delete=models.PROTECT)
    SenderWallet_obj = models.ForeignKey('transactions.Wallet', related_name='sender', blank=True, null=True, on_delete=models.PROTECT)
    token_value = models.DecimalField(max_digits=10, decimal_places=4)
    regarding = models.JSONField(default=None, blank=True, null=True)
    validated = models.BooleanField(default=None, blank=True, null=True)
    enact_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    enacted = models.BooleanField(default=None, blank=True, null=True)
    signed = models.JSONField(default=dict)
    iden_length = 20

    def __str__(self):
        return f'TX:{self.id}_re:{self.regarding},to:{self.ReceiverWallet_obj}/{self.token_value}-tokens.{self.validated}'

    class Meta:
        ordering = ['-created', 'id']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Transaction', 'networkChain': 'Wallet', 'modlVer': 1, 'id': None, 'created': None, 'validations': {}, 'senderChainGenId': None, 'senderBlockId': None, 'SenderBlock_obj': None, 'ReceiverBlock_obj': None, 'ReceiverWallet_obj': None, 'SenderWallet_obj': None, 'token_value': '0', 'regarding': None, 'validated': None, 'enact_dt': None, 'enacted': None, 'iden_length': 20, 'signed': {}}
        
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','token_value','ReceiverWallet_obj','SenderWallet_obj','enact_dt']

    def get_chains(self, obj=None):
        commit_chain = None
        if self.SenderWallet_obj:
            commit_chain = self.SenderWallet_obj.get_chain()
        network_chain = self.ReceiverWallet_obj.get_chain()
        return network_chain, commit_chain

    def assess_validation(self):
        prnt('-assess_validation', now_utc())
        from utils.locked import verify_obj_to_data
        if verify_obj_to_data(self, self):
            if self.SenderBlock_obj:
                prev_Sendblock = self.SenderBlock_obj.get_previous_block()
                if prev_Sendblock and prev_Sendblock._meta.object_name == 'Blockchain' or prev_Sendblock and prev_Sendblock.validated:
                    if self.SenderBlock_obj.validated:
                        prnt('true1')
                        return True
            else:
                self_node = get_self_node()
                chain = Blockchain.objects.filter(id=self.senderChainGenId).values('id').first()
                if chain and self_node.chain_array and chain['id'] in self_node.chain_array:
                    if self.ReceiverBlock_obj and self.ReceiverBlock_obj.validated:
                        prnt('true2')
                        return True
        prnt('false')
        return False
    
    def get_reward_block(self):
        if 'BlockReward' in self.regarding:
            from network.models import Block
            rewardBlockId = self.regarding['BlockReward']
            return Block.objects.filter(id=rewardBlockId).first()
        return None

    def calculate(self, value=None, wallet_total=None, dir='receive', return_float=False, exclude_from_tally=None):
        if not value:
            value = self.token_value
        if dir == 'receive' or dir == 'add':
            wallet_total = self.ReceiverWallet_obj.tally_tokens(exclude=exclude_from_tally)
        elif self.SenderWallet_obj:
            if dir == 'send' or dir == 'subtract' or dir == 'sub':
                wallet_total = self.SenderWallet_obj.tally_tokens(exclude=exclude_from_tally)
        if dir == 'receive':
            result = Decimal(wallet_total) + Decimal(value)
        elif dir == 'send':
            result = Decimal(wallet_total) - Decimal(value)
        if return_float:
            return result
        else:
            return str(result)

    def enact_transaction(self, id=None):
        prnt('-enact_transaction')
        if not self.validated:
            return False
        if self.enacted:
            return True
        if self.enact_dt and self.enact_dt > now_utc():
            return False
        if not self.assess_validation():
            return False
        if self.ReceiverBlock_obj and self.ReceiverBlock_obj.validated == False:
            self.ReceiverBlock_obj = None
            self.save()
            self.send_for_block_creation()
            return False

        if not self.ReceiverBlock_obj or not self.ReceiverBlock_obj.validated == True:
            prnt('rf4')
            return False
        if self.SenderWallet_obj:
            sender_wallet = self.SenderWallet_obj
            sender_wallet.value = self.calculate(value=self.token_value, dir='send', exclude_from_tally=self)
            sender_wallet.save(update_fields=['value'])
        receiver_wallet = self.ReceiverWallet_obj
        receiver_wallet.value = self.calculate(value=self.token_value, dir='receive', exclude_from_tally=self)
        receiver_wallet.save(update_fields=['value'])
        self.enacted = True
        super(Transaction, self).save()
        return True
        
    def tally_tokens(self):
        prnt('-tally_tokens trs')
        if self.ReceiverWallet_obj:
            self.ReceiverWallet_obj.tally_tokens()
        if self.SenderWallet_obj:
            self.SenderWallet_obj.tally_tokens()

    def send_for_block_creation(self, id=None, downstream_worker=True, do_not_save=False):
        prnt('-send_for_block_creation',self.id,downstream_worker)
        from utils.locked import get_node_assignment
        from utils.models import get_self_node, round_time, e_brake
        if e_brake(1):
            return

        self_node = get_self_node()
        prnt('self.ReceiverBlock_obj',self.ReceiverBlock_obj,'senderBlockId',self.senderBlockId)
        if self.SenderBlock_obj:
            senderBlock = self.SenderBlock_obj
        else:
            senderBlock = Block.objects.filter(id=self.senderBlockId).first()
        if not senderBlock or senderBlock.validated == False:
            self.validated = False
            self.save()
            prnt('no senderBlock')
            return None
        if senderBlock and senderBlock.validated and not self.validated:
            self.mark_valid()
        if self.validated == False:
            prnt('not valid')
            return None
        if self.ReceiverBlock_obj:
            prnt('done send_for_block_creation4')
            return self.ReceiverBlock_obj
        else:
            receiverBlock = Block.objects.filter(Transaction_obj=self, Blockchain_obj__genesisId=self.ReceiverWallet_obj.id).exclude(id=self.senderBlockId).exclude(validated=False).order_by('created').first()
            if receiverBlock:
                if not do_not_save:
                    self.ReceiverBlock_obj = receiverBlock
                    self.save()
                prnt('done send_for_block_creation5')
                return receiverBlock
            if self.created < now_utc() - datetime.timedelta(days=3):
                from network.models import retrieve_transaction
                if retrieve_transaction(tx=self.id, block_type='receiver'):
                    prnt('done send_for_block_creation6')
                    return
            prnt('no ReceiverBlock 1')
            now = round_time(now_utc(), amount='10mins')
            creator_nodeId_list, validator_list = get_node_assignment(self, dt=now, return_receiverTransaction=True)
            prnt('creator_nodeId_list, validator_list',creator_nodeId_list, validator_list,'self_node.id',self_node.id)
            receiverChain = self.ReceiverWallet_obj.get_chain()

            if self_node.id in creator_nodeId_list:
                receiverChain = self.ReceiverWallet_obj.get_chain()
                prnt('receiverChain',receiverChain)
                receiverBlock = receiverChain.create_block(transaction=self, dt=now)
                if not receiverBlock:
                    prnt('done send_for_block_creation7')
                    return None
                self.ReceiverBlock_obj = receiverBlock
                self.save()
                if downstream_worker:
                    queue = django_rq.get_queue('main')
                    queue.enqueue(receiverBlock.broadcast, broadcast_list={self_node.id:validator_list}, target_node_id=self_node.id, job_timeout=150)
                else:
                    receiverBlock.broadcast(broadcast_list={self_node.id:validator_list}, target_node_id=self_node.id)
                prnt('self.updated_on_node:', self.updated_on_node, 'now_uct()', now_utc(),'self.ReceiverBlock_obj:', self.ReceiverBlock_obj)
                prnt('done send_for_block_creation1')
                return receiverBlock
        prnt('done send_for_block_creation3')
        return None

    def mark_valid(self, skip_assess=False, downstream_worker=None):
        prnt('-mark_valid',self,self.validated)
        if not self.validated:
            if skip_assess or self.assess_validation():
                from utils.locked import verify_obj_to_data
                if verify_obj_to_data(self, self):
                    self.validated = True
                    super(Transaction, self).save()

                receiverChain = self.ReceiverWallet_obj.get_chain()
                if 'pending' in receiverChain.queuedData and self.id in receiverChain.queuedData['pending']:
                    del receiverChain.queuedData['pending'][self.id]
                    receiverChain.save()

                if self.SenderWallet_obj:
                    senderChain = self.SenderWallet_obj.get_chain()
                    if 'pending' in senderChain.queuedData and self.id in senderChain.queuedData['pending']:
                        del senderChain.queuedData['pending'][self.id]
                    senderChain.save()

        if self.validated and not self.enacted:
            if not self.enact_dt or self.enact_dt < now_utc():
                self.enact_transaction()

    def is_not_valid(self, omit=None, note=None):
        prnt('-is_not_valid tx',self.id)
        self.validated = False
        super(Transaction, self).save()

        if self.ReceiverWallet_obj:
            receiverChain = self.ReceiverWallet_obj.get_chain()
            if 'pending' in receiverChain.queuedData and self.id in receiverChain.queuedData['pending']:
                del receiverChain.queuedData['pending'][self.id]
                receiverChain.save()
            if self.ReceiverBlock_obj and self.ReceiverBlock_obj != False:
                self.ReceiverBlock_obj.is_not_valid(note=note, mark_strike=False)
            if self.SenderWallet_obj:
                senderChain = self.SenderWallet_obj.get_chain()
                if 'pending' in senderChain.queuedData and self.id in senderChain.queuedData['pending']:
                    del senderChain.queuedData['pending'][self.id]
                senderChain.save()
            if self.enacted:
                self.enacted = False
                super(Transaction, self).save()
                self.tally_tokens()

    def initialize(self):
        self.modlVer = self.latestVer
        if not self.created:
            self.created = now_utc()
        if not self.enact_dt:
            self.enact_dt = self.created
        if self.id is None:
            self.id = hash_obj_id(self)
        return self

    def save(self, share=False, sig=None, *args, **kwargs):
        prnt('-saving transaction', self)
        def contains_invalid_characters(s):
            return bool(re.search(r'[^0-9.]', s))
        if not self.SenderWallet_obj:
            if not self.regarding or 'BlockReward' not in self.regarding:
                prnt('do not save transaction1')
                return None
        if contains_invalid_characters(self.token_value):
            prnt('do not save transaction2')
            return None

        # create block obj
        if self.id is None and not self.regarding or self.id is None and 'BlockReward' in self.regarding and self.regarding['BlockReward'] == 'coming' and Decimal(self.token_value) == 0:
            self.initialize()
            super(Transaction, self).save(*args, **kwargs)
            prnt('transaction saved1')
            return
        
        else:
            update_fields = kwargs.get('update_fields', None)
            if update_fields and len(update_fields) == 1:
                if all(i for i in update_fields if i in ['validations','ReceiverBlock_obj','SenderBlock_obj']):
                    update_fields.append('updated_on_node')
                    kwargs['update_fields'] = update_fields
                    self.updated_on_node = now_utc()
                    prnt('transaction saved3')
                    super(Transaction, self).save(*args, **kwargs)
                    return
            elif not is_locked(self):
                from utils.locked import verify_data, get_signing_data
                if verify_data(get_signing_data(self), self.signed, signature=sig):
                
                    super(Transaction, self).save(*args, **kwargs)
                    prnt('transaction saved2')
                    return
        prnt('transaction not saved')
    
    def delete(self, superDel=False, skip_block=None):
        if not is_locked(self) or superDel:
            sender_block = self.SenderBlock_obj
            receiver_block = self.ReceiverBlock_obj
            self.SenderBlock_obj = None
            self.ReceiverBlock_obj = None
            self.save(update_fields=['ReceiverBlock_obj','SenderBlock_obj'])
            super(Transaction, self).delete()
            if sender_block and sender_block.id != skip_block:
                if not is_locked(sender_block) or superDel:
                    super(Block, sender_block).delete()
            if receiver_block and receiver_block.id != skip_block:
                if not is_locked(receiver_block) or superDel:
                    super(Block, receiver_block).delete()
