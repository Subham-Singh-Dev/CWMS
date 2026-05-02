from rest_framework import serializers
from attendance.models import Attendance
from employees.models import Employee
from payroll.models import MonthlySalary, Advance


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source='employee.name', 
        read_only=True
    )

    class Meta:
        model = Attendance
        fields = [
            'id',
            'employee',
            'employee_name', 
            'date',
            'status',
            'overtime_hours',
        ]


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            'id',
            'name',
            'phone_number',
            'is_active',
            'join_date',
            'daily_wage',
            'role', 
            'employment_type',
        ]

class AdvanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source='employee.name',
        read_only=True
    )
    class Meta:
        model = Advance
        fields = [
            'id',
            'employee',
            'employee_name',
            'amount',
            'issued_date',
            'remaining_amount',
        ]

class MonthlySalarySerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source='employee.name',
        read_only=True
    )
    class Meta:
        model = MonthlySalary
        fields = [
            'id',
            'employee',
            'employee_name',
            'month',
            'gross_pay',
            'net_pay',
            'advance_deducted',
            'is_paid',
        ]