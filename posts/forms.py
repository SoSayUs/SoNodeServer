from django import forms

from .models import Post
from legis.models import Agenda

from datetime import date

today = date.today()
    
class AgendaForm(forms.ModelForm):
    date = forms.DateField(widget=forms.TextInput(attrs={'value': today, 'type': 'date'}), required=True)

    class Meta:
        model = Agenda
        fields = ['date']

class PostSearchForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['pointerType']


class SearchForm(forms.Form):
    search = forms.CharField(required=False, label='Search')
    
class DateForm(forms.Form):
    date = forms.CharField(required=False, label='Date')