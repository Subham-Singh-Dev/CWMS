from django import forms
from employees.models import Employee

class AssignLeaveForm(forms.Form):
    LEAVE_TYPE_CHOICES = [
        ('EL', 'Earned Leave'),
        ('CL', 'Casual Leave'),
        ('SL', 'Sick Leave'),
    ]

    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        label="Select Employee",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    department = forms.CharField(
        max_length=100, 
        required=False, 
        label="Department / Site",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Department'})
    )
    leave_type = forms.ChoiceField(
        choices=LEAVE_TYPE_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    from_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    to_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    total_days = forms.IntegerField(
        min_value=1,
        label="Total Days",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
    address_on_leave = forms.CharField(
        required=False,
        label="Address/Contact while on leave",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")

        if from_date and to_date and to_date < from_date:
            raise forms.ValidationError("To Date cannot be before From Date.")
        return cleaned_data